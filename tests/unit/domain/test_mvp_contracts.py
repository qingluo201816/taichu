"""MVP first-version data contract tests."""

import unittest
from typing import Any, cast

from pydantic import ValidationError

from taichu.domain.models import (
    AIReferenceScope,
    AIWorkspaceConversation,
    AIWorkspaceMessage,
    AIWorkspaceMessageRole,
    AIWorkspaceOutputType,
    AIWorkspaceTaskType,
    CharacterKnowledgeFields,
    CharacterStateRecord,
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
    PromptSnapshot,
    SourceReference,
    SourceReferenceType,
    StructuredKnowledgeCard,
    StructuredKnowledgeImportance,
    StructuredKnowledgeStatus,
    StructuredKnowledgeType,
    WritingOutline,
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
            body="秦阳出身低微，但在残碑前引发金鳞异象。",
            importance=StructuredKnowledgeImportance.CORE,
            status=StructuredKnowledgeStatus.DRAFT,
            source_refs=[
                SourceReference(
                    source_type=SourceReferenceType.CHAPTER,
                    source_id="chapter-001",
                    display_name="第1章 大田金鳞元神出",
                    excerpt="秦阳掌心浮现金鳞，残碑随之震动。",
                    note="角色首次出现异象。",
                )
            ],
            fields=CharacterKnowledgeFields(
                identity="少年修士",
                faction="暂无",
                current_realm="未定",
                techniques=["未定"],
                items=["残碑碎片"],
                relationship_summary="暂未建立主要关系网。",
                appearance_chapters=["chapter-001"],
                state_records=[
                    CharacterStateRecord(
                        time_point="故事开篇",
                        chapter_id="chapter-001",
                        realm="未定",
                        location="大田村外残碑",
                        life_status="存活",
                        camp="未定",
                        note="引发金鳞异象。",
                    )
                ],
            ).model_dump(mode="json"),
            created_at=NOW,
            updated_at=NOW,
        )

        self.assertFalse(card.can_be_used_as_effective_knowledge())
        active = card.model_copy(update={"status": StructuredKnowledgeStatus.ACTIVE})
        self.assertTrue(active.can_be_used_as_effective_knowledge())
        self.assertNotIn("known_secrets", card.fields)
        self.assertNotIn("current_goal", card.fields)

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

    def test_ai_workspace_conversation_saves_prompt_snapshot(self) -> None:
        conversation = AIWorkspaceConversation(
            id="ai-conv-001",
            chapter_id="chapter-001",
            task_type=AIWorkspaceTaskType.CONTINUE,
            reference_scope=AIReferenceScope.CHAPTER,
            model_name="mock-llm",
            is_mock=True,
            messages=[
                AIWorkspaceMessage(
                    message_id="msg-001",
                    role=AIWorkspaceMessageRole.USER,
                    content="续写 200 字",
                    task_type=AIWorkspaceTaskType.CONTINUE,
                    reference_scope=AIReferenceScope.CHAPTER,
                    prompt_snapshot=PromptSnapshot(
                        structured={
                            "user_input": "续写 200 字",
                            "route": "mock_continue_text",
                        },
                        final_prompt="【模拟提示词】任务：续写。",
                    ),
                    skill="mock-continue",
                    route="mock_continue_text",
                    created_at=NOW,
                ),
                AIWorkspaceMessage(
                    message_id="msg-002",
                    role=AIWorkspaceMessageRole.ASSISTANT,
                    content={"text": "模拟正文候选。"},
                    task_type=AIWorkspaceTaskType.CONTINUE,
                    reference_scope=AIReferenceScope.CHAPTER,
                    output_type=AIWorkspaceOutputType.TEXT_CANDIDATE,
                    is_mock=True,
                    created_at=NOW,
                ),
            ],
            created_at=NOW,
            updated_at=NOW,
        )

        prompt_snapshot = conversation.messages[0].prompt_snapshot
        self.assertIsNotNone(prompt_snapshot)
        assert prompt_snapshot is not None
        self.assertTrue(conversation.is_mock)
        self.assertEqual(prompt_snapshot.final_prompt, "【模拟提示词】任务：续写。")

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
