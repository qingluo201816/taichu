"""SourceRef v1 contract tests."""

import unittest

from pydantic import ValidationError

from taichu.domain.models import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.domain.rules import (
    SourceRefValidationResult,
    SourceRefValidator,
    validate_source_ref_contract,
)


def create_source_ref() -> SourceRef:
    """Create a valid SourceRef for contract tests."""
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id="chapter_001",
        path="project_assets/source/manuscripts/chapters/chapter_001.md",
        chapter_id="chapter_001",
        anchor_type=SourceAnchorType.PARAGRAPH,
        paragraph_start=0,
        excerpt="正文段落",
        excerpt_hash="hash_excerpt",
        source_hash="hash_source",
        created_at="2026-06-27T00:00:00Z",
    )


class AcceptingValidator:
    """Storage-aware validator stub used to verify the Protocol shape."""

    def validate(self, ref: SourceRef) -> SourceRefValidationResult:
        return SourceRefValidationResult(valid=True, ref=ref)


class SourceRefContractTest(unittest.TestCase):
    """Verify local SourceRef validation boundaries."""

    def test_source_ref_validator_protocol(self) -> None:
        validator = AcceptingValidator()

        self.assertIsInstance(validator, SourceRefValidator)
        self.assertTrue(validator.validate(create_source_ref()).valid)

    def test_validate_source_ref_contract_accepts_valid_ref(self) -> None:
        ref = create_source_ref()

        self.assertEqual(validate_source_ref_contract(ref), ref)

    def test_rejects_generated_sqlite_source(self) -> None:
        with self.assertRaises(ValidationError):
            SourceRef(
                source_type=SourceRefSourceType.CHAPTER,
                source_id="chapter_001",
                path="project_assets/generated/sqlite/taichu.db",
                anchor_type=SourceAnchorType.DOCUMENT,
                excerpt="不允许",
                excerpt_hash="hash_excerpt",
                source_hash="hash_source",
                created_at="2026-06-27T00:00:00Z",
            )

    def test_rejects_invalid_paragraph_range(self) -> None:
        with self.assertRaises(ValidationError):
            SourceRef(
                source_type=SourceRefSourceType.CHAPTER,
                source_id="chapter_001",
                path="project_assets/source/manuscripts/chapters/chapter_001.md",
                anchor_type=SourceAnchorType.PARAGRAPH_RANGE,
                paragraph_start=2,
                paragraph_end=1,
                excerpt="倒置范围",
                excerpt_hash="hash_excerpt",
                source_hash="hash_source",
                created_at="2026-06-27T00:00:00Z",
            )

    def test_char_offsets_are_paragraph_relative(self) -> None:
        ref = SourceRef(
            source_type=SourceRefSourceType.CHAPTER,
            source_id="chapter_001",
            path="project_assets/source/manuscripts/chapters/chapter_001.md",
            anchor_type=SourceAnchorType.PARAGRAPH,
            paragraph_start=0,
            char_start=1,
            char_end=3,
            excerpt="正文段落",
            excerpt_hash="hash_excerpt",
            source_hash="hash_source",
            created_at="2026-06-27T00:00:00Z",
        )

        self.assertEqual(ref.char_start, 1)
        self.assertEqual(ref.char_end, 3)

    def test_knowledge_field_requires_knowledge_source(self) -> None:
        with self.assertRaises(ValidationError):
            SourceRef(
                source_type=SourceRefSourceType.CHAPTER,
                source_id="chapter_001",
                path="project_assets/source/manuscripts/chapters/chapter_001.md",
                anchor_type=SourceAnchorType.KNOWLEDGE_FIELD,
                field_path="fields.realm",
                excerpt="字段证据",
                excerpt_hash="hash_excerpt",
                source_hash="hash_source",
                created_at="2026-06-27T00:00:00Z",
            )
