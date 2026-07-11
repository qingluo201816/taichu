"""Tests for the safe JSON evaluation dataset repository."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest

from taichu.infrastructure.evaluations.json_dataset_repository import (
    EvaluationDatasetRepositoryError,
    JsonEvaluationDatasetRepository,
)


class JsonEvaluationDatasetRepositoryTest(unittest.IsolatedAsyncioTestCase):
    """Validate discovery, checksums, source evidence, and path safety."""

    async def test_loads_curated_first_five_chapter_dataset(self) -> None:
        repository = JsonEvaluationDatasetRepository(
            Path("tests/fixtures/evaluations"),
            Path("project_assets/source"),
        )

        dataset = await repository.get_dataset(
            "taichu_knowledge_eval_first5_three_experts"
        )
        counts = [
            len(dataset.cases[case.case_id].expected_cards)
            for case in dataset.manifest.cases
        ]

        self.assertEqual(counts, [13, 11, 18, 27, 25, 67])
        self.assertEqual(dataset.manifest.lifecycle.value, "confirmed")
        self.assertTrue(dataset.checksum)

    async def test_default_list_only_returns_confirmed_valid_datasets(self) -> None:
        repository = JsonEvaluationDatasetRepository(
            Path("tests/fixtures/evaluations"),
            Path("project_assets/source"),
        )

        datasets = await repository.list_datasets()

        self.assertIn(
            "taichu_knowledge_eval_first5_three_experts",
            [dataset.dataset_id for dataset in datasets],
        )

    async def test_rejects_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            datasets_root, source_root = _write_minimal_dataset(Path(directory))
            expected_path = datasets_root / "demo_dataset" / "expected.json"
            expected_path.write_text("[]\n", encoding="utf-8")
            repository = JsonEvaluationDatasetRepository(
                datasets_root,
                source_root,
            )

            result = await repository.validate_dataset("demo_dataset")

            self.assertFalse(result.valid)
            self.assertEqual(result.issues[0].code, "EVALUATION_DATASET_INVALID")

    async def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            datasets_root, source_root = _write_minimal_dataset(Path(directory))
            dataset_root = datasets_root / "demo_dataset"
            manifest = _read_json(dataset_root / "manifest.json")
            manifest["cases"][0]["expected_cards_path"] = "../outside.json"
            _write_json(dataset_root / "manifest.json", manifest)
            _write_checksums(dataset_root)
            repository = JsonEvaluationDatasetRepository(
                datasets_root,
                source_root,
            )

            with self.assertRaises(EvaluationDatasetRepositoryError) as context:
                await repository.get_dataset("demo_dataset")

            self.assertEqual(context.exception.code, "EVALUATION_ID_INVALID")

    async def test_rejects_changed_markdown_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            datasets_root, source_root = _write_minimal_dataset(Path(directory))
            source_path = source_root / "manuscripts" / "chapter.md"
            source_path.write_text("正文已经变化。", encoding="utf-8")
            repository = JsonEvaluationDatasetRepository(
                datasets_root,
                source_root,
            )

            result = await repository.validate_dataset("demo_dataset")

            self.assertFalse(result.valid)
            self.assertEqual(result.issues[0].code, "EVALUATION_SOURCE_CHANGED")


def _write_minimal_dataset(root: Path) -> tuple[Path, Path]:
    datasets_root = root / "evaluations"
    dataset_root = datasets_root / "demo_dataset"
    source_root = root / "source"
    (dataset_root / "_metadata").mkdir(parents=True)
    (source_root / "manuscripts").mkdir(parents=True)
    markdown = "秦阳走入山门。"
    source_hash = sha256(markdown.encode("utf-8")).hexdigest()
    (source_root / "manuscripts" / "chapter.md").write_text(
        markdown,
        encoding="utf-8",
    )
    _write_json(
        source_root / "manuscripts" / "manifest.json",
        {
            "chapters": [
                {
                    "id": "chapter-abcdef",
                    "markdown_path": "manuscripts/chapter.md",
                }
            ]
        },
    )
    _write_json(dataset_root / "_metadata" / "schema.json", {})
    _write_json(
        dataset_root / "expected.json",
        [
            {
                "expected_card_id": "character_qinyang",
                "knowledge_type": "character",
                "card": {
                    "type": "character",
                    "name": "秦阳",
                    "aliases": [],
                    "summary": "秦阳走入山门。",
                    "status": "active",
                    "importance": "normal",
                    "source_origin": "agent_extract",
                },
                "accepted_names": ["秦阳"],
                "exact_fields": ["type", "status"],
                "set_fields": ["aliases"],
                "semantic_fields": ["summary"],
                "expected_claims": [
                    {
                        "claim_id": "claim_qinyang",
                        "field": "summary",
                        "importance": "major",
                        "description": "秦阳走入山门",
                        "source_quote_ids": ["quote_qinyang"],
                    }
                ],
                "source_quote_ids": ["quote_qinyang"],
            }
        ],
    )
    _write_json(
        dataset_root / "rules.json",
        {
            "field_weights": {"type": 2},
            "reference_identity_map": {},
            "reference_fields": [],
        },
    )
    _write_json(
        dataset_root / "evidence.json",
        [
            {
                "quote_id": "quote_qinyang",
                "chapter_id": "chapter-abcdef",
                "text": markdown,
                "start_offset": 0,
                "end_offset": len(markdown),
                "source_hash": source_hash,
            }
        ],
    )
    _write_json(dataset_root / "negative.json", [])
    _write_json(
        dataset_root / "manifest.json",
        {
            "dataset_id": "demo_dataset",
            "label": "演示评测集",
            "lifecycle": "confirmed",
            "agent_name": "knowledge_extraction",
            "schema_snapshot_path": "_metadata/schema.json",
            "checksum_manifest_path": "_metadata/checksums.sha256.json",
            "cases": [
                {
                    "case_id": "chapter_001",
                    "scope_type": "chapter",
                    "chapter_ids": ["chapter-abcdef"],
                    "source_chapter_hashes": {
                        "chapter-abcdef": source_hash,
                    },
                    "expected_cards_path": "expected.json",
                    "evaluation_rules_path": "rules.json",
                    "source_evidence_path": "evidence.json",
                    "negative_cases_path": "negative.json",
                }
            ],
        },
    )
    _write_checksums(dataset_root)
    return datasets_root, source_root


def _write_checksums(dataset_root: Path) -> None:
    checksum_path = dataset_root / "_metadata" / "checksums.sha256.json"
    values = {
        path.relative_to(dataset_root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(dataset_root.rglob("*"))
        if path.is_file() and path != checksum_path
    }
    _write_json(checksum_path, values)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
