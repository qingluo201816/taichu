"""Application-service tests for knowledge-extraction effect evaluation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

from taichu.application.agents.models.agent_run import (
    AgentReviewCandidateAction,
    AgentReviewItem,
    AgentRun,
    AgentRunScope,
    AgentRunStatus,
)
from taichu.application.contracts.evaluation_judge import EvaluationJudgeResponse
from taichu.application.contracts.llm import LLMModelIdentity
from taichu.application.evaluations.knowledge_extraction.dataset import (
    DatasetValidationResult,
    EvaluationDatasetSummary,
    LoadedEvaluationCase,
    LoadedEvaluationDataset,
)
from taichu.application.evaluations.knowledge_extraction.models import (
    AmbiguousMatch,
    CandidateMatchResult,
    CandidateRef,
    DatasetManifest,
    EvaluationCaseRef,
    EvaluationLifecycle,
    EvaluationRules,
    EvaluationScopeType,
    ExpectedCard,
    SourceEvidence,
)
from taichu.application.evaluations.knowledge_extraction.records import (
    EvaluationComparison,
    EvaluationStatus,
    IndependenceLevel,
    JudgeCallRecord,
    KnowledgeEvaluationRecord,
)
from taichu.application.services.knowledge_extraction_evaluation_service import (
    EvaluationServiceError,
    KnowledgeExtractionEvaluationService,
    _actual_candidates,
    _background_failure,
    _build_comparisons,
    _comparison_issue_type,
    _display_model_title,
    _judge_failure_code,
    _legacy_judge_diagnostics,
    derive_independence,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType
from taichu.infrastructure.evaluations.json_result_store import (
    JsonEvaluationResultStore,
)


class _DatasetRepository:
    def __init__(self, dataset: LoadedEvaluationDataset) -> None:
        self.dataset = dataset

    async def list_datasets(
        self,
        *,
        include_non_confirmed: bool = False,
    ) -> list[EvaluationDatasetSummary]:
        return [
            EvaluationDatasetSummary(
                dataset_id=self.dataset.manifest.dataset_id,
                label=self.dataset.manifest.label,
                lifecycle=EvaluationLifecycle.CONFIRMED,
                case_count=1,
                valid=True,
                checksum=self.dataset.checksum,
            )
        ]

    async def validate_dataset(self, dataset_id: str) -> DatasetValidationResult:
        return DatasetValidationResult(
            dataset_id=dataset_id,
            valid=True,
            lifecycle=EvaluationLifecycle.CONFIRMED,
            checksum=self.dataset.checksum,
        )

    async def get_dataset(self, dataset_id: str) -> LoadedEvaluationDataset:
        assert dataset_id == self.dataset.manifest.dataset_id
        return self.dataset


class _RunStore:
    def __init__(self, runs: list[AgentRun]) -> None:
        self.runs = {run.run_id: run for run in runs}

    async def write_run(self, run: AgentRun) -> AgentRun:
        self.runs[run.run_id] = run
        return run

    async def get_run(self, run_id: str) -> AgentRun | None:
        return self.runs.get(run_id)

    async def delete_run(self, run_id: str) -> bool:
        return self.runs.pop(run_id, None) is not None

    async def list_runs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[list[AgentRun], int]:
        values = list(self.runs.values())
        start = (page - 1) * page_size
        return values[start : start + page_size], len(values)

    async def find_run_for_candidate(self, candidate_id: str) -> AgentRun | None:
        return next(
            (
                run
                for run in self.runs.values()
                if any(item.review_item_id == candidate_id for item in run.review_items)
            ),
            None,
        )


class _ChapterService:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown

    async def read_chapter(self, chapter_id: str) -> SimpleNamespace:
        assert chapter_id == "chapter-001"
        return SimpleNamespace(markdown=self.markdown)


class _Judge:
    def __init__(self, *, available: bool) -> None:
        self._available = available
        self.calls = 0
        self._identity = LLMModelIdentity(
            provider="deepseek",
            model_id="judge-model",
            family="judge",
            endpoint_kind="openai_compatible",
            known=True,
        )

    @property
    def available(self) -> bool:
        return self._available

    @property
    def model_identity(self) -> LLMModelIdentity:
        return self._identity

    async def complete(
        self,
        prompt: str,
        *,
        output_schema: type[BaseModel],
    ) -> EvaluationJudgeResponse:
        self.calls += 1
        raise AssertionError("本测试不应调用语义裁判")


class _SuccessfulJudge(_Judge):
    async def complete(
        self,
        prompt: str,
        *,
        output_schema: type[BaseModel],
    ) -> EvaluationJudgeResponse:
        assert output_schema.__name__ == "JudgeBatchOutput"
        self.calls += 1
        encoded = prompt.split("<UNTRUSTED_EVALUATION_DATA>\n", 1)[1].split(
            "\n</UNTRUSTED_EVALUATION_DATA>",
            1,
        )[0]
        cases = json.loads(encoded)
        dimensions = {
            name: {
                "score": 4,
                "verdict": "equivalent",
                "quote_ids": [],
                "reason": "候选内容与正文和期望一致。",
            }
            for name in (
                "factual_fidelity",
                "key_fact_coverage",
                "evidence_grounding",
                "scope_discipline",
                "knowledge_usability",
            )
        }
        output = output_schema.model_validate(
            {
                "items": [
                    {
                        "case_id": item["case_id"],
                        "expected_card_id": item["expected_card_id"],
                        "actual_review_item_id": item["actual_review_item_id"],
                        "status": "scored",
                        "dimensions": dimensions,
                        "findings": [],
                        "critical_flags": [],
                        "reference_issues": [],
                        "missing_quote_ids": [],
                        "confidence": 0.95,
                        "reason": None,
                    }
                    for item in cases
                ]
            }
        )
        return EvaluationJudgeResponse(
            output=output,
            raw_response="opaque structured-output audit payload",
            model_identity=self.model_identity,
        )


class _DifferenceJudge(_SuccessfulJudge):
    async def complete(
        self,
        prompt: str,
        *,
        output_schema: type[BaseModel],
    ) -> EvaluationJudgeResponse:
        if "<UNTRUSTED_DIFFERENCE_DATA>" in prompt:
            assert output_schema.__name__ == "DifferenceExplanationBatchOutput"
            self.calls += 1
            encoded = prompt.split("<UNTRUSTED_DIFFERENCE_DATA>\n", 1)[1].split(
                "\n</UNTRUSTED_DIFFERENCE_DATA>",
                1,
            )[0]
            cases = json.loads(encoded)
            output = output_schema.model_validate(
                {
                    "items": [
                        {
                            "explanation_id": item["explanation_id"],
                            "summary": (
                                "已匹配为同一张角色卡，但本次摘要对关键事实的"
                                "覆盖不完整。"
                            ),
                        }
                        for item in cases
                    ]
                }
            )
            return EvaluationJudgeResponse(
                output=output,
                raw_response="opaque difference-output audit payload",
                model_identity=self.model_identity,
            )
        response = await super().complete(
            prompt,
            output_schema=output_schema,
        )
        payload = response.output.model_dump(mode="json")
        for item in payload["items"]:
            dimension = item["dimensions"]["key_fact_coverage"]
            dimension["score"] = 3
            dimension["verdict"] = "mostly_correct"
            dimension["reason"] = "候选覆盖主要事实，但仍有细节遗漏。"
        return response.model_copy(
            update={"output": output_schema.model_validate(payload)}
        )


def test_preview_and_deterministic_background_use_frozen_inputs(
    tmp_path: Path,
) -> None:
    asyncio.run(_preview_and_background_scenario(tmp_path))


def test_background_failure_does_not_misreport_internal_error_as_corruption() -> None:
    code, message = _background_failure(PermissionError("sharing violation"))

    assert code == "EVALUATION_EXECUTION_FAILED"
    assert "后台执行失败" in message


def test_update_candidate_is_fully_evaluable(tmp_path: Path) -> None:
    asyncio.run(_update_candidate_preview_scenario(tmp_path))


async def _update_candidate_preview_scenario(tmp_path: Path) -> None:
    markdown = "秦阳握着青铜令牌走入山门。"
    dataset = _dataset(markdown)
    run = _run(markdown, action=AgentReviewCandidateAction.UPDATE_CARD)
    service = KnowledgeExtractionEvaluationService(
        dataset_repository=_DatasetRepository(dataset),
        result_repository=JsonEvaluationResultStore(tmp_path),
        run_store=_RunStore([run]),
        chapter_service=_ChapterService(markdown),  # type: ignore[arg-type]
        judge=_SuccessfulJudge(available=True),
    )

    preview = await service.preview(
        dataset_id=dataset.manifest.dataset_id,
        run_ids=[run.run_id],
        judge_enabled=True,
        metric_profile_id="knowledge_extraction_balanced",
    )

    assert preview["can_create"] is True
    assert preview["has_diagnostic_runs"] is False
    assert preview["warnings"] == []
    assert preview["runs"][0]["eligibility_level"] == "full"
    assert preview["estimate"]["matched_card_count"] == 1
    assert preview["estimate"]["judge_card_count"] == 1


async def _preview_and_background_scenario(tmp_path: Path) -> None:
    markdown = "秦阳握着青铜令牌走入山门。"
    dataset = _dataset(markdown)
    run = _run(markdown)
    results = JsonEvaluationResultStore(tmp_path)
    service = KnowledgeExtractionEvaluationService(
        dataset_repository=_DatasetRepository(dataset),
        result_repository=results,
        run_store=_RunStore([run]),
        chapter_service=_ChapterService(markdown),  # type: ignore[arg-type]
        judge=_Judge(available=False),
    )

    preview = await service.preview(
        dataset_id=dataset.manifest.dataset_id,
        run_ids=[run.run_id],
        judge_enabled=False,
        metric_profile_id="knowledge_extraction_balanced",
    )
    created = await service.create_evaluation(
        dataset_id=dataset.manifest.dataset_id,
        run_ids=[run.run_id],
        judge_enabled=False,
        metric_profile_id="knowledge_extraction_balanced",
    )
    completed = await _wait_for_terminal(results, created.evaluation_id)

    assert preview["can_create"] is True
    assert preview["estimate"]["matched_card_count"] == 1
    assert preview["estimate"]["judge_card_count"] == 0
    assert completed.status is EvaluationStatus.COMPLETED
    assert completed.progress.run_completed == 1
    assert completed.progress.judge_card_total == 0
    assert completed.run_results[0].metrics["candidate_f1_micro"] == 1
    assert completed.run_results[0].metrics["evidence_score"] == 1
    assert completed.run_results[0].overall_quality_score is None
    assert completed.run_results[0].final_quality_state.value == "not_comparable"
    persisted = await results.get_run_result(created.evaluation_id, run.run_id)
    assert persisted is not None
    assert (
        persisted.metrics["candidate_f1_micro"]
        == completed.run_results[0].metrics["candidate_f1_micro"]
    )
    assert "structured_fields" in persisted.metrics
    assert "structured_fields" not in completed.run_results[0].metrics
    assert persisted.comparisons
    assert completed.run_results[0].comparisons == []
    snapshot = await results.read_snapshot_files(created.evaluation_id)
    assert snapshot["chapters/chapter-001.md"].decode() == markdown
    assert "output_schema" in snapshot["judge_contract.json"].decode()
    await service.shutdown()


def test_judge_unavailable_is_preview_blocker_and_create_503_contract(
    tmp_path: Path,
) -> None:
    asyncio.run(_judge_unavailable_scenario(tmp_path))


async def _judge_unavailable_scenario(tmp_path: Path) -> None:
    markdown = "秦阳握着青铜令牌走入山门。"
    dataset = _dataset(markdown)
    run = _run(markdown)
    service = KnowledgeExtractionEvaluationService(
        dataset_repository=_DatasetRepository(dataset),
        result_repository=JsonEvaluationResultStore(tmp_path),
        run_store=_RunStore([run]),
        chapter_service=_ChapterService(markdown),  # type: ignore[arg-type]
        judge=_Judge(available=False),
    )

    preview = await service.preview(
        dataset_id=dataset.manifest.dataset_id,
        run_ids=[run.run_id],
        judge_enabled=True,
        metric_profile_id="knowledge_extraction_balanced",
    )

    assert preview["can_create"] is False
    assert preview["judge"]["available"] is False
    caught: EvaluationServiceError | None = None
    try:
        await service.create_evaluation(
            dataset_id=dataset.manifest.dataset_id,
            run_ids=[run.run_id],
            judge_enabled=True,
            metric_profile_id="knowledge_extraction_balanced",
        )
    except EvaluationServiceError as error:
        caught = error
    assert caught is not None
    assert caught.code == "EVALUATION_JUDGE_UNAVAILABLE"


def test_freeze_rechecks_markdown_after_dataset_loading(tmp_path: Path) -> None:
    asyncio.run(_freeze_recheck_scenario(tmp_path))


async def _freeze_recheck_scenario(tmp_path: Path) -> None:
    expected = "秦阳握着青铜令牌走入山门。"
    changed = "正文在评测集加载后发生变化。"
    dataset = _dataset(expected)
    service = KnowledgeExtractionEvaluationService(
        dataset_repository=_DatasetRepository(dataset),
        result_repository=JsonEvaluationResultStore(tmp_path),
        run_store=_RunStore([_run(expected)]),
        chapter_service=_ChapterService(changed),  # type: ignore[arg-type]
        judge=_Judge(available=False),
    )

    caught: EvaluationServiceError | None = None
    try:
        await service.preview(
            dataset_id=dataset.manifest.dataset_id,
            run_ids=[_run(expected).run_id],
            judge_enabled=False,
            metric_profile_id="knowledge_extraction_balanced",
        )
    except EvaluationServiceError as error:
        caught = error
    assert caught is not None
    assert caught.code == "EVALUATION_SOURCE_CHANGED"


def test_judge_failure_degrades_and_retry_reuses_parent_snapshot(
    tmp_path: Path,
) -> None:
    asyncio.run(_judge_failure_and_retry_scenario(tmp_path))


async def _judge_failure_and_retry_scenario(tmp_path: Path) -> None:
    markdown = "秦阳握着青铜令牌走入山门。"
    dataset = _dataset(markdown)
    run = _run(markdown)
    results = JsonEvaluationResultStore(tmp_path)
    chapters = _ChapterService(markdown)
    judge = _Judge(available=True)
    service = KnowledgeExtractionEvaluationService(
        dataset_repository=_DatasetRepository(dataset),
        result_repository=results,
        run_store=_RunStore([run]),
        chapter_service=chapters,  # type: ignore[arg-type]
        judge=judge,
    )

    parent = await service.create_evaluation(
        dataset_id=dataset.manifest.dataset_id,
        run_ids=[run.run_id],
        judge_enabled=True,
        metric_profile_id="knowledge_extraction_balanced",
    )
    parent_terminal = await _wait_for_terminal(results, parent.evaluation_id)
    parent_result = await results.get_run_result(parent.evaluation_id, run.run_id)
    parent_snapshot = await results.read_snapshot_files(parent.evaluation_id)
    chapters.markdown = "当前正文已经变化，但严格重试不得重新读取。"

    retried = await service.retry_evaluation(parent.evaluation_id)
    retry_terminal = await _wait_for_terminal(results, retried.evaluation_id)
    retry_snapshot = await results.read_snapshot_files(retried.evaluation_id)

    assert parent_terminal.status is EvaluationStatus.COMPLETED_WITH_WARNINGS
    assert parent_terminal.progress.judge_card_completed == 1
    assert parent_terminal.progress.judge_batch_completed == 1
    assert parent_terminal.run_results[0].metrics["candidate_f1_micro"] == 1
    assert parent_terminal.run_results[0].overall_quality_score is None
    assert parent_terminal.warnings[0].code == "EVALUATION_JUDGE_INVALID_OUTPUT"
    assert "语义裁判未纳入本次评分" in parent_terminal.warnings[0].message
    assert parent_result is not None
    assert parent_result.comparisons[0].issue_type == "judge_failed"
    judge_result = parent_result.comparisons[0].judge_result
    assert judge_result is not None
    failed_call = await results.get_judge_call(
        parent.evaluation_id,
        judge_result["judge_call_ids"][0],
    )
    assert failed_call is not None
    assert failed_call.error_code == "judge_provider_error"
    assert parent_result.comparisons[0].explanation is not None
    assert parent_result.comparisons[0].explanation.source.value == "rule"
    assert "不代表抽取错误" in parent_result.comparisons[0].explanation.summary
    assert retry_terminal.status is EvaluationStatus.COMPLETED_WITH_WARNINGS
    assert retry_terminal.parent_evaluation_id == parent.evaluation_id
    assert retry_terminal.snapshot_root_hash == parent_terminal.snapshot_root_hash
    assert retry_snapshot == parent_snapshot
    # 每次评估包含一次失败的语义裁判和一次失败的差异说明调用。
    assert judge.calls == 4
    await service.shutdown()


def test_model_independence_uses_real_provider_model_and_family() -> None:
    generation = LLMModelIdentity(
        provider="deepseek",
        model_id="deepseek-chat",
        family="deepseek-v4",
        endpoint_kind="openai_compatible",
        known=True,
    )
    same_family = generation.model_copy(update={"model_id": "deepseek-reasoner"})
    different = generation.model_copy(
        update={"provider": "openai", "model_id": "gpt-x", "family": "gpt"}
    )

    assert derive_independence(generation, generation).value == "same_model"
    assert derive_independence(generation, same_family).value == "same_provider_family"
    assert derive_independence(generation, different).value == "different_model"
    assert (
        derive_independence(
            generation,
            LLMModelIdentity.unknown("测试未知身份。"),
        ).value
        == "unknown"
    )


def test_update_candidates_are_evaluated_after_schema_merge_preview() -> None:
    markdown = "秦阳握着青铜令牌走入山门。"
    run = _run(markdown, action=AgentReviewCandidateAction.UPDATE_CARD)
    review_item = run.review_items[0].model_copy(
        update={
            "target_card_id": "character-qinyang",
            "suggested_card": {
                **run.review_items[0].suggested_card,
                "aliases": ["新别名"],
                "summary": "秦阳带着青铜令牌进入山门。",
                "role_type": "antagonist",
                "last_seen_chapter_id": "chapter-002",
            },
        }
    )
    run = run.model_copy(
        update={
            "review_items": [review_item],
            "typed_candidates": [
                {
                    "type": "character",
                    "name": "秦阳",
                    "target_card_id": "character-qinyang",
                    "_existing_card": {
                        "type": "character",
                        "name": "秦阳",
                        "aliases": ["旧别名"],
                        "summary": "秦阳原本是山下少年。",
                        "role_type": "supporting",
                        "last_seen_chapter_id": "chapter-001",
                    },
                }
            ],
        }
    )

    candidate = _actual_candidates(run)[0]

    assert candidate.merge_preview_applied is True
    assert candidate.card["summary"] == "秦阳带着青铜令牌进入山门。"
    assert candidate.card["aliases"] == ["旧别名", "新别名"]
    assert candidate.card["role_type"] == "supporting"
    assert candidate.card["last_seen_chapter_id"] == "chapter-002"


def test_judge_failure_code_distinguishes_timeout_protocol_and_provider() -> None:
    assert _judge_failure_code(asyncio.TimeoutError()) == "judge_timeout"
    assert _judge_failure_code(json.JSONDecodeError("坏 JSON", "", 0)) == (
        "judge_protocol_invalid_json"
    )
    assert _judge_failure_code(RuntimeError("连接中断")) == "judge_provider_error"


def test_display_model_title_uses_frozen_author_facing_name() -> None:
    run = _run("秦阳握着青铜令牌走入山门。").model_copy(
        update={
            "model_name": "Claude Sonnet 5",
            "requested_model_name": "claude-sonnet-5",
            "model_id": "claude-sonnet-5",
            "model_display_name": "Claude Sonnet 5",
            "upstream_model": "claude-sonnet-5",
            "generation_model_identity": LLMModelIdentity(
                provider="rightcode",
                model_id="claude-sonnet-5",
                family="claude-sonnet",
                endpoint_kind="anthropic_messages",
                known=True,
            ),
        }
    )

    assert _display_model_title(run) == "Claude Sonnet 5"
    assert (
        _display_model_title(
            run.model_copy(
                update={
                    "model_name": "claude-sonnet-5",
                    "model_display_name": "claude-sonnet-5",
                }
            )
        )
        == "模型信息未记录"
    )


def test_comparison_issue_type_only_reports_real_differences() -> None:
    exact_match = EvaluationComparison(
        run_id="extract_run_20260711_120000_a1b2c3",
        case_id="chapter-001",
        knowledge_type="character",
        issue_type="field_difference",
        expected_card_id="expected-001",
        actual_candidate_id="actual-001",
    )
    field_difference = exact_match.model_copy(
        update={
            "field_diffs": [
                {
                    "field_name": "aliases",
                    "expected_value": ["阿阳"],
                    "actual_value": [],
                }
            ]
        }
    )
    semantic_issue = exact_match.model_copy(
        update={
            "judge_result": {
                "status": "scored",
                "dimensions": {
                    "key_fact_coverage": {"score": 2},
                    "evidence_grounding": {"score": 4},
                },
            }
        }
    )
    evidence_issue = exact_match.model_copy(
        update={
            "judge_result": {
                "status": "scored",
                "dimensions": {"evidence_grounding": {"score": 3}},
            }
        }
    )
    judge_disagreement = exact_match.model_copy(
        update={"judge_result": {"status": "reference_conflict"}}
    )
    judge_inconclusive = exact_match.model_copy(
        update={"judge_result": {"status": "inconclusive"}}
    )
    judge_failed = exact_match.model_copy(update={"judge_result": {"status": "failed"}})
    ambiguous_match = exact_match.model_copy(update={"issue_type": "ambiguous_match"})

    assert _comparison_issue_type(exact_match) is None
    assert _comparison_issue_type(field_difference) == "field_difference"
    assert _comparison_issue_type(semantic_issue) == "semantic_issue"
    assert _comparison_issue_type(evidence_issue) == "evidence_issue"
    assert _comparison_issue_type(judge_disagreement) == "judge_disagreement"
    assert _comparison_issue_type(judge_inconclusive) == "judge_inconclusive"
    assert _comparison_issue_type(judge_failed) == "judge_failed"
    assert _comparison_issue_type(ambiguous_match) == "ambiguous_match"


def test_legacy_judge_diagnostics_distinguishes_failed_and_inconclusive() -> None:
    comparison = EvaluationComparison(
        run_id="extract_run_20260711_120000_a1b2c3",
        case_id="chapter-001",
        knowledge_type="character",
        issue_type="judge_disagreement",
        expected_card_id="expected-001",
        actual_candidate_id="actual-001",
        judge_result={
            "status": "disagreement",
            "judge_call_ids": ["call-1", "call-2"],
        },
    )
    valid_item = {
        "expected_card_id": "expected-001",
        "actual_review_item_id": "actual-001",
    }
    valid_call = JudgeCallRecord(
        call_id="call-1",
        evaluation_id="evaluation-001",
        run_ids=[comparison.run_id],
        judge_model_identity=LLMModelIdentity(
            provider="deepseek",
            model_id="judge-model",
            family="judge",
            endpoint_kind="openai_compatible",
            known=True,
        ),
        independence_level=IndependenceLevel.DIFFERENT_MODEL,
        prompt_contract_id="knowledge_extraction_semantic_judge",
        prompt_hash="prompt-hash",
        input_snapshot_hash="snapshot-hash",
        input_prompt="prompt",
        parsed_output={"items": [valid_item]},
        started_at="2026-07-13T00:00:00Z",
    )

    failed = _legacy_judge_diagnostics(comparison, [], 2)
    inconclusive = _legacy_judge_diagnostics(comparison, [valid_call], 2)
    disagreement = _legacy_judge_diagnostics(
        comparison,
        [valid_call, valid_call.model_copy(update={"call_id": "call-2"})],
        2,
    )

    assert failed["status"] == "failed"
    assert failed["valid_result_count"] == 0
    assert "不代表抽取错误" in failed["reason"]
    assert inconclusive["status"] == "inconclusive"
    assert inconclusive["valid_result_count"] == 1
    assert disagreement["status"] == "disagreement"
    assert disagreement["valid_result_count"] == 2


def test_ambiguous_match_is_one_review_item_without_missing_or_extra_rows() -> None:
    matches = CandidateMatchResult(
        ambiguities=[
            AmbiguousMatch(
                knowledge_type=StructuredKnowledgeType.EVENT,
                weight=80,
                actual_candidates=[
                    CandidateRef(
                        card_id="actual-001",
                        knowledge_type=StructuredKnowledgeType.EVENT,
                        name="秦浩轩制止张狂殴打少年",
                    )
                ],
                expected_cards=[
                    CandidateRef(
                        card_id="expected-001",
                        knowledge_type=StructuredKnowledgeType.EVENT,
                        name="秦浩轩喝止张狂欺凌少年",
                    ),
                    CandidateRef(
                        card_id="expected-002",
                        knowledge_type=StructuredKnowledgeType.EVENT,
                        name="秦浩轩再次阻止张狂",
                    ),
                ],
                normalized_keys=["event-semantic:test"],
            )
        ]
    )

    comparisons = _build_comparisons(
        "extract_run_20260711_120000_a1b2c3",
        "chapter-001",
        "第一章",
        matches,
        [],
        [],
        [],
    )

    assert len(comparisons) == 1
    assert comparisons[0].issue_type == "ambiguous_match"
    assert comparisons[0].match_kind == "ambiguous_match"
    assert comparisons[0].judge_result is not None
    assert "漏提取和多提取计数中排除" in comparisons[0].judge_result["reason"]


def test_successful_judge_persists_auditable_call_and_semantic_result(
    tmp_path: Path,
) -> None:
    asyncio.run(_successful_judge_scenario(tmp_path))


def test_visible_difference_gets_persisted_model_explanation(tmp_path: Path) -> None:
    asyncio.run(_model_explanation_scenario(tmp_path))


async def _successful_judge_scenario(tmp_path: Path) -> None:
    markdown = "秦阳握着青铜令牌走入山门。"
    dataset = _dataset(markdown)
    run = _run(markdown)
    results = JsonEvaluationResultStore(tmp_path)
    judge = _SuccessfulJudge(available=True)
    service = KnowledgeExtractionEvaluationService(
        dataset_repository=_DatasetRepository(dataset),
        result_repository=results,
        run_store=_RunStore([run]),
        chapter_service=_ChapterService(markdown),  # type: ignore[arg-type]
        judge=judge,
    )

    created = await service.create_evaluation(
        dataset_id=dataset.manifest.dataset_id,
        run_ids=[run.run_id],
        judge_enabled=True,
        metric_profile_id="knowledge_extraction_balanced",
    )
    terminal = await _wait_for_terminal(results, created.evaluation_id)
    persisted = await results.get_run_result(created.evaluation_id, run.run_id)

    assert terminal.status is EvaluationStatus.COMPLETED
    assert terminal.run_results[0].semantic_score == 1
    assert persisted is not None
    judge_result = persisted.comparisons[0].judge_result
    assert judge_result is not None
    call_id = judge_result["judge_call_ids"][0]
    call = await results.get_judge_call(created.evaluation_id, call_id)
    assert call is not None
    assert call.self_judge is False
    assert call.input_snapshot_hash != terminal.snapshot_root_hash
    assert call.parsed_output is not None
    await service.shutdown()


async def _model_explanation_scenario(tmp_path: Path) -> None:
    markdown = "秦阳握着青铜令牌走入山门。"
    dataset = _dataset(markdown)
    run = _run(markdown)
    results = JsonEvaluationResultStore(tmp_path)
    judge = _DifferenceJudge(available=True)
    service = KnowledgeExtractionEvaluationService(
        dataset_repository=_DatasetRepository(dataset),
        result_repository=results,
        run_store=_RunStore([run]),
        chapter_service=_ChapterService(markdown),  # type: ignore[arg-type]
        judge=judge,
    )

    created = await service.create_evaluation(
        dataset_id=dataset.manifest.dataset_id,
        run_ids=[run.run_id],
        judge_enabled=True,
        metric_profile_id="knowledge_extraction_balanced",
    )
    terminal = await _wait_for_terminal(results, created.evaluation_id)
    persisted = await results.get_run_result(created.evaluation_id, run.run_id)

    assert terminal.status is EvaluationStatus.COMPLETED
    assert persisted is not None
    comparison = persisted.comparisons[0]
    assert comparison.issue_type == "semantic_issue"
    assert comparison.explanation is not None
    assert comparison.explanation.source.value == "model"
    assert "覆盖不完整" in comparison.explanation.summary
    assert comparison.explanation.call_id
    explanation_call = await results.get_judge_call(
        created.evaluation_id,
        comparison.explanation.call_id,
    )
    assert explanation_call is not None
    assert (
        explanation_call.prompt_contract_id
        == "knowledge_extraction_difference_explanation"
    )
    assert judge.calls == 2
    await service.shutdown()


def test_active_fingerprint_and_startup_recovery_are_terminal_safe(
    tmp_path: Path,
) -> None:
    asyncio.run(_active_fingerprint_and_recovery_scenario(tmp_path))


async def _active_fingerprint_and_recovery_scenario(tmp_path: Path) -> None:
    markdown = "秦阳握着青铜令牌走入山门。"
    dataset = _dataset(markdown)
    run = _run(markdown)
    results = JsonEvaluationResultStore(tmp_path)
    gate = asyncio.Event()

    def gated_task(work: Awaitable[None]) -> asyncio.Task[None]:
        async def wait_then_run() -> None:
            await gate.wait()
            await work

        return asyncio.create_task(wait_then_run())

    service = KnowledgeExtractionEvaluationService(
        dataset_repository=_DatasetRepository(dataset),
        result_repository=results,
        run_store=_RunStore([run]),
        chapter_service=_ChapterService(markdown),  # type: ignore[arg-type]
        judge=_Judge(available=False),
        task_factory=gated_task,
    )
    first = await service.create_evaluation(
        dataset_id=dataset.manifest.dataset_id,
        run_ids=[run.run_id],
        judge_enabled=False,
        metric_profile_id="knowledge_extraction_balanced",
    )
    duplicate_error: Exception | None = None
    try:
        await service.create_evaluation(
            dataset_id=dataset.manifest.dataset_id,
            run_ids=[run.run_id],
            judge_enabled=False,
            metric_profile_id="knowledge_extraction_balanced",
        )
    except Exception as error:  # persistence exposes its stable code boundary
        duplicate_error = error

    assert duplicate_error is not None
    assert getattr(duplicate_error, "code", None) == "EVALUATION_ALREADY_RUNNING"
    await service.recover_interrupted()
    recovered = await results.get_record(first.evaluation_id)
    assert recovered is not None
    assert recovered.status is EvaluationStatus.FAILED
    assert recovered.error_code == "EVALUATION_PROCESS_INTERRUPTED"

    gate.set()
    await asyncio.sleep(0.05)
    unchanged = await results.get_record(first.evaluation_id)
    assert unchanged is not None
    assert unchanged.status is EvaluationStatus.FAILED
    assert unchanged.finished_at == recovered.finished_at
    await service.shutdown()


async def _wait_for_terminal(
    repository: JsonEvaluationResultStore,
    evaluation_id: str,
) -> KnowledgeEvaluationRecord:
    for _ in range(200):
        record = await repository.get_record(evaluation_id)
        assert record is not None
        if record.is_terminal:
            return record
        await asyncio.sleep(0.01)
    raise AssertionError("后台评估未在测试时限内结束")


def _dataset(markdown: str) -> LoadedEvaluationDataset:
    source_hash = sha256(markdown.encode()).hexdigest()
    quote = "秦阳握着青铜令牌走入山门。"
    case_ref = EvaluationCaseRef(
        case_id="chapter-001",
        scope_type=EvaluationScopeType.CHAPTER,
        chapter_ids=["chapter-001"],
        source_chapter_hashes={"chapter-001": source_hash},
        expected_cards_path="chapter-001/expected.json",
        evaluation_rules_path="chapter-001/rules.json",
        source_evidence_path="chapter-001/evidence.json",
        negative_cases_path="chapter-001/negative.json",
    )
    expected = ExpectedCard(
        expected_card_id="character-qinyang",
        knowledge_type=StructuredKnowledgeType.CHARACTER,
        card={
            "type": "character",
            "name": "秦阳",
            "aliases": [],
            "appearance_chapter_count": 1,
            "summary": "秦阳走入山门。",
        },
        accepted_names=[],
        exact_fields=["appearance_chapter_count"],
        set_fields=["aliases"],
        semantic_fields=["summary"],
        expected_claims=[],
        source_quote_ids=["quote-qinyang"],
    )
    evidence = SourceEvidence(
        quote_id="quote-qinyang",
        chapter_id="chapter-001",
        text=quote,
        start_offset=0,
        end_offset=len(quote),
        source_hash=source_hash,
    )
    loaded_case = LoadedEvaluationCase(
        ref=case_ref,
        expected_cards=[expected],
        rules=EvaluationRules(),
        source_evidence=[evidence],
        negative_cases=[],
        checksum="case-checksum",
    )
    manifest = DatasetManifest(
        dataset_id="service_test_dataset",
        label="服务测试评测集",
        lifecycle=EvaluationLifecycle.CONFIRMED,
        agent_name="knowledge_extraction",
        schema_snapshot_path="schema.json",
        checksum_manifest_path="checksums.json",
        cases=[case_ref],
    )
    return LoadedEvaluationDataset(
        manifest=manifest,
        cases={case_ref.case_id: loaded_case},
        checksum="dataset-checksum",
    )


def _run(
    markdown: str,
    *,
    action: AgentReviewCandidateAction = AgentReviewCandidateAction.CREATE_CARD,
) -> AgentRun:
    run_id = "extract_run_20260711_120000_a1b2c3"
    source_hash = sha256(markdown.encode()).hexdigest()
    now = "2026-07-11T12:00:00Z"
    return AgentRun(
        run_id=run_id,
        status=AgentRunStatus.COMPLETED,
        scope=AgentRunScope(
            scope_type="chapter",
            chapter_id="chapter-001",
            chapter_title="第一章",
            content_hash=source_hash,
        ),
        started_at=now,
        finished_at=now,
        generation_model_identity=LLMModelIdentity(
            provider="deepseek",
            model_id="generation-model",
            family="generation",
            endpoint_kind="openai_compatible",
            known=True,
        ),
        review_items=[
            AgentReviewItem(
                review_item_id="review-qinyang",
                run_id=run_id,
                candidate_action=action,
                knowledge_type=StructuredKnowledgeType.CHARACTER,
                display_title="秦阳",
                suggested_card={
                    "type": "character",
                    "name": "秦阳",
                    "aliases": [],
                    "appearance_chapter_count": 1,
                    "summary": "秦阳走入山门。",
                    "evidence_excerpt": markdown,
                },
                source_excerpt=markdown,
                created_at=now,
                updated_at=now,
            )
        ],
    )
