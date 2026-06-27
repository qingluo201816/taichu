"""Selection workflow schema contract tests."""

import unittest
from typing import Any, cast

from pydantic import ValidationError

from taichu.application.workflows.selection import (
    SelectionWorkflowInput,
    SelectionWorkflowOutput,
)
from taichu.domain.models import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
    AIWorkflow,
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)


def create_selection_ref() -> SourceRef:
    """Create a valid paragraph-relative selection SourceRef."""
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="project_assets/source/manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        char_start=0,
        char_end=4,
        excerpt="选中文本",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )


class SelectionWorkflowSchemaTest(unittest.TestCase):
    """Verify Selection AI contracts without implementing the service."""

    def test_selection_input_accepts_selection_workflow(self) -> None:
        data = SelectionWorkflowInput(
            workflow=AIWorkflow.CONTINUE_TEXT,
            chapter_id="chapter_001",
            selected_text="选中文本",
            selection_ref=create_selection_ref(),
            target_word_count=200,
        )

        self.assertEqual(data.workflow, AIWorkflow.CONTINUE_TEXT)
        self.assertEqual(data.retrieval_scope.value, "fact_scope")

    def test_selection_input_rejects_chat_workflow(self) -> None:
        with self.assertRaises(ValidationError):
            SelectionWorkflowInput(
                workflow=AIWorkflow.CHAT,
                chapter_id="chapter_001",
                selected_text="选中文本",
                selection_ref=create_selection_ref(),
            )

    def test_selection_output_requires_ai_result_card(self) -> None:
        card = AIResultCard(
            id="card_001",
            type=AIResultCardType.TEXT_CANDIDATE,
            workflow=AIWorkflow.CONTINUE_TEXT,
            status=AIResultCardStatus.GENERATED,
            chapter_id="chapter_001",
            input_context={},
            content="续写候选",
            source_refs=[create_selection_ref()],
            created_at="2026-06-27T00:00:00Z",
            updated_at="2026-06-27T00:00:00Z",
        )

        self.assertEqual(SelectionWorkflowOutput(card=card).card.id, card.id)
        with self.assertRaises(ValidationError):
            SelectionWorkflowOutput(card=cast(Any, "裸字符串"))
