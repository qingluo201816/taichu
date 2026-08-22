"""离线三元组抽取包的独立校验与加载。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphExtractedTriplets,
    VectorGraphSourceDocument,
)

INPUT_SCHEMA = "taichu.vector_graph.offline_extraction_input.v1"
OUTPUT_SCHEMA = "taichu.vector_graph.offline_extraction_output.v1"
REQUIRED_OUTPUT_FILES = {
    "manifest.json",
    "triplets.jsonl",
    "validation_report.json",
}
_OUTPUT_RECORD_KEYS = {
    "record_type",
    "document_index",
    "source_ref",
    "chunk_index",
    "content_sha256",
    "status",
    "triplets",
    "warnings",
}


@dataclass(frozen=True, slots=True)
class OfflineExtractionPackage:
    triplets: VectorGraphExtractedTriplets
    document_count: int
    triplet_count: int
    warning_count: int
    snapshot_sha256: str
    triplets_file_sha256: str
    producer_surface: str
    producer_model: str


def load_offline_extraction_package(
    *,
    input_path: Path,
    output_dir: Path,
    plan: VectorGraphBuildPlan,
    documents: list[VectorGraphSourceDocument],
) -> OfflineExtractionPackage:
    """校验输入快照、当前语料和输出三元组完全一致后才返回数据。"""
    input_records = _read_jsonl(input_path)
    if not input_records:
        raise ValueError("离线抽取输入文件为空。")
    input_manifest = input_records[0]
    if input_manifest.get("record_type") != "manifest":
        raise ValueError("离线抽取输入第一条必须是清单。")
    if input_manifest.get("schema_version") != INPUT_SCHEMA:
        raise ValueError("离线抽取输入 Schema 版本不支持。")
    if input_manifest.get("snapshot_sha256") != plan.snapshot_sha256:
        raise ValueError("离线抽取输入快照已过期，与当前语料不一致。")

    input_documents = input_records[1:]
    if len(input_documents) != plan.document_count or len(documents) != plan.document_count:
        raise ValueError("离线抽取输入文档数与当前建模计划不一致。")
    for index, (record, document) in enumerate(
        zip(input_documents, documents, strict=True)
    ):
        expected = {
            "document_index": index,
            "source_ref": document.source_ref,
            "chunk_index": document.chunk_index,
            "content_sha256": document.content_sha256,
        }
        if record.get("record_type") != "document" or any(
            record.get(key) != value for key, value in expected.items()
        ):
            raise ValueError(f"离线抽取输入第 {index} 个文档与当前语料不一致。")
        if record.get("content") != document.content:
            raise ValueError(f"离线抽取输入第 {index} 个文档正文已变化。")

    actual_files = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual_files != REQUIRED_OUTPUT_FILES:
        missing = sorted(REQUIRED_OUTPUT_FILES - actual_files)
        extra = sorted(actual_files - REQUIRED_OUTPUT_FILES)
        raise ValueError(f"离线输出包文件不完整：缺少 {missing}，多出 {extra}。")

    output_manifest = _read_json(output_dir / "manifest.json")
    report = _read_json(output_dir / "validation_report.json")
    if output_manifest.get("schema_version") != OUTPUT_SCHEMA:
        raise ValueError("离线输出 Schema 版本不支持。")
    if output_manifest.get("status") != "complete":
        raise ValueError("离线输出包未标记为完整。")
    if output_manifest.get("input_snapshot_sha256") != plan.snapshot_sha256:
        raise ValueError("离线输出快照与当前语料不一致。")
    if report.get("valid") is not True:
        raise ValueError("离线输出包的自检报告未通过。")

    triplets_path = output_dir / "triplets.jsonl"
    triplets_sha256 = hashlib.sha256(triplets_path.read_bytes()).hexdigest()
    if output_manifest.get("triplets_file_sha256") != triplets_sha256:
        raise ValueError("离线三元组文件哈希与清单不一致。")

    output_records = _read_jsonl(triplets_path)
    if len(output_records) != len(input_documents):
        raise ValueError("离线三元组记录数与输入文档数不一致。")
    extracted: dict[tuple[str, int, str], tuple[tuple[str, str, str], ...]] = {}
    total_triplets = 0
    warning_count = 0
    for index, (source, record) in enumerate(
        zip(input_documents, output_records, strict=True)
    ):
        if set(record) != _OUTPUT_RECORD_KEYS:
            raise ValueError(f"离线输出第 {index} 条字段不符合 Schema。")
        if record.get("record_type") != "extraction" or record.get("status") != "completed":
            raise ValueError(f"离线输出第 {index} 条未完成。")
        for key in ("document_index", "source_ref", "chunk_index", "content_sha256"):
            if record.get(key) != source.get(key):
                raise ValueError(f"离线输出第 {index} 条身份不匹配。")
        raw_triplets = record.get("triplets")
        if not isinstance(raw_triplets, list):
            raise ValueError(f"离线输出第 {index} 条三元组不是列表。")
        normalized: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in raw_triplets:
            if not isinstance(item, list) or len(item) != 3:
                raise ValueError(f"离线输出第 {index} 条含非法三元组。")
            value = tuple(str(part).strip() for part in item)
            if any(not part for part in value):
                raise ValueError(f"离线输出第 {index} 条含空三元组成员。")
            typed_value = (value[0], value[1], value[2])
            if typed_value in seen:
                raise ValueError(f"离线输出第 {index} 条含重复三元组。")
            seen.add(typed_value)
            normalized.append(typed_value)
        warnings = record.get("warnings")
        if not isinstance(warnings, list) or not all(
            isinstance(item, str) and item.strip() for item in warnings
        ):
            raise ValueError(f"离线输出第 {index} 条警告格式非法。")
        identity = (
            str(record["source_ref"]),
            int(record["chunk_index"]),
            str(record["content_sha256"]),
        )
        if identity in extracted:
            raise ValueError(f"离线输出第 {index} 条文档身份重复。")
        extracted[identity] = tuple(normalized)
        total_triplets += len(normalized)
        warning_count += len(warnings)

    if output_manifest.get("input_document_count") != len(output_records):
        raise ValueError("离线输出清单的输入文档数不一致。")
    if output_manifest.get("completed_document_count") != len(output_records):
        raise ValueError("离线输出清单的完成文档数不一致。")
    if output_manifest.get("total_triplet_count") != total_triplets:
        raise ValueError("离线输出清单的三元组总数不一致。")
    if output_manifest.get("missing_document_indexes") != []:
        raise ValueError("离线输出清单声明存在缺失文档。")

    producer = output_manifest.get("producer")
    producer = producer if isinstance(producer, dict) else {}
    return OfflineExtractionPackage(
        triplets=extracted,
        document_count=len(output_records),
        triplet_count=total_triplets,
        warning_count=warning_count,
        snapshot_sha256=plan.snapshot_sha256,
        triplets_file_sha256=triplets_sha256,
        producer_surface=str(producer.get("surface", "")).strip(),
        producer_model=str(producer.get("model", "")).strip(),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取 JSON 文件：{path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON 文件顶层必须是对象：{path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"无法读取 JSONL 文件：{path}") from error
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSONL 第 {line_number} 行不是合法 JSON：{path}") from error
        if not isinstance(value, dict):
            raise ValueError(f"JSONL 第 {line_number} 行顶层必须是对象：{path}")
        records.append(value)
    return records
