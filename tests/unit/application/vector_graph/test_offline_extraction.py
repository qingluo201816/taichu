import hashlib
import json
from pathlib import Path

import pytest

from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphSourceDocument,
    VectorGraphSourceType,
)
from taichu.application.vector_graph.offline_extraction import (
    load_offline_extraction_package,
)


def _write_package(tmp_path: Path) -> tuple[Path, Path, VectorGraphBuildPlan, list[VectorGraphSourceDocument]]:
    content = "秦浩轩生活在大田镇。"
    content_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    document = VectorGraphSourceDocument(
        source_type=VectorGraphSourceType.MANUSCRIPT_CHUNK,
        source_id="chapter-1",
        source_ref="manuscript:chapter-1:0-10",
        title="第一章",
        content=content,
        content_sha256=content_sha,
        updated_at="2026-08-16T00:00:00Z",
    )
    plan = VectorGraphBuildPlan(
        snapshot_sha256="a" * 64,
        manuscript_count=1,
        manuscript_chunk_count=1,
        knowledge_card_count=0,
        document_count=1,
        total_content_chars=len(content),
    )
    input_path = tmp_path / "input.jsonl"
    input_records = [
        {
            "record_type": "manifest",
            "schema_version": "taichu.vector_graph.offline_extraction_input.v1",
            "snapshot_sha256": plan.snapshot_sha256,
        },
        {
            "record_type": "document",
            "document_index": 0,
            "source_ref": document.source_ref,
            "chunk_index": 0,
            "content_sha256": content_sha,
            "content": content,
        },
    ]
    input_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in input_records) + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    extraction = {
        "record_type": "extraction",
        "document_index": 0,
        "source_ref": document.source_ref,
        "chunk_index": 0,
        "content_sha256": content_sha,
        "status": "completed",
        "triplets": [["秦浩轩", "位于", "大田镇"]],
        "warnings": [],
    }
    triplets_path = output_dir / "triplets.jsonl"
    triplets_path.write_text(json.dumps(extraction, ensure_ascii=False) + "\n", encoding="utf-8")
    triplets_sha = hashlib.sha256(triplets_path.read_bytes()).hexdigest()
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "taichu.vector_graph.offline_extraction_output.v1",
                "status": "complete",
                "input_snapshot_sha256": plan.snapshot_sha256,
                "input_document_count": 1,
                "completed_document_count": 1,
                "missing_document_indexes": [],
                "total_triplet_count": 1,
                "triplets_file_sha256": triplets_sha,
                "producer": {"surface": "ChatGPT web", "model": "test"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_dir / "validation_report.json").write_text(
        json.dumps({"valid": True}), encoding="utf-8"
    )
    return input_path, output_dir, plan, [document]


def test_load_offline_extraction_package_validates_and_returns_triplets(
    tmp_path: Path,
) -> None:
    input_path, output_dir, plan, documents = _write_package(tmp_path)

    package = load_offline_extraction_package(
        input_path=input_path,
        output_dir=output_dir,
        plan=plan,
        documents=documents,
    )

    assert package.document_count == 1
    assert package.triplet_count == 1
    assert next(iter(package.triplets.values())) == (("秦浩轩", "位于", "大田镇"),)


def test_load_offline_extraction_package_rejects_stale_snapshot(tmp_path: Path) -> None:
    input_path, output_dir, plan, documents = _write_package(tmp_path)
    stale_plan = plan.model_copy(update={"snapshot_sha256": "b" * 64})

    with pytest.raises(ValueError, match="快照已过期"):
        load_offline_extraction_package(
            input_path=input_path,
            output_dir=output_dir,
            plan=stale_plan,
            documents=documents,
        )
