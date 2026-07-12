"""MVP first-version data contract tests."""

import unittest
from typing import Any, cast

from pydantic import ValidationError

from taichu.domain.models import (
    EditorBackground,
    EditorFontStyle,
    EditorPreferences,
    MVPInboxIdea,
    MVPInboxIssue,
    MVPInboxPendingFact,
    MVPInboxPriority,
    MVPInboxStatus,
    OutlineChapter,
    OutlineVolume,
    SourceReference,
    SourceReferenceType,
    StructuredKnowledgeCard,
    StructuredKnowledgeImportance,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
    WritingAIButtonType,
    WritingAIInput,
    WritingAIOutputType,
    WritingAIPromptSnapshot,
    WritingAIReferenceScope,
    WritingAIRetrievalContext,
    WritingAIRetrievalEvidenceItem,
    WritingAIRun,
    WritingAIRunStatus,
    WritingAIStructuredOutput,
    WritingOutline,
    knowledge_type_schema,
)


NOW = "2026-06-30T12:00:00+09:00"


class MVPContractTest(unittest.TestCase):
    """Verify the MVP data objects required by Phase 1."""

    def test_outline_uses_volume_and_chapter_stable_ids(self) -> None:
        outline = WritingOutline(
            volumes=[
                OutlineVolume(
                    volume_id="volume-001",
                    name="第一卷 大田初醒",
                    order=1,
                    chapters=[
                        OutlineChapter(
                            chapter_id="chapter-001",
                            display_title="第1章 大田金鳞元神出",
                            order=1,
                            markdown_path=(
                                "manuscripts/chapters/volume-001/chapter-001.md"
                            ),
                        )
                    ],
                )
            ],
            current_volume_id="volume-001",
            current_chapter_id="chapter-001",
            updated_at=NOW,
        )

        self.assertEqual(outline.volumes[0].volume_id, "volume-001")
        self.assertEqual(outline.volumes[0].chapters[0].display_title, "第1章 大田金鳞元神出")

    def test_source_reference_limits_excerpt_and_requires_author_note_body(self) -> None:
        source_ref = SourceReference(
            source_type=SourceReferenceType.AUTHOR_NOTE,
            source_id="author-note-001",
            display_name="作者说明：金鳞异象",
            excerpt="金鳞异象暂定为元神外显。",
            note="作者手动说明。",
            author_note_body="金鳞异象暂定为元神外显，不等于完整境界。",
        )

        self.assertEqual(source_ref.source_type, SourceReferenceType.AUTHOR_NOTE)
        with self.assertRaises(ValidationError):
            SourceReference(
                source_type=SourceReferenceType.AUTHOR_NOTE,
                source_id="author-note-002",
                display_name="作者说明：缺少正文",
                excerpt="缺少正文。",
            )
        with self.assertRaises(ValidationError):
            SourceReference(
                source_type=SourceReferenceType.CHAPTER,
                source_id="chapter-001",
                display_name="第1章",
                excerpt="甲" * 301,
            )

    def test_structured_knowledge_card_supports_character_fields(self) -> None:
        card = StructuredKnowledgeCard(
            id="character-qin-yang",
            type=StructuredKnowledgeType.CHARACTER,
            name="秦阳",
            aliases=["秦无咎"],
            summary="主角，早期出现疑似金鳞元神异象。",
            importance=StructuredKnowledgeImportance.CORE,
            lifecycle=StructuredKnowledgeLifecycle.DRAFT,
            source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
            source_note="作者手动确认：第1章 大田金鳞元神出。",
            role_type="protagonist",
            identity="少年修士",
            relationship_summary="暂未建立主要关系网。",
            current_realm_text="未定",
            first_seen_chapter_id="chapter-001",
            created_at=NOW,
            updated_at=NOW,
        )

        self.assertFalse(card.can_be_used_as_effective_knowledge())
        confirmed = card.model_copy(
            update={"lifecycle": StructuredKnowledgeLifecycle.CONFIRMED}
        )
        self.assertTrue(confirmed.can_be_used_as_effective_knowledge())
        payload = card.model_dump(mode="json")
        self.assertNotIn("body", payload)
        self.assertNotIn("tags", payload)
        self.assertNotIn("fields", payload)
        self.assertNotIn("source_refs", payload)
        self.assertEqual(card.role_type, "protagonist")

    def test_knowledge_schema_does_not_register_forbidden_fields(self) -> None:
        schema = knowledge_type_schema(StructuredKnowledgeType.CHARACTER)
        field_keys = {field.field_key for field in schema.fields}

        self.assertIn("source_origin", field_keys)
        self.assertIn("role_type", field_keys)
        self.assertNotIn("body", field_keys)
        self.assertNotIn("tags", field_keys)
        self.assertNotIn("fields", field_keys)
        self.assertNotIn("source_refs", field_keys)

    def test_inbox_records_use_three_common_statuses(self) -> None:
        idea = MVPInboxIdea(
            id="idea-001",
            content="灵感内容",
            source_chapter_id="chapter-001",
            priority=MVPInboxPriority.NORMAL,
            status=MVPInboxStatus.TODO,
            created_at=NOW,
            updated_at=NOW,
        )
        pending_fact = MVPInboxPendingFact(
            id="pending-fact-001",
            title="金鳞异象",
            content="秦阳掌心出现金鳞异象。",
            source_chapter_id="chapter-001",
            origin="作者手动记录",
            priority=MVPInboxPriority.HIGH,
            status=MVPInboxStatus.PROCESSED,
            confirmed_knowledge_card_id="character-qin-yang",
            created_at=NOW,
            updated_at=NOW,
        )
        issue = MVPInboxIssue(
            id="issue-001",
            title="金鳞异象是否过早暴露",
            content="需要确认是否要在第 1 章解释异象来源。",
            status=MVPInboxStatus.DEPRECATED,
            created_at=NOW,
            updated_at=NOW,
        )

        self.assertEqual(idea.status, MVPInboxStatus.TODO)
        self.assertEqual(pending_fact.confirmed_knowledge_card_id, "character-qin-yang")
        self.assertEqual(issue.status, MVPInboxStatus.DEPRECATED)

    def test_writing_ai_run_saves_prompt_retrieval_and_output(self) -> None:
        run = WritingAIRun(
            run_id="writing-ai-run-001",
            status=WritingAIRunStatus.COMPLETED,
            button_type=WritingAIButtonType.CONTINUE,
            button_label="续写",
            model="deepseek-chat",
            chapter_id="chapter-001",
            chapter_title="第1章 大田金鳞元神出",
            reference_scope=WritingAIReferenceScope.CHAPTER,
            input=WritingAIInput(user_input="续写 200 字"),
            prompt_snapshot=WritingAIPromptSnapshot(
                prompt_id="continue_prompt_v1",
                prompt_version="1.0.0",
                system_prompt="系统提示词",
                user_prompt="用户提示词",
                rendered_at=NOW,
            ),
            retrieval_context=WritingAIRetrievalContext(
                used=True,
                items=[
                    WritingAIRetrievalEvidenceItem(
                        item_id="chapter:chapter-001",
                        source_type="chapter",
                        source_id="chapter-001",
                        display_name="第1章 大田金鳞元神出",
                        excerpt="秦阳掌心出现金鳞异象。",
                        usage="当前章节上下文",
                    )
                ],
                knowledge_context="无匹配知识卡。",
                evidence_context="当前章节上下文。",
            ),
            raw_llm_output='{"output_type":"text_candidate","text":"正文候选。"}',
            structured_output=WritingAIStructuredOutput(
                output_type=WritingAIOutputType.TEXT_CANDIDATE,
                content={"text": "正文候选。", "risk_notes": [], "used_evidence": []},
            ),
            created_at=NOW,
            updated_at=NOW,
        )

        prompt_snapshot = run.prompt_snapshot
        self.assertIsNotNone(prompt_snapshot)
        assert prompt_snapshot is not None
        self.assertEqual(prompt_snapshot.prompt_id, "continue_prompt_v1")
        self.assertEqual(run.reference_scope, WritingAIReferenceScope.CHAPTER)
        structured_output = run.structured_output
        retrieval_context = run.retrieval_context
        self.assertIsNotNone(structured_output)
        self.assertIsNotNone(retrieval_context)
        assert structured_output is not None
        assert retrieval_context is not None
        self.assertEqual(
            structured_output.output_type,
            WritingAIOutputType.TEXT_CANDIDATE,
        )
        self.assertEqual(retrieval_context.items[0].source_type, "chapter")

    def test_editor_preferences_do_not_accept_llm_config(self) -> None:
        preferences = EditorPreferences(
            font_size=18,
            font_style=EditorFontStyle.SERIF,
            editor_background=EditorBackground.DARK,
            updated_at=NOW,
        )

        self.assertEqual(preferences.font_style, EditorFontStyle.SERIF)
        with self.assertRaises(ValidationError):
            EditorPreferences.model_validate(
                {
                    "font_size": 18,
                    "font_style": EditorFontStyle.SERIF,
                    "editor_background": EditorBackground.DARK,
                    "updated_at": NOW,
                    "model_name": cast(Any, "deepseek"),
                }
            )
