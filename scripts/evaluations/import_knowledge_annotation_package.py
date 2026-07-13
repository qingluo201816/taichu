"""Convert an author annotation ZIP into a runnable evaluation fixture."""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any
from zipfile import ZipFile

from taichu.application.evaluations.knowledge_extraction.models import (
    DatasetManifest,
    EvaluationRules,
    ExpectedCard,
    ExpectedClaim,
    NegativeCase,
    SourceEvidence,
)
from taichu.domain.models.structured_knowledge import (
    FORBIDDEN_KNOWLEDGE_FIELD_KEYS,
    StructuredKnowledgeType,
    all_knowledge_card_field_keys,
    all_knowledge_type_schemas,
    knowledge_type_field_keys,
)
from taichu.infrastructure.evaluations.json_dataset_repository import (
    JsonEvaluationDatasetRepository,
)


DEFAULT_DATASET_ID = "taichu_knowledge_eval_first5_author_confirmed"
CASE_NAMES = (
    "chapter_001",
    "chapter_002",
    "chapter_003",
    "chapter_004",
    "chapter_005",
    "batch_001_005",
)
EVIDENCE_TEXT_OVERRIDES = {
    "quote_negative_chapter_004_009": (
        "有失传已久的上古灵法、魔术、还有许多能令整个修真界掀起血雨腥风的法宝"
    ),
    "quote_negative_batch_001_005_041": (
        "有失传已久的上古灵法、魔术、还有许多能令整个修真界掀起血雨腥风的法宝"
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=Path)
    parser.add_argument(
        "--datasets-root",
        type=Path,
        default=Path("tests/fixtures/evaluations"),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("project_assets/source"),
    )
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    output = build_dataset(
        zip_path=args.zip_path,
        datasets_root=args.datasets_root,
        source_root=args.source_root,
        dataset_id=args.dataset_id,
        replace=args.replace,
    )
    result = asyncio.run(
        JsonEvaluationDatasetRepository(
            args.datasets_root,
            args.source_root,
        ).validate_dataset(args.dataset_id)
    )
    if not result.valid:
        details = "; ".join(f"{item.code}: {item.message}" for item in result.issues)
        raise RuntimeError(f"生成后的评测集未通过仓库校验：{details}")
    print(f"已生成并验证评测集：{output}")


def build_dataset(
    *,
    zip_path: Path,
    datasets_root: Path,
    source_root: Path,
    dataset_id: str,
    replace: bool,
) -> Path:
    zip_path = zip_path.resolve()
    source_root = source_root.resolve()
    datasets_root = datasets_root.resolve()
    output_root = datasets_root / dataset_id
    if output_root.exists():
        if not replace:
            raise FileExistsError(f"评测集目录已存在：{output_root}")
        shutil.rmtree(output_root)

    source_manifest = _read_json(source_root / "manuscripts/manifest.json")
    sources = _load_sources(source_root, source_manifest)
    zip_digest = sha256(zip_path.read_bytes()).hexdigest()
    ambiguity_records: list[dict[str, Any]] = []
    corrected_records: list[dict[str, Any]] = []
    dropped_records: list[dict[str, Any]] = []
    case_outputs: list[dict[str, Any]] = []
    case_refs: list[dict[str, Any]] = []

    with ZipFile(zip_path) as archive:
        package_root = _package_root(archive)
        package_manifest = _read_zip_json(archive, f"{package_root}/manifest.json")
        source_scope = package_manifest["source_scope"]
        chapter_ids_by_case = {
            str(item["case_id"]): [str(item["章节标识"])]
            for item in source_scope["chapters"]
        }
        chapter_ids_by_case["batch_001_005"] = [
            str(item["章节标识"]) for item in source_scope["chapters"]
        ]

        for case_name in CASE_NAMES:
            draft = _read_zip_json(
                archive,
                f"{package_root}/developer_draft/{case_name}.json",
            )
            chapter_ids = chapter_ids_by_case[case_name]
            case_dir = f"cases/{case_name}"
            expected = [_convert_card(item) for item in draft["expected_cards"]]
            positive_quote_ids = {
                quote_id
                for card in expected
                for quote_id in (
                    card["source_quote_ids"]
                    + [
                        value
                        for claim in card["expected_claims"]
                        for value in claim["source_quote_ids"]
                    ]
                )
            }
            resolved_evidence = [
                _resolve_evidence(
                    item,
                    sources=sources,
                    case_name=case_name,
                    ambiguity_records=ambiguity_records,
                    required=item["quote_id"] in positive_quote_ids,
                    corrected_records=corrected_records,
                    dropped_records=dropped_records,
                )
                for item in draft["source_evidence_draft"]
            ]
            evidence = [item for item in resolved_evidence if item is not None]
            known_quote_ids = {item["quote_id"] for item in evidence}
            negatives = []
            for item in draft["negative_cases"]:
                converted = _convert_negative(item)
                available_quote_ids = [
                    quote_id
                    for quote_id in converted["source_quote_ids"]
                    if quote_id in known_quote_ids
                ]
                if not available_quote_ids:
                    dropped_records.append(
                        {
                            "case_id": case_name,
                            "kind": "negative_case",
                            "id": converted["negative_case_id"],
                            "reason": "全部原文依据均无法在当前 Markdown 中定位。",
                        }
                    )
                    continue
                converted["source_quote_ids"] = available_quote_ids
                negatives.append(converted)
            rules = _convert_rules(draft["evaluation_rules"])

            for item in expected:
                ExpectedCard.model_validate(item)
            for item in evidence:
                SourceEvidence.model_validate(item)
            for item in negatives:
                NegativeCase.model_validate(item)
            EvaluationRules.model_validate(rules)

            files = {
                f"{case_dir}/expected.json": expected,
                f"{case_dir}/evidence.json": evidence,
                f"{case_dir}/negative.json": negatives,
                f"{case_dir}/rules.json": rules,
            }
            case_outputs.append(files)
            case_refs.append(
                {
                    "case_id": case_name,
                    "scope_type": draft["scope_type"],
                    "chapter_ids": chapter_ids,
                    "source_chapter_hashes": {
                        chapter_id: sources[chapter_id]["hash"]
                        for chapter_id in chapter_ids
                    },
                    "expected_cards_path": f"{case_dir}/expected.json",
                    "evaluation_rules_path": f"{case_dir}/rules.json",
                    "source_evidence_path": f"{case_dir}/evidence.json",
                    "negative_cases_path": f"{case_dir}/negative.json",
                }
            )

    manifest = {
        "dataset_id": dataset_id,
        "label": "太初前五章知识沉淀评测集（作者确认标注）",
        "lifecycle": "confirmed",
        "agent_name": "knowledge_extraction",
        "schema_snapshot_path": "_metadata/schema.json",
        "checksum_manifest_path": "_metadata/checksums.sha256.json",
        "cases": case_refs,
    }
    DatasetManifest.model_validate(manifest)
    schema_snapshot = {
        "source": "src/taichu/domain/models/structured_knowledge.py",
        "knowledge_types": [
            item.model_dump(mode="json") for item in all_knowledge_type_schemas()
        ],
        "forbidden_card_fields": sorted(FORBIDDEN_KNOWLEDGE_FIELD_KEYS),
        "notes": {
            "appearance_chapter_count": "保留为统计字段，但不参与抽取效果评分。",
            "expected_claims_importance": "仅表示评测断言优先级，不是知识卡字段。",
        },
    }
    import_report = {
        "source_package": zip_path.name,
        "source_package_sha256": zip_digest,
        "source_dataset_id": package_manifest["dataset_id"],
        "transformations": [
            "作者审核结构映射为当前运行时评测契约。",
            "知识卡 lifecycle 从标注草稿态调整为运行候选使用的 confirmed。",
            "按当前 Markdown 精确解析证据偏移与来源哈希。",
            "移除仅供作者审核和开发映射使用的辅助字段。",
            "使用当前知识卡 schema 重新生成快照。",
        ],
        "case_counts": {
            case_name: {
                "expected_cards": len(case_outputs[index][f"cases/{case_name}/expected.json"]),
                "source_evidence": len(case_outputs[index][f"cases/{case_name}/evidence.json"]),
                "negative_cases": len(case_outputs[index][f"cases/{case_name}/negative.json"]),
            }
            for index, case_name in enumerate(CASE_NAMES)
        },
        "ambiguous_exact_matches": ambiguity_records,
        "corrected_evidence_texts": corrected_records,
        "dropped_unsupported_annotations": dropped_records,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "manifest.json", manifest)
    _write_json(output_root / "_metadata/schema.json", schema_snapshot)
    _write_json(output_root / "_metadata/import_report.json", import_report)
    for files in case_outputs:
        for relative_path, payload in files.items():
            _write_json(output_root / relative_path, payload)
    _write_checksums(output_root)
    return output_root


def _convert_card(value: dict[str, Any]) -> dict[str, Any]:
    knowledge_type = StructuredKnowledgeType(value["knowledge_type"])
    card = deepcopy(value["card"])
    unknown = set(card) - all_knowledge_card_field_keys()
    if unknown:
        raise ValueError(
            f"{value['expected_card_id']} 包含当前 schema 未定义字段：{sorted(unknown)}"
        )
    wrong_type_fields = set(card) - knowledge_type_field_keys(knowledge_type) - {"type"}
    if wrong_type_fields:
        raise ValueError(
            f"{value['expected_card_id']} 包含其他知识类型字段：{sorted(wrong_type_fields)}"
        )
    if set(card) & FORBIDDEN_KNOWLEDGE_FIELD_KEYS:
        raise ValueError(f"{value['expected_card_id']} 包含已禁用知识卡字段")
    card["type"] = knowledge_type.value
    card["lifecycle"] = "confirmed"
    claims = [
        ExpectedClaim(
            claim_id=item["claim_id"],
            field=item["field"],
            importance=item["importance"],
            description=item["description"],
            source_quote_ids=item["source_quote_ids"],
        ).model_dump(mode="json")
        for item in value["expected_claims"]
    ]
    return {
        "expected_card_id": value["expected_card_id"],
        "knowledge_type": knowledge_type.value,
        "card": card,
        "accepted_names": value["accepted_names"],
        "exact_fields": [
            field for field in value["exact_fields"] if field != "appearance_chapter_count"
        ],
        "set_fields": value["set_fields"],
        "semantic_fields": value["semantic_fields"],
        "expected_claims": claims,
        "source_quote_ids": value["source_quote_ids"],
    }


def _resolve_evidence(
    value: dict[str, Any],
    *,
    sources: dict[str, dict[str, str]],
    case_name: str,
    ambiguity_records: list[dict[str, Any]],
    required: bool,
    corrected_records: list[dict[str, Any]],
    dropped_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    chapter_id = str(value["chapter_id"])
    original_text = str(value["text"])
    text = EVIDENCE_TEXT_OVERRIDES.get(str(value["quote_id"]), original_text)
    if text != original_text:
        corrected_records.append(
            {
                "case_id": case_name,
                "quote_id": value["quote_id"],
                "original_text": original_text,
                "resolved_text": text,
                "reason": "标注摘录省略了原句中间文字，已按当前 Markdown 补全。",
            }
        )
    markdown = sources[chapter_id]["text"]
    starts = _all_starts(markdown, text)
    resolved_text = text
    if not starts:
        normalized_spans = _normalized_spans(markdown, text)
        starts = [start for start, _end in normalized_spans]
        if normalized_spans:
            start, end = normalized_spans[0]
            resolved_text = markdown[start:end]
    if not starts:
        if required:
            raise ValueError(
                f"{case_name}/{value['quote_id']} 无法在 {chapter_id} 中精确定位：{text!r}"
            )
        dropped_records.append(
            {
                "case_id": case_name,
                "kind": "source_evidence",
                "id": value["quote_id"],
                "chapter_id": chapter_id,
                "text": text,
                "reason": "原文无法在当前 Markdown 中精确定位，且仅供负样本使用。",
            }
        )
        return None
    if len(starts) > 1:
        ambiguity_records.append(
            {
                "case_id": case_name,
                "quote_id": value["quote_id"],
                "chapter_id": chapter_id,
                "candidate_offsets": starts,
                "selected_offset": starts[0],
            }
        )
    start = starts[0]
    return {
        "quote_id": value["quote_id"],
        "chapter_id": chapter_id,
        "text": resolved_text,
        "start_offset": start,
        "end_offset": start + len(resolved_text),
        "source_hash": sources[chapter_id]["hash"],
    }


def _convert_negative(value: dict[str, Any]) -> dict[str, Any]:
    return NegativeCase(
        negative_case_id=value["negative_case_id"],
        knowledge_type=value["knowledge_type"],
        accepted_names=value["accepted_names"],
        reason=value["reason"],
        source_quote_ids=value["source_quote_ids"],
    ).model_dump(mode="json")


def _convert_rules(value: dict[str, Any]) -> dict[str, Any]:
    return EvaluationRules(
        field_weights=value["field_weights"],
        reference_identity_map=value["reference_identity_map"],
        reference_fields=value["reference_fields"],
    ).model_dump(mode="json")


def _load_sources(source_root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for chapter in manifest["chapters"]:
        path = source_root / chapter["markdown_path"]
        text = path.read_text(encoding="utf-8")
        result[str(chapter["id"])] = {
            "text": text,
            "hash": sha256(text.encode("utf-8")).hexdigest(),
        }
    return result


def _package_root(archive: ZipFile) -> str:
    roots = {Path(name).parts[0] for name in archive.namelist() if name}
    if len(roots) != 1:
        raise ValueError("标注 ZIP 必须只有一个顶层目录")
    return roots.pop()


def _read_zip_json(archive: ZipFile, name: str) -> dict[str, Any]:
    with archive.open(name) as stream:
        return json.load(stream)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_checksums(dataset_root: Path) -> None:
    checksum_path = dataset_root / "_metadata/checksums.sha256.json"
    values = {
        path.relative_to(dataset_root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(dataset_root.rglob("*"))
        if path.is_file() and path != checksum_path
    }
    _write_json(checksum_path, values)


def _all_starts(value: str, needle: str) -> list[int]:
    starts: list[int] = []
    cursor = 0
    while True:
        position = value.find(needle, cursor)
        if position < 0:
            return starts
        starts.append(position)
        cursor = position + 1


def _normalized_spans(value: str, needle: str) -> list[tuple[int, int]]:
    normalized_value, index_map = _normalized_with_index_map(value)
    normalized_needle, _ = _normalized_with_index_map(needle)
    spans: list[tuple[int, int]] = []
    for start in _all_starts(normalized_value, normalized_needle):
        end_index = start + len(normalized_needle) - 1
        spans.append((index_map[start], index_map[end_index] + 1))
    return spans


def _normalized_with_index_map(value: str) -> tuple[str, list[int]]:
    quote_characters = frozenset({"‘", "’", "“", "”", "'"})
    ignored_characters = frozenset({"【", "】"})
    characters: list[str] = []
    index_map: list[int] = []
    for index, character in enumerate(value):
        if character in ignored_characters or character.isspace():
            continue
        characters.append('"' if character in quote_characters else character)
        index_map.append(index)
    return "".join(characters), index_map


if __name__ == "__main__":
    main()
