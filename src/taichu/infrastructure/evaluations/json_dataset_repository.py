"""Safe JSON repository for knowledge-extraction evaluation datasets."""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from pydantic import ValidationError

from taichu.application.evaluations.knowledge_extraction.dataset import (
    DatasetValidationIssue,
    DatasetValidationResult,
    EvaluationDatasetSummary,
    LoadedEvaluationCase,
    LoadedEvaluationDataset,
)
from taichu.application.evaluations.knowledge_extraction.models import (
    DatasetManifest,
    EvaluationLifecycle,
    EvaluationRules,
    ExpectedCard,
    NegativeCase,
    SourceEvidence,
)
from taichu.application.evaluations.knowledge_extraction.normalization import (
    normalize_identity,
)


_DATASET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_CHAPTER_ID_PATTERN = re.compile(r"^chapter-[a-z0-9][a-z0-9_-]{5,127}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_JOINED_NEGATIVE_NAME_PATTERN = re.compile(r"、")


class JsonEvaluationDatasetRepository:
    """Discover and validate registered datasets under one configured root."""

    def __init__(self, datasets_root: Path, source_root: Path) -> None:
        self._root = datasets_root.resolve()
        self._source_root = source_root.resolve()

    async def list_datasets(
        self,
        *,
        include_non_confirmed: bool = False,
    ) -> list[EvaluationDatasetSummary]:
        """Return compact summaries; invalid data never leaks local paths."""
        return await asyncio.to_thread(
            self._list_datasets_sync,
            include_non_confirmed,
        )

    async def validate_dataset(self, dataset_id: str) -> DatasetValidationResult:
        """Return all validation issues that can be found for one dataset."""
        return await asyncio.to_thread(self._validate_dataset_sync, dataset_id)

    async def get_dataset(self, dataset_id: str) -> LoadedEvaluationDataset:
        """Load one confirmed dataset or raise a stable repository error."""
        return await asyncio.to_thread(self._get_dataset_sync, dataset_id)

    def _list_datasets_sync(
        self,
        include_non_confirmed: bool,
    ) -> list[EvaluationDatasetSummary]:
        if not self._root.exists():
            return []
        summaries: list[EvaluationDatasetSummary] = []
        for directory in sorted(self._root.iterdir(), key=lambda path: path.name):
            if not directory.is_dir() or not _DATASET_ID_PATTERN.fullmatch(
                directory.name
            ):
                continue
            result = self._validate_dataset_sync(directory.name)
            manifest = _try_read_manifest(directory / "manifest.json")
            if manifest is None:
                if include_non_confirmed:
                    summaries.append(
                        EvaluationDatasetSummary(
                            dataset_id=directory.name,
                            label=directory.name,
                            lifecycle=EvaluationLifecycle.DRAFT,
                            case_count=0,
                            valid=False,
                            issues=result.issues,
                        )
                    )
                continue
            if not include_non_confirmed and (
                manifest.lifecycle is not EvaluationLifecycle.CONFIRMED
                or not result.valid
            ):
                continue
            summaries.append(
                EvaluationDatasetSummary(
                    dataset_id=manifest.dataset_id,
                    label=manifest.label,
                    lifecycle=manifest.lifecycle,
                    case_count=len(manifest.cases),
                    valid=result.valid,
                    checksum=result.checksum,
                    issues=result.issues,
                )
            )
        return summaries

    def _validate_dataset_sync(self, dataset_id: str) -> DatasetValidationResult:
        try:
            loaded = self._load_dataset_sync(dataset_id, require_confirmed=False)
        except EvaluationDatasetRepositoryError as error:
            return DatasetValidationResult(
                dataset_id=dataset_id,
                valid=False,
                lifecycle=error.lifecycle,
                issues=[
                    DatasetValidationIssue(
                        code=error.code,
                        message=str(error),
                        path=error.relative_path,
                    )
                ],
            )
        return DatasetValidationResult(
            dataset_id=dataset_id,
            valid=True,
            lifecycle=loaded.manifest.lifecycle,
            checksum=loaded.checksum,
        )

    def _get_dataset_sync(self, dataset_id: str) -> LoadedEvaluationDataset:
        return self._load_dataset_sync(dataset_id, require_confirmed=True)

    def _load_dataset_sync(
        self,
        dataset_id: str,
        *,
        require_confirmed: bool,
    ) -> LoadedEvaluationDataset:
        _validate_identifier(dataset_id, _DATASET_ID_PATTERN, "评测集")
        dataset_root = _safe_child(self._root, dataset_id)
        if not dataset_root.is_dir():
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_NOT_FOUND",
                "未找到指定评测集。",
            )
        manifest_path = _safe_relative(dataset_root, "manifest.json")
        try:
            manifest = DatasetManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as error:
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_INVALID",
                "评测集清单格式不正确。",
                relative_path="manifest.json",
            ) from error
        if manifest.dataset_id != dataset_id:
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_INVALID",
                "评测集目录与清单标识不一致。",
                lifecycle=manifest.lifecycle,
                relative_path="manifest.json",
            )
        if (
            require_confirmed
            and manifest.lifecycle is not EvaluationLifecycle.CONFIRMED
        ):
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_INVALID",
                "评测集尚未确认，不能开始正式评估。",
                lifecycle=manifest.lifecycle,
            )
        checksum_path = _safe_relative(
            dataset_root,
            manifest.checksum_manifest_path,
        )
        checksum_records = _read_checksum_manifest(checksum_path)
        _validate_checksum_records(dataset_root, checksum_records)
        referenced_paths = [
            "manifest.json",
            manifest.schema_snapshot_path,
            *[
                value
                for case in manifest.cases
                for value in (
                    case.expected_cards_path,
                    case.evaluation_rules_path,
                    case.source_evidence_path,
                    case.negative_cases_path,
                )
            ],
        ]
        for relative_path in referenced_paths:
            _safe_relative(dataset_root, relative_path)
        _require_checksummed(
            checksum_records,
            referenced_paths,
        )
        chapter_sources = _load_chapter_sources(self._source_root)
        loaded_cases: dict[str, LoadedEvaluationCase] = {}
        for case_ref in manifest.cases:
            _validate_identifier(case_ref.case_id, _CASE_ID_PATTERN, "case")
            for chapter_id in case_ref.chapter_ids:
                _validate_identifier(chapter_id, _CHAPTER_ID_PATTERN, "章节")
            expected_cards = _load_list(
                dataset_root,
                case_ref.expected_cards_path,
                ExpectedCard,
            )
            rules = _load_model(
                dataset_root,
                case_ref.evaluation_rules_path,
                EvaluationRules,
            )
            source_evidence = _load_list(
                dataset_root,
                case_ref.source_evidence_path,
                SourceEvidence,
            )
            negative_cases = _load_list(
                dataset_root,
                case_ref.negative_cases_path,
                NegativeCase,
            )
            _validate_case_content(
                case_ref=case_ref,
                expected_cards=expected_cards,
                source_evidence=source_evidence,
                negative_cases=negative_cases,
                chapter_sources=chapter_sources,
            )
            case_paths = (
                case_ref.expected_cards_path,
                case_ref.evaluation_rules_path,
                case_ref.source_evidence_path,
                case_ref.negative_cases_path,
            )
            case_checksum = _hash_text(
                "".join(checksum_records[path] for path in case_paths)
            )
            loaded_cases[case_ref.case_id] = LoadedEvaluationCase(
                ref=case_ref,
                expected_cards=expected_cards,
                rules=rules,
                source_evidence=source_evidence,
                negative_cases=negative_cases,
                checksum=case_checksum,
            )
        dataset_checksum = _hash_text(
            json.dumps(
                checksum_records,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return LoadedEvaluationDataset(
            manifest=manifest,
            cases=loaded_cases,
            checksum=dataset_checksum,
        )


class EvaluationDatasetRepositoryError(ValueError):
    """Stable error raised for unsafe or invalid evaluation datasets."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        lifecycle: EvaluationLifecycle | None = None,
        relative_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.lifecycle = lifecycle
        self.relative_path = relative_path


def _try_read_manifest(path: Path) -> DatasetManifest | None:
    try:
        return DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None


def _load_model(dataset_root: Path, relative_path: str, model_type: type[Any]) -> Any:
    path = _safe_relative(dataset_root, relative_path)
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_DATASET_INVALID",
            "评测集文件格式不正确。",
            relative_path=relative_path,
        ) from error


def _load_list(
    dataset_root: Path, relative_path: str, model_type: type[Any]
) -> list[Any]:
    path = _safe_relative(dataset_root, relative_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("dataset payload must be a list")
        return [model_type.model_validate(item) for item in payload]
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_DATASET_INVALID",
            "评测集列表文件格式不正确。",
            relative_path=relative_path,
        ) from error


def _read_checksum_manifest(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_DATASET_INVALID",
            "评测集校验清单无法读取。",
        ) from error
    if not isinstance(payload, dict):
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_DATASET_INVALID",
            "评测集校验清单必须是对象。",
        )
    records: dict[str, str] = {}
    for raw_path, raw_digest in payload.items():
        relative_path = str(raw_path).replace("\\", "/")
        digest = str(raw_digest).lower()
        if not _SHA256_PATTERN.fullmatch(digest):
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_INVALID",
                "评测集校验值格式不正确。",
                relative_path=relative_path,
            )
        records[relative_path] = digest
    return records


def _validate_checksum_records(root: Path, records: dict[str, str]) -> None:
    for relative_path, expected in records.items():
        path = _safe_relative(root, relative_path)
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_INVALID",
                "评测集文件校验值不一致。",
                relative_path=relative_path,
            )


def _require_checksummed(records: dict[str, str], paths: list[str]) -> None:
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized not in records:
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_INVALID",
                "评测集引用的文件未登记校验值。",
                relative_path=normalized,
            )


def _load_chapter_sources(source_root: Path) -> dict[str, tuple[str, str]]:
    manifest_path = _safe_relative(source_root, "manuscripts/manifest.json")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        chapters = payload["chapters"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_SOURCE_CHANGED",
            "正文清单无法读取。",
        ) from error
    result: dict[str, tuple[str, str]] = {}
    for chapter in chapters:
        chapter_id = str(chapter["id"])
        markdown_path = _safe_relative(source_root, str(chapter["markdown_path"]))
        markdown = markdown_path.read_text(encoding="utf-8")
        result[chapter_id] = (markdown, _hash_text(markdown))
    return result


def _validate_case_content(
    *,
    case_ref: Any,
    expected_cards: list[ExpectedCard],
    source_evidence: list[SourceEvidence],
    negative_cases: list[NegativeCase],
    chapter_sources: dict[str, tuple[str, str]],
) -> None:
    expected_ids = [card.expected_card_id for card in expected_cards]
    if len(expected_ids) != len(set(expected_ids)):
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_DATASET_INVALID",
            "评测 case 中存在重复期望卡。",
        )
    quote_by_id = {quote.quote_id: quote for quote in source_evidence}
    if len(quote_by_id) != len(source_evidence):
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_DATASET_INVALID",
            "评测 case 中存在重复证据标识。",
        )
    for chapter_id, expected_hash in case_ref.source_chapter_hashes.items():
        source = chapter_sources.get(chapter_id)
        if source is None or source[1] != expected_hash:
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_SOURCE_CHANGED",
                "评测集登记的正文与当前正文不一致。",
            )
    for quote in source_evidence:
        source = chapter_sources.get(quote.chapter_id)
        if source is None or quote.chapter_id not in case_ref.chapter_ids:
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_INVALID",
                "证据引用了评测范围外的章节。",
            )
        markdown, source_hash = source
        if quote.source_hash != source_hash:
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_SOURCE_CHANGED",
                "证据来源哈希与当前正文不一致。",
            )
        if (
            quote.end_offset > len(markdown)
            or markdown[quote.start_offset : quote.end_offset] != quote.text
        ):
            raise EvaluationDatasetRepositoryError(
                "EVALUATION_DATASET_INVALID",
                "证据原文无法在正文中精确定位。",
            )
    known_quotes = set(quote_by_id)
    accepted_owner: dict[tuple[str, str], str] = {}
    for card in expected_cards:
        _require_quote_ids(card.source_quote_ids, known_quotes)
        for claim in card.expected_claims:
            _require_quote_ids(claim.source_quote_ids, known_quotes)
        for name in card.accepted_names:
            key = (card.knowledge_type.value, normalize_identity(name))
            previous = accepted_owner.get(key)
            if previous is not None and previous != card.expected_card_id:
                raise EvaluationDatasetRepositoryError(
                    "EVALUATION_DATASET_INVALID",
                    "同类型期望卡的可接受名称发生冲突。",
                )
            accepted_owner[key] = card.expected_card_id
    negative_ids = [item.negative_case_id for item in negative_cases]
    if len(negative_ids) != len(set(negative_ids)):
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_DATASET_INVALID",
            "评测 case 中存在重复负样本。",
        )
    for item in negative_cases:
        _require_quote_ids(item.source_quote_ids, known_quotes)
        normalized_names: set[str] = set()
        for name in item.accepted_names:
            normalized = normalize_identity(name)
            if not normalized or _JOINED_NEGATIVE_NAME_PATTERN.search(name):
                raise EvaluationDatasetRepositoryError(
                    "EVALUATION_DATASET_INVALID",
                    "负样本的每个可接受名称必须单独填写，不能用顿号合写。",
                )
            if normalized in normalized_names:
                raise EvaluationDatasetRepositoryError(
                    "EVALUATION_DATASET_INVALID",
                    "同一负样本中存在重复的可接受名称。",
                )
            normalized_names.add(normalized)


def _require_quote_ids(values: list[str], known_quotes: set[str]) -> None:
    if not set(values).issubset(known_quotes):
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_DATASET_INVALID",
            "评测规则引用了不存在的证据标识。",
        )


def _validate_identifier(value: str, pattern: re.Pattern[str], label: str) -> None:
    if not pattern.fullmatch(value):
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_ID_INVALID",
            f"{label}标识格式不正确。",
        )


def _safe_child(root: Path, child: str) -> Path:
    return _ensure_within(root, root / child)


def _safe_relative(root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_ID_INVALID",
            "评测集路径不安全。",
        )
    return _ensure_within(root, root / path)


def _ensure_within(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise EvaluationDatasetRepositoryError(
            "EVALUATION_ID_INVALID",
            "评测集路径不安全。",
        ) from error
    return resolved


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
