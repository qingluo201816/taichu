"""Knowledge extraction workflow tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import PrivateAttr

from taichu.application.services.import_service import ImportService
from taichu.application.services.chapter_service import ChapterService
from taichu.application.contracts.llm import LLMModelIdentity, LLMModelProfile
from taichu.application.contracts.knowledge_sedimentation_progress_repository import (
    InMemoryKnowledgeSedimentationProgressRepository,
)
from taichu.application.invocations.config import TAICHU_MODEL_REQUEST_METADATA_KEY
from taichu.application.services.knowledge_extraction_service import (
    KnowledgeExtractionService,
    _aggregate_batch_candidates,
    _identity_from_profile,
)
from taichu.application.agents.knowledge_extraction.workflow import (
    KnowledgeExtractionDependencies,
    _aggregate_entities,
    _candidate_validation_errors,
    _canonical_entity_name,
    _ground_candidates_from_entity_groups,
    _item_quality_decision,
    _match_existing,
    _technique_quality_decision,
    dedupe_candidates_by_target,
    initial_knowledge_extraction_state,
    mark_cross_type_projection_conflicts,
    mark_epistemic_fact_conflicts,
    merge_overlapping_event_candidates,
    synthesize_candidate_summaries,
)
from taichu.application.services.knowledge_service import KnowledgeService
from taichu.application.agents.models.agent_run import AgentRunStatus
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType
from taichu.infrastructure.agent_runs import JsonAgentRunStore
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend
from tests.fakes import InMemoryKnowledgeRepository


class KnowledgeExtractionWorkflowTest(unittest.IsolatedAsyncioTestCase):
    """Verify LangGraph workflow behavior with mock LLM responses."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.assets_root = Path(self._temporary_directory.name)
        self.storage = ProjectAssetStorageBackend(self.assets_root)
        await ImportService(self.storage).import_text(
            (
                "第一章 山门\n"
                "秦阳握着青铜令牌走入太初教山门。\n"
                "秦阳在山门前确认太初教规。\n"
                "秦阳仍在炼气一层。\n"
                "秦阳默诵太初引气诀。\n"
                "太初教规矩，持青铜令牌方可入山。\n"
                "小山羊胡子在旁边看了一眼。\n"
                "少年们围在药铺门口。"
            ),
            source_name="workflow_fixture.txt",
        )
        self.chapter_service = ChapterService(self.storage)
        self.repository = InMemoryKnowledgeRepository()
        self.knowledge_service = KnowledgeService(self.repository)
        self.run_store = JsonAgentRunStore(self.assets_root)

    async def asyncTearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_profile_identity_preserves_the_selected_provider(self) -> None:
        profile = LLMModelProfile(
            id="deepseek-v4-pro",
            display_name="DeepSeek V4 Pro",
            provider="deepseek_official",
            upstream_model="deepseek-v4-pro",
            wire_protocol="anthropic_messages",
            enabled=True,
            is_default=True,
            supports_streaming=True,
            upstream_verified=True,
        )

        identity = _identity_from_profile(profile)

        self.assertEqual(identity.provider, "deepseek_official")

    def _service(self, llm: _TestLLM) -> KnowledgeExtractionService:
        return KnowledgeExtractionService(
            chapter_service=self.chapter_service,
            llm=llm,
            model_catalog=llm,
            knowledge_repository=self.repository,
            knowledge_service=self.knowledge_service,
            run_store=self.run_store,
            sedimentation_progress_repository=(
                InMemoryKnowledgeSedimentationProgressRepository()
            ),
        )

    async def test_immortal_seed_leaf_levels_share_one_realm_group(self) -> None:
        state = initial_knowledge_extraction_state(
            chapter_id="chapter_001",
            chapter_title="第一章 山门",
            model_name="test-model",
        )
        state["markdown_text"] = "秦阳突破仙苗境一叶，随后抵达仙苗境三叶。"
        state["raw_mentions"] = [
            {
                "name": "仙苗境一叶",
                "knowledge_type": "realm",
                "evidence_excerpts": ["秦阳突破仙苗境一叶"],
            },
            {
                "name": "仙苗境三叶",
                "knowledge_type": "realm",
                "evidence_excerpts": ["随后抵达仙苗境三叶"],
            },
        ]

        aggregated = await _aggregate_entities()(state)

        self.assertEqual(len(aggregated["entity_groups"]), 1)
        group = aggregated["entity_groups"][0]
        self.assertEqual(group["canonical_name"], "仙苗境")
        self.assertEqual(group["raw_names"], ["仙苗境一叶", "仙苗境三叶"])
        self.assertEqual(group["mention_count"], 2)

    def test_only_immortal_seed_leaf_levels_are_folded(self) -> None:
        self.assertEqual(_canonical_entity_name("realm", "仙苗境三十五叶"), "仙苗境")
        self.assertEqual(
            _canonical_entity_name("realm", "仙苗境四十五至四十九叶"), "仙苗境"
        )
        self.assertEqual(_canonical_entity_name("realm", "仙树境"), "仙树境")
        self.assertEqual(
            _canonical_entity_name("character", "仙苗境三叶"), "仙苗境三叶"
        )

    async def test_workflow_writes_completed_run_with_prompt_and_review_items(
        self,
    ) -> None:
        llm = _PromptAwareLLM()
        service = self._service(llm)

        run = await service.create_run(chapter_id="chapter_001")
        loaded = await self.run_store.get_run(run.run_id)

        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertIsNotNone(loaded)
        self.assertEqual(run.metrics.llm_call_count, 4)
        self.assertEqual(run.model_name, "test-model")
        self.assertIsNone(run.requested_model_name)
        self.assertEqual(run.generation_model_identity, _TEST_MODEL_IDENTITY)
        self.assertEqual(
            run.scope.chapter_content_hashes,
            {"chapter_001": run.scope.content_hash},
        )
        self.assertTrue(all(call.model_name == "test-model" for call in run.llm_calls))
        self.assertGreaterEqual(run.metrics.candidate_total, 8)
        self.assertGreaterEqual(len(run.raw_mentions), 8)
        self.assertEqual(run.raw_mentions[0].name, "秦阳")
        self.assertGreaterEqual(len(run.entity_groups), 8)
        self.assertEqual(run.entity_groups[0].quality_decision, "accepted")
        self.assertGreaterEqual(len(run.entity_groups[0].evidence_excerpts), 2)
        node_names = [node.node_name for node in run.nodes]
        self.assertIn("MentionNormalizeNode", node_names)
        self.assertIn("EntityAggregationNode", node_names)
        self.assertIn("CandidateQualityGateNode", node_names)
        self.assertIn("EventRuleExpertNode", node_names)
        self.assertIn("MergeExpertCandidatesNode", node_names)
        self.assertIn("WriteIntermediateJsonNode", node_names)
        self.assertNotIn("MergeChapterCandidatesNode", node_names)
        graph_edges = {(edge.source, edge.target) for edge in run.graph_edges}
        self.assertIn(("TypeDispatchNode", "CharacterExpertNode"), graph_edges)
        self.assertIn(("TypeDispatchNode", "EntityExpertNode"), graph_edges)
        self.assertIn(("TypeDispatchNode", "EventRuleExpertNode"), graph_edges)
        self.assertIn(("EventRuleExpertNode", "MergeExpertCandidatesNode"), graph_edges)
        self.assertTrue(
            all(call.input_prompt and call.raw_response for call in run.llm_calls)
        )
        self.assertTrue(
            all("importance" not in call.input_prompt for call in run.llm_calls)
        )
        prompts_by_node = {call.node_name: call.input_prompt for call in run.llm_calls}
        general_prompt = prompts_by_node["GeneralExtractionNode"]
        self.assertIn("朴素常识、社会经验、人物观点", general_prompt)
        self.assertIn("每个 mention 只能对应一个独立对象", general_prompt)
        self.assertIn("所属对象＋称谓", general_prompt)
        self.assertIn("修饰语＋类别词", general_prompt)
        self.assertIn("禁止把两个地点", general_prompt)
        self.assertIn(
            "同一泛称可能指向多人时必须省略",
            prompts_by_node["CharacterExpertNode"],
        )
        self.assertIn(
            "禁止创建复合新卡",
            prompts_by_node["EntityExpertNode"],
        )
        self.assertIn(
            "已有 active 卡的 aliases 与 name 具有同等身份约束",
            prompts_by_node["EntityExpertNode"],
        )
        event_rule_prompt = prompts_by_node["EventRuleExpertNode"]
        self.assertIn("同一设定主题和事实集合", event_rule_prompt)
        self.assertIn("同一连续行动链", event_rule_prompt)
        self.assertIn("必须保留事件的认知层级", event_rule_prompt)
        self.assertIn("坠崖、重伤、失联", event_rule_prompt)
        self.assertIn("已有 active 规则卡摘要：\n[]", event_rule_prompt)
        self.assertTrue(all(len(request.tools) == 1 for request in llm.requests))
        self.assertTrue(
            all(request.tool_choice == "required" for request in llm.requests)
        )
        self.assertTrue(
            all(
                request.tools[0]["function"].get("strict") is True
                for request in llm.requests
            )
        )
        self.assertTrue(
            all("字段 schema" not in _prompt_text(request) for request in llm.requests)
        )
        self.assertTrue(
            all("输出 JSON" not in _prompt_text(request) for request in llm.requests)
        )
        self.assertCountEqual(
            [call.prompt_version for call in run.llm_calls],
            [
                "general_extraction_v4",
                "character_expert_v3",
                "entity_expert_v3",
                "event_rule_expert_v1",
            ],
        )
        self.assertEqual(run.prompt_version, "knowledge_extraction_prompt_v3")
        self.assertIn("GeneralExtractionNode", {node.node_name for node in run.nodes})
        self.assertEqual(run.review_items[0].candidate_action.value, "create_card")
        self.assertGreater(run.metrics.realm_candidate_count, 0)
        self.assertGreater(run.metrics.technique_candidate_count, 0)
        self.assertGreater(run.metrics.event_candidate_count, 0)
        self.assertGreater(run.metrics.rule_candidate_count, 0)

    async def test_event_rule_prompt_can_reuse_semantically_same_active_rule(
        self,
    ) -> None:
        draft = await self.knowledge_service.create_card(
            StructuredKnowledgeType.RULE,
            {
                "name": "太初教山门通行规则",
                "aliases": [],
                "summary": "进入太初教山门需要符合门禁要求。",
                "source_origin": "manual",
                "source_note": "作者确认的山门规则。",
                "exceptions": None,
            },
        )
        confirmed = await self.knowledge_service.confirm_card(draft.id)
        service = self._service(_PromptAwareRuleReuseLLM())

        run = await service.create_run(chapter_id="chapter_001")
        candidate = next(
            item
            for item in run.review_items
            if item.display_title == "太初教山门通行规则"
        )
        event_rule_call = next(
            call for call in run.llm_calls if call.node_name == "EventRuleExpertNode"
        )

        self.assertEqual(candidate.candidate_action.value, "update_card")
        self.assertEqual(candidate.target_card_id, confirmed.id)
        self.assertEqual(candidate.matched_card_name, "太初教山门通行规则")
        self.assertIn('"name": "太初教山门通行规则"', event_rule_call.input_prompt)
        self.assertIn(
            '"summary": "进入太初教山门需要符合门禁要求。"',
            event_rule_call.input_prompt,
        )
        self.assertNotIn("{{active_rule_index}}", event_rule_call.input_prompt)

    async def test_missing_native_tool_call_marks_run_failed(self) -> None:
        service = self._service(_SequenceLLM(["未调用结果工具"]))

        run = await service.create_run(chapter_id="chapter_001")

        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertIn("原生工具契约", run.errors[0])
        self.assertEqual(len(run.llm_calls), 1)
        self.assertEqual(run.llm_calls[0].error is not None, True)

    async def test_existing_card_summary_is_synthesized_as_one_fact_snapshot(
        self,
    ) -> None:
        draft = await self.knowledge_service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {
                "name": "秦阳",
                "aliases": [],
                "summary": "秦阳原本是太初教弟子。",
                "source_origin": "manual",
                "source_note": "第一章之前的作者设定。",
                "identity": "太初教弟子",
            },
        )
        await self.knowledge_service.confirm_card(draft.id)
        service = self._service(_PromptAwareLLM())

        run = await service.create_run(chapter_id="chapter_001")
        candidate = next(
            item for item in run.review_items if item.display_title == "秦阳"
        )

        self.assertEqual(candidate.candidate_action.value, "update_card")
        self.assertEqual(
            candidate.suggested_card["summary"],
            "秦阳是太初教弟子，本章手持青铜令牌走入太初教山门。",
        )
        self.assertNotIn("\n", str(candidate.suggested_card["summary"]))
        synthesis_calls = [
            call
            for call in run.llm_calls
            if call.node_name == "SynthesizeCandidateSummariesNode"
        ]
        self.assertEqual(len(synthesis_calls), 1)
        self.assertIn("秦阳原本是太初教弟子", synthesis_calls[0].input_prompt)

    async def test_summary_synthesis_failure_requires_author_edit(self) -> None:
        draft = await self.knowledge_service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {
                "name": "秦阳",
                "aliases": [],
                "summary": "秦阳原本是太初教弟子。",
                "source_origin": "manual",
                "source_note": "作者设定。",
            },
        )
        await self.knowledge_service.confirm_card(draft.id)
        service = self._service(_PromptAwareSummaryFailureLLM())

        run = await service.create_run(chapter_id="chapter_001")
        candidate = next(
            item for item in run.review_items if item.display_title == "秦阳"
        )

        self.assertEqual(candidate.candidate_action.value, "conflict")
        self.assertEqual(
            candidate.suggested_card["summary"],
            "秦阳原本是太初教弟子。",
        )
        self.assertFalse(candidate.schema_validation.passed)
        self.assertIn("摘要输出格式错误", candidate.schema_validation.errors[-1])

    async def test_summary_synthesis_limits_each_call_to_five_candidates(
        self,
    ) -> None:
        llm = _MultiModelLLM()
        state = initial_knowledge_extraction_state(
            chapter_id="chapter_001",
            model_name="test-model",
            model_id="test-model",
        )
        dependencies = KnowledgeExtractionDependencies(
            chapter_service=self.chapter_service,
            llm=llm,
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )
        candidates = [
            {
                "type": "character",
                "name": f"候选{i}",
                "aliases": [],
                "summary": f"候选{i}的新事实。",
                "source_origin": "agent_extract",
                "source_note": f"第{i}章来源。",
                "evidence_excerpt": f"候选{i}出现。",
                "evidence_excerpts": [f"候选{i}出现。"],
            }
            for i in range(1, 7)
        ]

        result = await synthesize_candidate_summaries(
            state,
            dependencies,
            candidates,
            include_new=True,
            node_name="BatchSynthesizeCandidateSummariesNode",
        )
        summary_requests = [
            request
            for request in llm.requests
            if '"candidate_id"' in _prompt_text(request)
        ]

        self.assertEqual(len(result), 6)
        self.assertEqual(len(summary_requests), 2)
        self.assertEqual(
            [
                len(
                    re.findall(
                        r'"candidate_id":\s*"summary_candidate_', _prompt_text(request)
                    )
                )
                for request in summary_requests
            ],
            [5, 1],
        )
        self.assertTrue(
            all(request.max_output_tokens == 100_000 for request in summary_requests)
        )

    async def test_summary_synthesis_does_not_stack_transport_retries(
        self,
    ) -> None:
        llm = _TransientSummaryFailureLLM()
        state = initial_knowledge_extraction_state(
            chapter_id="chapter_001",
            model_name="test-model",
            model_id="test-model",
        )
        dependencies = KnowledgeExtractionDependencies(
            chapter_service=self.chapter_service,
            llm=llm,
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )
        candidates = [
            {
                "type": "character",
                "name": "秦阳",
                "aliases": [],
                "summary": "秦阳本轮出现。",
                "source_origin": "agent_extract",
                "source_note": "第一章来源。",
                "evidence_excerpt": "秦阳走入山门。",
                "evidence_excerpts": ["秦阳走入山门。"],
            }
        ]

        result = await synthesize_candidate_summaries(
            state,
            dependencies,
            candidates,
            include_new=True,
            node_name="BatchSynthesizeCandidateSummariesNode",
        )

        self.assertEqual(result[0]["summary"], "秦阳本轮出现。")
        self.assertIn("_summary_synthesis_error", result[0])
        self.assertFalse(result[0]["schema_validation"]["passed"])
        self.assertEqual(llm.summary_attempts, 1)
        self.assertEqual(len(state["llm_calls"]), 1)
        self.assertTrue(state["llm_calls"][0]["error"])
        self.assertTrue(state["errors"])

    async def test_summary_synthesis_stops_waiting_after_its_deadline(self) -> None:
        llm = _BlockingLLM()
        state = initial_knowledge_extraction_state(
            chapter_id="chapter_001",
            model_name="test-model",
            model_id="test-model",
        )
        dependencies = KnowledgeExtractionDependencies(
            chapter_service=self.chapter_service,
            llm=llm,
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )
        candidates = [
            {
                "type": "character",
                "name": "秦阳",
                "aliases": [],
                "summary": "秦阳本轮出现。",
                "source_origin": "agent_extract",
                "source_note": "第一章来源。",
                "evidence_excerpt": "秦阳走入山门。",
                "evidence_excerpts": ["秦阳走入山门。"],
            }
        ]

        with patch(
            "taichu.application.agents.knowledge_extraction.workflow."
            "_SUMMARY_SYNTHESIS_TIMEOUT_SECONDS",
            0.01,
        ):
            result = await synthesize_candidate_summaries(
                state,
                dependencies,
                candidates,
                include_new=True,
                node_name="BatchSynthesizeCandidateSummariesNode",
            )

        self.assertTrue(not llm.started.is_set() or llm.cancelled.is_set())
        self.assertIn("_summary_synthesis_error", result[0])
        self.assertIn("摘要超时", result[0]["_summary_synthesis_error"])
        self.assertIn("超过 0.01 秒", state["errors"][0])
        self.assertIn("超过 0.01 秒", state["llm_calls"][0]["error"])

    async def test_summary_synthesis_marks_missing_items_as_output_truncated(
        self,
    ) -> None:
        state = initial_knowledge_extraction_state(
            chapter_id="chapter_001",
            model_name="test-model",
            model_id="test-model",
        )
        dependencies = KnowledgeExtractionDependencies(
            chapter_service=self.chapter_service,
            llm=_TruncatedSummaryLLM(),
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )
        candidates = [
            {
                "type": "character",
                "name": name,
                "aliases": [],
                "summary": f"{name}本轮出现。",
                "source_origin": "agent_extract",
                "source_note": "第一章来源。",
                "evidence_excerpt": f"{name}走入山门。",
                "evidence_excerpts": [f"{name}走入山门。"],
            }
            for name in ("秦阳", "徐羽")
        ]

        result = await synthesize_candidate_summaries(
            state,
            dependencies,
            candidates,
            include_new=True,
            node_name="BatchSynthesizeCandidateSummariesNode",
        )

        self.assertNotIn("_summary_synthesis_error", result[0])
        self.assertIn("摘要输出截断", result[1]["_summary_synthesis_error"])
        self.assertFalse(result[1]["schema_validation"]["passed"])

    async def test_summary_synthesis_rejects_unexpected_output_fields(self) -> None:
        state = initial_knowledge_extraction_state(
            chapter_id="chapter_001",
            model_name="test-model",
            model_id="test-model",
        )
        dependencies = KnowledgeExtractionDependencies(
            chapter_service=self.chapter_service,
            llm=_UnexpectedSummaryFieldLLM(),
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )
        candidates = [
            {
                "type": "character",
                "name": "秦阳",
                "aliases": [],
                "summary": "秦阳本轮出现。",
                "source_origin": "agent_extract",
                "source_note": "第一章来源。",
                "evidence_excerpt": "秦阳走入山门。",
                "evidence_excerpts": ["秦阳走入山门。"],
            }
        ]

        result = await synthesize_candidate_summaries(
            state,
            dependencies,
            candidates,
            include_new=True,
            node_name="BatchSynthesizeCandidateSummariesNode",
        )

        self.assertEqual(result[0]["summary"], "秦阳本轮出现。")
        self.assertIn("摘要输出格式错误", result[0]["_summary_synthesis_error"])
        self.assertFalse(result[0]["schema_validation"]["passed"])

    def test_retired_importance_field_fails_candidate_validation(self) -> None:
        errors = _candidate_validation_errors(
            {
                "type": "character",
                "name": "秦阳",
                "aliases": [],
                "summary": "本章出现的角色。",
                "importance": "normal",
                "source_origin": "agent_extract",
                "source_note": "来自第一章。",
                "evidence_excerpt": "秦阳走入山门。",
            }
        )

        self.assertTrue(any("importance" in error for error in errors))

    def test_named_item_and_technique_use_grounded_function_evidence(self) -> None:
        self.assertEqual(
            _item_quality_decision(
                "明鉴仙眼",
                ["明鉴仙眼能够洞悉弟子的身体并检验仙种资质。"],
            )[0],
            "accepted",
        )

    def test_epistemic_guard_blocks_inferred_death_but_keeps_belief_event(self) -> None:
        candidates = [
            {
                "type": "event",
                "name": "张狂跌落悬崖身亡",
                "summary": "张狂跌落悬崖后已经死亡。",
                "description": "张狂死亡。",
                "evidence_excerpts": [
                    "千丈悬崖掉下去必定粉身碎骨，众人认定张狂必死无疑。"
                ],
            },
            {
                "type": "event",
                "name": "众人误以为张狂已经死亡",
                "summary": "众人因张狂坠崖而误以为他已经死亡。",
                "description": "这是众人的判断，不是死亡事实。",
                "evidence_excerpts": ["众人认定张狂必死无疑。"],
            },
        ]

        guarded = mark_epistemic_fact_conflicts(candidates)

        self.assertTrue(guarded[0].get("internal_conflicts"))
        self.assertIn("不能推导为死亡", guarded[0]["internal_conflicts"][1])
        self.assertNotIn("internal_conflicts", guarded[1])

    def test_epistemic_guard_accepts_directly_confirmed_death(self) -> None:
        candidate = {
            "type": "event",
            "name": "守卫当场身亡",
            "summary": "守卫遭到攻击后当场身亡。",
            "description": "守卫死亡。",
            "evidence_excerpts": ["守卫遭到一击，当场身亡，随后被人抬走。"],
        }

        guarded = mark_epistemic_fact_conflicts([candidate])

        self.assertNotIn("internal_conflicts", guarded[0])
        self.assertEqual(
            _item_quality_decision(
                "窗户",
                ["弟子推开窗户。"],
            )[0],
            "rejected",
        )
        self.assertEqual(
            _technique_quality_decision(
                "六爻卦",
                ["六爻卦乃上古绝学，可预知福祸并制敌于无形。"],
            )[0],
            "accepted",
        )
        self.assertEqual(
            _technique_quality_decision(
                "神识冲击",
                ["神识冲击是修炼灵魂衍生的攻击法。"],
            )[0],
            "accepted",
        )

    def test_expert_evidence_is_replaced_by_grounded_entity_group_quotes(self) -> None:
        state = initial_knowledge_extraction_state(
            chapter_id="chapter_001",
            model_name="test-model",
        )
        state["markdown_text"] = "秦阳握着青铜令牌走入山门。"
        state["entity_groups"] = [
            {
                "entity_group_id": "entity_group_001",
                "evidence_excerpts": ["秦阳握着青铜令牌走入山门。"],
            }
        ]
        candidates = [
            {
                "entity_group_id": "entity_group_001",
                "type": "character",
                "name": "秦阳",
                "evidence_excerpt": "秦阳走进了山门……",
                "evidence_excerpts": ["秦阳走进了山门……"],
            }
        ]

        grounded = _ground_candidates_from_entity_groups(state, candidates)

        self.assertEqual(
            grounded[0]["evidence_excerpts"],
            ["秦阳握着青铜令牌走入山门。"],
        )
        self.assertEqual(
            grounded[0]["evidence_excerpt"],
            "秦阳握着青铜令牌走入山门。",
        )

    def test_candidates_matching_same_confirmed_card_are_merged_once(self) -> None:
        candidates = [
            {
                "type": "faction",
                "name": "至上仙尊真乙太初教",
                "aliases": [],
                "target_card_id": "faction-1",
                "matched_card_name": "至上仙尊真乙太初教",
                "chapter_ids": ["chapter_006"],
                "evidence_excerpts": ["太初教传承数千年。"],
            },
            {
                "type": "faction",
                "name": "太初教",
                "aliases": ["至上仙尊真乙太初教"],
                "target_card_id": "faction-1",
                "matched_card_name": "至上仙尊真乙太初教",
                "chapter_ids": ["chapter_007"],
                "evidence_excerpts": ["太初教出现三名紫种弟子。"],
            },
        ]

        merged = dedupe_candidates_by_target(candidates)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name"], "至上仙尊真乙太初教")
        self.assertEqual(merged[0]["chapter_ids"], ["chapter_006", "chapter_007"])
        self.assertIn("太初教", merged[0]["aliases"])

    def test_new_candidates_with_overlapping_name_and_alias_are_merged_once(
        self,
    ) -> None:
        candidates = [
            {
                "type": "rule",
                "name": "太初教灵田种植与灵泉规则",
                "aliases": ["灵泉灌溉规则", "灵药种植门槛规则"],
                "chapter_ids": ["chapter_034"],
                "chapter_titles": ["第34章"],
                "source_note": "第34章来源。",
                "evidence_excerpts": ["灵泉极为罕见。"],
            },
            {
                "type": "rule",
                "name": "灵泉灌溉规则",
                "aliases": [],
                "chapter_ids": ["chapter_035"],
                "chapter_titles": ["第35章"],
                "source_note": "第35章来源。",
                "evidence_excerpts": ["灵泉只能在同等努力下带来更多收获。"],
            },
        ]

        merged = dedupe_candidates_by_target(candidates)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name"], "太初教灵田种植与灵泉规则")
        self.assertIn("灵泉灌溉规则", merged[0]["aliases"])
        self.assertEqual(merged[0]["chapter_ids"], ["chapter_034", "chapter_035"])
        self.assertEqual(
            merged[0]["evidence_excerpts"],
            ["灵泉极为罕见。", "灵泉只能在同等努力下带来更多收获。"],
        )

    def test_cross_type_projection_is_marked_for_author_review(self) -> None:
        evidence = "神识冲击是修炼灵魂衍生的攻击法。"
        candidates = [
            {
                "type": "technique",
                "name": "神识冲击",
                "evidence_excerpts": [evidence],
            },
            {
                "type": "rule",
                "name": "神识冲击修炼限制",
                "evidence_excerpts": [evidence],
            },
        ]

        marked = mark_cross_type_projection_conflicts(candidates)

        self.assertNotIn("internal_conflicts", marked[0])
        self.assertIn("重复类型投影", marked[1]["internal_conflicts"][0])

    async def test_unique_cross_type_alias_match_reuses_existing_card(self) -> None:
        draft = await self.knowledge_service.create_card(
            StructuredKnowledgeType.CHARACTER,
            {
                "name": "五彩灵兽",
                "aliases": ["小灵兽"],
                "summary": "五彩灵兽可以承载修炼者的神识。",
                "source_origin": "manual",
                "source_note": "作者确认设定。",
                "identity": "灵兽",
            },
        )
        confirmed = await self.knowledge_service.confirm_card(draft.id)
        state = initial_knowledge_extraction_state(
            chapter_id="chapter_001",
            model_name="test-model",
        )
        state["typed_candidates"] = [
            {
                "type": "item",
                "name": "小灵兽",
                "aliases": [],
                "summary": "小灵兽本章表现出承载神识的能力。",
                "source_origin": "agent_extract",
                "source_note": "第一章关键原文。",
                "evidence_excerpt": "修炼者将神识附在小灵兽身上。",
                "evidence_excerpts": ["修炼者将神识附在小灵兽身上。"],
                "item_type": "灵兽",
            }
        ]
        dependencies = KnowledgeExtractionDependencies(
            chapter_service=self.chapter_service,
            llm=_PromptAwareLLM(),
            knowledge_repository=self.repository,
            run_store=self.run_store,
        )

        matched_state = await _match_existing(dependencies)(state)
        candidate = matched_state["typed_candidates"][0]

        self.assertEqual(candidate["target_card_id"], confirmed.id)
        self.assertEqual(candidate["matched_card_name"], "五彩灵兽")
        self.assertEqual(candidate["type"], "character")
        self.assertEqual(candidate["name"], "五彩灵兽")
        self.assertIn("小灵兽", candidate["aliases"])
        self.assertNotIn("item_type", candidate)
        self.assertIn("按已有卡类型对齐", candidate["match_reason"])
        self.assertTrue(candidate["schema_validation"]["passed"])

    def test_same_chapter_event_with_contained_evidence_is_merged(self) -> None:
        candidates = [
            {
                "type": "event",
                "name": "林青采得月华草",
                "aliases": [],
                "summary": "林青采得月华草，并决定当夜立即服下。",
                "source_note": "第十章来源一。",
                "chapter_id": "chapter_010",
                "evidence_excerpt": "采得月华草的林青决定当夜立即服下它。",
                "evidence_excerpts": [
                    "采得月华草的林青决定当夜立即服下它。",
                    "林青将月华草收入怀中。",
                ],
            },
            {
                "type": "event",
                "name": "林青服下月华草",
                "aliases": [],
                "summary": "林青决定当夜立即服下月华草。",
                "source_note": "第十章来源二。",
                "chapter_id": "chapter_010",
                "evidence_excerpt": "林青决定当夜立即服下它。",
                "evidence_excerpts": ["林青决定当夜立即服下它。"],
            },
        ]

        merged = merge_overlapping_event_candidates(candidates)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name"], "林青采得月华草")
        self.assertIn("林青服下月华草", merged[0]["aliases"])
        self.assertEqual(len(merged[0]["evidence_excerpts"]), 3)
        self.assertIn("第十章来源一", merged[0]["source_note"])
        self.assertIn("第十章来源二", merged[0]["source_note"])

    def test_batch_aggregation_reconciles_first_and_last_seen_chapters(self) -> None:
        states = [
            {
                "chapter_id": "chapter_006",
                "chapter_title": "第6章",
                "typed_candidates": [_batch_character_candidate("chapter_006")],
            },
            {
                "chapter_id": "chapter_010",
                "chapter_title": "第10章",
                "typed_candidates": [_batch_character_candidate("chapter_010")],
            },
        ]

        aggregated = _aggregate_batch_candidates(states)

        self.assertEqual(aggregated[0]["first_seen_chapter_id"], "chapter_006")
        self.assertEqual(aggregated[0]["last_seen_chapter_id"], "chapter_010")

    async def test_invalid_expert_tool_arguments_fail_without_prompt_repair(
        self,
    ) -> None:
        service = self._service(_PromptAwareRepairLLM())

        run = await service.create_run(chapter_id="chapter_001")

        self.assertEqual(run.status, AgentRunStatus.FAILED)
        event_calls = [
            call for call in run.llm_calls if call.node_name == "EventRuleExpertNode"
        ]
        self.assertEqual(len(event_calls), 1)
        self.assertIsNotNone(event_calls[0].error)
        self.assertIn("原生工具契约", event_calls[0].error or "")
        self.assertNotIn("json_repair", event_calls[0].prompt_version)

    async def test_quality_gate_filters_generic_mentions_before_experts(self) -> None:
        service = self._service(_SequenceLLM([_generic_mentions_response()]))

        run = await service.create_run(chapter_id="chapter_001")

        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertEqual(run.metrics.llm_call_count, 1)
        self.assertEqual(run.metrics.candidate_total, 0)
        self.assertEqual(len(run.entity_groups), 3)
        self.assertTrue(
            all(group.quality_decision == "rejected" for group in run.entity_groups)
        )
        self.assertEqual(run.raw_candidates, [])

    async def test_batch_run_locks_selected_model_for_all_chapters(self) -> None:
        await ImportService(self.storage).import_text(
            "第一章 山门\n秦阳握着青铜令牌走入太初教山门。\n"
            "第二章 入门\n秦阳在山门前确认太初教规。",
            source_name="batch_model_fixture.txt",
        )
        llm = _MultiModelLLM()
        service = self._service(llm)

        events = [
            event
            async for event in service.stream_batch_run(
                chapter_ids=["chapter_001", "chapter_002"],
                model_name="alternate-model",
            )
        ]
        run = next(
            event["run"]
            for event in reversed(events)
            if isinstance(event.get("run"), dict)
        )

        self.assertTrue(llm.requests)
        self.assertTrue(
            all(request.model_id == "alternate-model" for request in llm.requests)
        )
        self.assertTrue(
            all(request.max_output_tokens == 100_000 for request in llm.requests)
        )
        self.assertFalse(
            any(
                call["node_name"] == "BatchSynthesizeCandidateSummariesNode"
                for call in run["llm_calls"]
            )
        )
        self.assertEqual(run["model_id"], "alternate-model")
        self.assertEqual(run["upstream_model"], "upstream-alternate")
        self.assertTrue(
            all(call["model_id"] == "alternate-model" for call in run["llm_calls"])
        )

    async def test_batch_run_is_failed_when_every_chapter_extraction_fails(
        self,
    ) -> None:
        service = self._service(_AlwaysFailLLM())

        events = [
            event
            async for event in service.stream_batch_run(
                chapter_ids=["chapter_001"],
            )
        ]
        run = next(
            event["run"]
            for event in reversed(events)
            if isinstance(event.get("run"), dict)
        )

        self.assertEqual(run["status"], AgentRunStatus.FAILED.value)
        self.assertEqual(run["failed_chapter_count"], 1)
        self.assertTrue(run["errors"])
        self.assertIn("无权调用该模型", run["errors"][0])
        self.assertEqual(events[-1]["event_type"], "task_failed")

    async def test_deleting_running_batch_cancels_task_and_keeps_record_deleted(
        self,
    ) -> None:
        llm = _BlockingLLM()
        service = self._service(llm)

        run = await service.start_batch_run_task(chapter_ids=["chapter_001"])
        await asyncio.wait_for(llm.started.wait(), timeout=1)
        await service.delete_run(run.run_id)

        await asyncio.wait_for(llm.cancelled.wait(), timeout=1)
        self.assertIsNone(await self.run_store.get_run(run.run_id))

    def test_batch_aggregation_keeps_one_source_block_per_chapter(self) -> None:
        candidates = _aggregate_batch_candidates(
            [
                {
                    "chapter_id": "chapter_001",
                    "chapter_title": "第一章 山门",
                    "typed_candidates": [
                        {
                            "type": "character",
                            "name": "秦阳",
                            "aliases": [],
                            "summary": "进入山门。",
                            "source_note": "旧格式来源。",
                            "evidence_excerpts": ["秦阳进入山门。"],
                        }
                    ],
                },
                {
                    "chapter_id": "chapter_002",
                    "chapter_title": "第二章 入门",
                    "typed_candidates": [
                        {
                            "type": "character",
                            "name": "秦阳",
                            "aliases": [],
                            "summary": "确认门规。",
                            "source_note": "旧格式来源。",
                            "evidence_excerpts": ["秦阳确认门规。"],
                        }
                    ],
                },
            ]
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["source_note"],
            "第一章 山门\n关键原文：“秦阳进入山门。”\n\n第二章 入门\n关键原文：“秦阳确认门规。”",
        )


_TEST_MODEL_IDENTITY = LLMModelIdentity(
    provider="test",
    model_id="test-model",
    family="test-model",
    endpoint_kind="test",
    known=True,
)


@dataclass(frozen=True)
class _NativeModelRequest:
    messages: tuple[BaseMessage, ...]
    tools: tuple[dict[str, Any], ...]
    tool_choice: str
    model_id: str
    run_id: str | None
    max_output_tokens: int | None


class _TestLLM(BaseChatModel):
    model_id: str = "deepseek-v4-pro"
    _requests: list[_NativeModelRequest] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "taichu-knowledge-extraction-test"

    @property
    def requests(self) -> list[_NativeModelRequest]:
        return self._requests

    @property
    def model_identity(self) -> LLMModelIdentity:
        return _TEST_MODEL_IDENTITY

    def list_models(self) -> list[LLMModelProfile]:
        return [
            LLMModelProfile(
                id="deepseek-v4-pro",
                display_name="test-model",
                provider="rightcode",
                upstream_model="test-model",
                wire_protocol="openai_responses",
                enabled=True,
                is_default=True,
                supports_streaming=False,
                upstream_verified=True,
            )
        ]

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        formatted = [convert_to_openai_tool(tool, strict=True) for tool in tools]
        normalized_choice = "required" if tool_choice == "any" else tool_choice
        return self.bind(
            tools=formatted,
            tool_choice=normalized_choice or "auto",
            **kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        raise NotImplementedError("知识沉淀测试模型只支持异步调用。")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if stop:
            raise ValueError("知识沉淀测试模型不支持 stop 参数。")
        metadata = getattr(run_manager, "metadata", None)
        request_metadata = (
            metadata.get(TAICHU_MODEL_REQUEST_METADATA_KEY, {})
            if isinstance(metadata, dict)
            else {}
        )
        tools = tuple(dict(item) for item in kwargs.pop("tools", ()))
        tool_choice = str(kwargs.pop("tool_choice", "auto"))
        kwargs.pop("ls_structured_output_format", None)
        if kwargs:
            raise ValueError("测试模型收到未知调用参数：" + "、".join(sorted(kwargs)))
        request = _NativeModelRequest(
            messages=tuple(messages),
            tools=tools,
            tool_choice=tool_choice,
            model_id=str(request_metadata.get("model_id") or self.model_id),
            run_id=_optional_string(request_metadata.get("run_id")),
            max_output_tokens=_optional_int(
                request_metadata.get("max_output_tokens")
            ),
        )
        self._requests.append(request)
        message = await self.complete(request)
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"model_id": request.model_id},
        )

    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        del request
        raise NotImplementedError


class _SequenceLLM(_TestLLM):
    def __init__(self, responses: list[str]) -> None:
        super().__init__()
        self._responses = responses

    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        if not self._responses:
            raise RuntimeError("没有可用的模拟 LLM 响应。")
        raw_response = self._responses.pop(0)
        try:
            json.loads(raw_response)
        except json.JSONDecodeError:
            return _text_response(raw_response)
        return _native_response(request, raw_response)


class _PromptAwareLLM(_TestLLM):
    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        prompt_text = _prompt_text(request)
        payload_by_tool = {
            "SummarySynthesisOutput": _summary_response(prompt_text),
            "EventRuleExpertOutput": _event_rule_response(),
            "EntityExpertOutput": _entity_response(),
            "CharacterExpertOutput": _character_response(),
            "GeneralExtractionOutput": _general_response(),
        }
        return _native_response(request, payload_by_tool[_selected_tool(request)])


class _AlwaysFailLLM(_TestLLM):
    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        del request
        raise RuntimeError("当前密钥无权调用该模型，请检查本机密钥权限。")


class _BlockingLLM(_TestLLM):
    _started: asyncio.Event = PrivateAttr()
    _cancelled: asyncio.Event = PrivateAttr()
    _release: asyncio.Event = PrivateAttr()

    def __init__(self) -> None:
        super().__init__()
        self._started = asyncio.Event()
        self._cancelled = asyncio.Event()
        self._release = asyncio.Event()

    @property
    def started(self) -> asyncio.Event:
        return self._started

    @property
    def cancelled(self) -> asyncio.Event:
        return self._cancelled

    @property
    def release(self) -> asyncio.Event:
        return self._release

    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return _native_response(request, _general_response())


class _PromptAwareRuleReuseLLM(_PromptAwareLLM):
    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        prompt_text = _prompt_text(request)
        if _selected_tool(request) == "SummarySynthesisOutput":
            candidate_ids = list(
                dict.fromkeys(re.findall(r'"candidate_id":\s*"([^"]+)"', prompt_text))
            )
            return _native_response(
                request,
                {
                    "summaries": [
                        {
                            "candidate_id": candidate_id,
                            "summary": "进入太初教山门需要持有青铜令牌。",
                        }
                        for candidate_id in candidate_ids
                    ]
                },
            )
        if _selected_tool(request) == "EventRuleExpertOutput":
            return _native_response(request, _event_rule_reuse_response())
        return await super().complete(request)


class _PromptAwareSummaryFailureLLM(_PromptAwareLLM):
    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        if _selected_tool(request) == "SummarySynthesisOutput":
            return _text_response("未调用摘要结果工具")
        return await super().complete(request)


class _TransientSummaryFailureLLM(_TestLLM):
    _summary_attempts: int = PrivateAttr(default=0)

    @property
    def summary_attempts(self) -> int:
        return self._summary_attempts

    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        prompt_text = _prompt_text(request)
        if _selected_tool(request) == "SummarySynthesisOutput":
            self._summary_attempts += 1
            if self._summary_attempts == 1:
                raise RuntimeError("模型调用失败，请稍后重试。")
            return _native_response(request, _summary_response(prompt_text))
        return _native_response(request, _general_response())


class _UnexpectedSummaryFieldLLM(_TestLLM):
    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        return _native_response(
            request,
            {
                "summaries": [
                    {
                        "candidate_id": "summary_candidate_001",
                        "summary": "秦阳走入太初教山门。",
                        "source_note": "不允许模型返回来源字段。",
                    }
                ]
            },
        )


class _TruncatedSummaryLLM(_TestLLM):
    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        return _native_response(
            request,
            {
                "summaries": [
                    {
                        "candidate_id": "summary_candidate_001",
                        "summary": "秦阳走入太初教山门。",
                    }
                ]
            },
            output_tokens=100_000,
            finish_reason="length",
        )


class _PromptAwareRepairLLM(_TestLLM):
    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        payload_by_tool = {
            "EventRuleExpertOutput": _broken_event_rule_response(),
            "EntityExpertOutput": _entity_response(),
            "CharacterExpertOutput": _character_response(),
            "GeneralExtractionOutput": _general_response(),
        }
        return _native_response(request, payload_by_tool[_selected_tool(request)])


class _MultiModelLLM(_TestLLM):
    def __init__(self) -> None:
        super().__init__()

    def list_models(self) -> list[LLMModelProfile]:
        return [
            _profile("test-model", "upstream-test", is_default=True),
            _profile("alternate-model", "upstream-alternate"),
        ]

    async def complete(self, request: _NativeModelRequest) -> AIMessage:
        prompt_text = _prompt_text(request)
        payload_by_tool = {
            "SummarySynthesisOutput": _summary_response(prompt_text),
            "EventRuleExpertOutput": _event_rule_response(),
            "EntityExpertOutput": _entity_response(),
            "CharacterExpertOutput": _character_response(),
            "GeneralExtractionOutput": _general_response(),
        }
        return _native_response(request, payload_by_tool[_selected_tool(request)])


def _prompt_text(request: _NativeModelRequest) -> str:
    return "\n".join(_message_text(message) for message in request.messages)


def _selected_tool(request: _NativeModelRequest) -> str:
    if request.tool_choice not in {"auto", "none", "required"}:
        return request.tool_choice
    function = request.tools[-1]["function"]
    return str(function["name"])


def _native_response(
    request: _NativeModelRequest,
    payload: object,
    *,
    output_tokens: int | None = None,
    finish_reason: str = "stop",
) -> AIMessage:
    try:
        arguments = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError as error:
        return AIMessage(
            content="",
            invalid_tool_calls=[
                {
                    "id": "call_structured_output",
                    "name": _selected_tool(request),
                    "args": payload,
                    "error": str(error),
                    "type": "invalid_tool_call",
                }
            ],
        )
    if not isinstance(arguments, dict):
        raise TypeError("结构化输出测试载荷必须是 JSON 对象。")
    usage_metadata = (
        {
            "input_tokens": 0,
            "output_tokens": output_tokens,
            "total_tokens": output_tokens,
        }
        if output_tokens is not None
        else None
    )
    return AIMessage(
        content="",
        id="call_structured_output",
        tool_calls=[
            {
                "id": "call_structured_output",
                "name": _selected_tool(request),
                "args": arguments,
                "type": "tool_call",
            }
        ],
        usage_metadata=usage_metadata,
        response_metadata={
            "model_id": request.model_id,
            "upstream_model": request.model_id,
            "finish_reason": finish_reason,
            "cost_currency": "USD",
            "cost_kind": "unknown",
        },
    )


def _text_response(text: str) -> AIMessage:
    return AIMessage(
        content=text,
        response_metadata={"finish_reason": "stop"},
    )


def _message_text(message: BaseMessage) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return None


def _summary_response(prompt: str) -> str:
    candidate_ids = list(
        dict.fromkeys(re.findall(r'"candidate_id":\s*"([^"]+)"', prompt))
    )
    return json.dumps(
        {
            "summaries": [
                {
                    "candidate_id": candidate_id,
                    "summary": (
                        "秦阳是太初教弟子，本章手持青铜令牌走入太初教山门。"
                        if candidate_id == "summary_candidate_001"
                        else "综合后的统一事实摘要。"
                    ),
                }
                for candidate_id in candidate_ids
            ]
        },
        ensure_ascii=False,
    )


def _batch_character_candidate(chapter_id: str) -> dict[str, object]:
    return {
        "type": "character",
        "name": "秦阳",
        "aliases": [],
        "summary": "秦阳本章出现。",
        "source_origin": "agent_extract",
        "source_note": f"{chapter_id} 来源。",
        "evidence_excerpt": "秦阳本章出现。",
        "evidence_excerpts": ["秦阳本章出现。"],
        "first_seen_chapter_id": chapter_id,
        "last_seen_chapter_id": chapter_id,
    }


def _profile(
    model_id: str, upstream_model: str, *, is_default: bool = False
) -> LLMModelProfile:
    return LLMModelProfile(
        id=model_id,
        display_name=model_id,
        provider="rightcode",
        upstream_model=upstream_model,
        wire_protocol="openai_responses",
        enabled=True,
        is_default=is_default,
        supports_streaming=True,
        upstream_verified=True,
    )


def _general_response() -> str:
    excerpt = "秦阳握着青铜令牌走入太初教山门。"
    second_excerpt = "秦阳在山门前确认太初教规。"
    return json.dumps(
        {
            "mentions": [
                {
                    "name": "秦阳",
                    "knowledge_type": "character",
                    "description": "秦阳走入太初教山门。",
                    "evidence_excerpts": [excerpt, second_excerpt],
                    "reason": "稳定专名角色。",
                },
                {
                    "name": "太初教山门",
                    "knowledge_type": "location",
                    "description": "太初教入口地点。",
                    "evidence_excerpts": [excerpt],
                    "reason": "稳定地点名。",
                },
                {
                    "name": "太初教",
                    "knowledge_type": "faction",
                    "description": "本章出现的修行势力。",
                    "evidence_excerpts": [excerpt],
                    "reason": "稳定组织名称。",
                },
                {
                    "name": "青铜令牌",
                    "knowledge_type": "item",
                    "description": "秦阳持有的令牌。",
                    "evidence_excerpts": [excerpt],
                    "reason": "具备可追踪归属的物品。",
                },
                {
                    "name": "炼气一层",
                    "knowledge_type": "realm",
                    "description": "明确修炼层次。",
                    "evidence_excerpts": ["秦阳仍在炼气一层。"],
                    "reason": "稳定境界。",
                },
                {
                    "name": "太初引气诀",
                    "knowledge_type": "technique",
                    "description": "太初教入门功法。",
                    "evidence_excerpts": ["秦阳默诵太初引气诀。"],
                    "reason": "稳定功法名称。",
                },
                {
                    "name": "秦阳入山门",
                    "knowledge_type": "event",
                    "description": "秦阳进入太初教山门。",
                    "evidence_excerpts": [excerpt],
                    "reason": "明确剧情事件。",
                },
                {
                    "name": "持令牌方可入山",
                    "knowledge_type": "rule",
                    "description": "太初教山门通行规则。",
                    "evidence_excerpts": ["太初教规矩，持青铜令牌方可入山。"],
                    "reason": "明确规则。",
                },
            ],
            "ignored": [],
        },
        ensure_ascii=False,
    )


def _character_response() -> str:
    excerpt = "秦阳握着青铜令牌走入太初教山门。"
    return json.dumps(
        {
            "knowledge_type": "character",
            "cards": [
                {
                    "entity_group_id": "entity_group_001",
                    "name": "秦阳",
                    "aliases": [],
                    "summary": "本章走入太初教山门的人物。",
                    "source_origin": "agent_extract",
                    "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                    "evidence_excerpt": excerpt,
                    "evidence_excerpts": [excerpt, "秦阳在山门前确认太初教规。"],
                    "role_type": "protagonist",
                    "identity": "太初教弟子",
                    "relationship_summary": None,
                    "death_chapter_id": None,
                    "current_realm_text": "炼气一层",
                    "first_seen_chapter_id": "chapter_001",
                    "last_seen_chapter_id": "chapter_001",
                }
            ],
        },
        ensure_ascii=False,
    )


def _entity_response() -> str:
    excerpt = "秦阳握着青铜令牌走入太初教山门。"
    return json.dumps(
        {
            "realms": [
                {
                    "entity_group_id": "entity_group_005",
                    "name": "炼气一层",
                    "aliases": [],
                    "summary": "秦阳当前所在的早期修炼层次。",
                    "source_origin": "agent_extract",
                    "source_note": "来自章节《第一章 山门》。原文摘录：秦阳仍在炼气一层。",
                    "evidence_excerpt": "秦阳仍在炼气一层。",
                    "evidence_excerpts": ["秦阳仍在炼气一层。"],
                    "system": None,
                    "level_order": None,
                }
            ],
            "techniques": [
                {
                    "entity_group_id": "entity_group_006",
                    "name": "太初引气诀",
                    "aliases": [],
                    "summary": "太初教入门引气功法。",
                    "source_origin": "agent_extract",
                    "source_note": "来自章节《第一章 山门》。原文摘录：秦阳默诵太初引气诀。",
                    "evidence_excerpt": "秦阳默诵太初引气诀。",
                    "evidence_excerpts": ["秦阳默诵太初引气诀。"],
                    "technique_type": "cultivation_method",
                    "grade": None,
                    "practice_condition": None,
                    "owner_faction_id": None,
                }
            ],
            "locations": [
                {
                    "entity_group_id": "entity_group_002",
                    "name": "太初教山门",
                    "aliases": ["山门"],
                    "summary": "秦阳入山时出现的太初教入口。",
                    "source_origin": "agent_extract",
                    "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                    "evidence_excerpt": excerpt,
                    "evidence_excerpts": [excerpt],
                    "controlling_faction_id": None,
                    "first_seen_chapter_id": "chapter_001",
                }
            ],
            "factions": [
                {
                    "entity_group_id": "entity_group_003",
                    "name": "太初教",
                    "aliases": [],
                    "summary": "本章出现的修行势力。",
                    "source_origin": "agent_extract",
                    "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                    "evidence_excerpt": excerpt,
                    "evidence_excerpts": [excerpt],
                    "faction_type": "sect",
                    "leader_id": None,
                }
            ],
            "items": [
                {
                    "entity_group_id": "entity_group_004",
                    "name": "青铜令牌",
                    "aliases": ["令牌"],
                    "summary": "秦阳入山时持有的令牌。",
                    "source_origin": "agent_extract",
                    "source_note": f"来自章节《第一章 山门》。原文摘录：{excerpt}",
                    "evidence_excerpt": excerpt,
                    "evidence_excerpts": [excerpt],
                    "item_type": "other",
                    "grade": None,
                    "current_holder_id": None,
                    "first_seen_chapter_id": "chapter_001",
                    "last_seen_chapter_id": "chapter_001",
                }
            ],
        },
        ensure_ascii=False,
    )


def _event_rule_response() -> str:
    return json.dumps(
        {
            "events": [
                {
                    "entity_group_id": "entity_group_007",
                    "name": "秦阳入山门",
                    "aliases": [],
                    "summary": "秦阳持青铜令牌进入太初教山门。",
                    "source_origin": "agent_extract",
                    "source_note": "来自章节《第一章 山门》。原文摘录：秦阳握着青铜令牌走入太初教山门。",
                    "evidence_excerpt": "秦阳握着青铜令牌走入太初教山门。",
                    "evidence_excerpts": ["秦阳握着青铜令牌走入太初教山门。"],
                    "chapter_id": "chapter_001",
                    "description": "秦阳正式进入太初教山门。",
                }
            ],
            "rules": [
                {
                    "entity_group_id": "entity_group_008",
                    "name": "持令牌方可入山",
                    "aliases": [],
                    "summary": "太初教山门通行需要青铜令牌。",
                    "source_origin": "agent_extract",
                    "source_note": "来自章节《第一章 山门》。原文摘录：太初教规矩，持青铜令牌方可入山。",
                    "evidence_excerpt": "太初教规矩，持青铜令牌方可入山。",
                    "evidence_excerpts": ["太初教规矩，持青铜令牌方可入山。"],
                    "exceptions": None,
                }
            ],
        },
        ensure_ascii=False,
    )


def _event_rule_reuse_response() -> str:
    payload = json.loads(_event_rule_response())
    rule = payload["rules"][0]
    rule["name"] = "太初教山门通行规则"
    rule["aliases"] = ["持令牌方可入山"]
    rule["summary"] = "进入太初教山门需要持有青铜令牌。"
    return json.dumps(payload, ensure_ascii=False)


def _broken_event_rule_response() -> str:
    return _event_rule_response().replace(
        '", "evidence_excerpt":',
        '”,\n      "evidence_excerpt":',
        1,
    )


def _generic_mentions_response() -> str:
    return json.dumps(
        {
            "mentions": [
                {
                    "name": "小山羊胡子",
                    "knowledge_type": "character",
                    "description": "只有外貌特征的临时称呼。",
                    "evidence_excerpts": ["小山羊胡子在旁边看了一眼。"],
                    "reason": "临时称呼",
                },
                {
                    "name": "少年们",
                    "knowledge_type": "character",
                    "description": "普通人群泛称。",
                    "evidence_excerpts": ["少年们围在药铺门口。"],
                    "reason": "泛称",
                },
                {
                    "name": "药铺门口",
                    "knowledge_type": "location",
                    "description": "普通功能空间。",
                    "evidence_excerpts": ["少年们围在药铺门口。"],
                    "reason": "普通地点",
                },
            ],
            "ignored": [],
        },
        ensure_ascii=False,
    )
