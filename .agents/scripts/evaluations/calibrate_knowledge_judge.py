"""Run and gate the human-labelled knowledge-judge calibration suite.

This command intentionally stays outside normal CI: ``run`` calls the configured
evaluation judge and therefore can consume network and model quota.  ``check`` is
the non-network release gate; it only verifies a previously confirmed report and
the locally configured judge identity.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
from typing import Any, Literal, Protocol, Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from taichu.application.contracts.evaluation_judge import EvaluationJudge
from taichu.application.contracts.llm import LLMModelIdentity
from taichu.application.evaluations.knowledge_extraction.judge import (
    PROMPT_CONTRACT_ID,
    JudgeBatchOutput,
    JudgeDimensionResult,
    JudgeInputCase,
    JudgeItem,
    JudgeStatus,
    aggregate_judge_samples,
    build_judge_prompt,
    prompt_contract_hash,
    semantic_score,
    validate_judge_output,
)
from taichu.application.evaluations.knowledge_extraction.metrics import (
    semantic_quality_state,
)
from taichu.application.evaluations.knowledge_extraction.models import (
    EvaluationLifecycle,
    ExpectedClaim,
    QualityState,
    SemanticQualityInputs,
    SourceEvidence,
)
from taichu.config import Settings
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT_ROOT = (
    REPOSITORY_ROOT
    / "project_assets"
    / "derived"
    / "agent_evaluations"
    / "knowledge_extraction"
    / "calibration_reports"
)
REPORT_ID_PATTERN = re.compile(r"^judge_calibration_\d{8}_\d{6}_[a-z0-9]{6}$")
CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,95}$")
CALIBRATION_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,95}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ERROR_MODES = (
    "correct",
    "omission",
    "hallucination",
    "contradiction",
    "future_leakage",
    "wrong_merge",
)
REQUIRED_DIMENSIONS = (
    "factual_fidelity",
    "key_fact_coverage",
    "evidence_grounding",
    "scope_discipline",
    "knowledge_usability",
)
OPTIONAL_DIMENSIONS = ("aggregation_integrity",)
THRESHOLDS = {
    "semantic_quality_state_accuracy": 0.85,
    "critical_issue_recall": 1.0,
    "verdict_consistency": 0.90,
    "dimension_mean_absolute_error": 0.75,
}


class CalibrationError(RuntimeError):
    """Base class for configuration, input, or execution failures."""


class ReportCorruptedError(CalibrationError):
    """Raised when persisted report material fails its integrity contract."""


class GateNotPassedError(CalibrationError):
    """Raised when intact material does not satisfy a calibration gate."""


class CalibrationModel(BaseModel):
    """Strict immutable base model for calibration-only metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CalibrationScope(StrEnum):
    """Supported semantic calibration scopes."""

    SINGLE_CHAPTER = "single_chapter"
    CHAPTER_BATCH = "chapter_batch"


class HumanCriticalFinding(CalibrationModel):
    """Human-adjudicated critical finding identity."""

    kind: str = Field(min_length=1)
    field: str = Field(min_length=1)
    claim_id: str | None = None


class HumanLabel(CalibrationModel):
    """Adjudicated semantic label; draft seeds deliberately leave it empty."""

    lifecycle: EvaluationLifecycle = EvaluationLifecycle.DRAFT
    status: JudgeStatus | None = None
    dimension_scores: dict[str, int | None] = Field(default_factory=dict)
    expected_semantic_quality_state: QualityState | None = None
    critical_findings: list[HumanCriticalFinding] = Field(default_factory=list)
    critical_flag_codes: list[str] = Field(default_factory=list)
    reviewer_ids: list[str] = Field(default_factory=list)
    adjudication_note: str | None = None

    @model_validator(mode="after")
    def _confirmed_label_is_complete(self) -> Self:
        allowed = set(REQUIRED_DIMENSIONS + OPTIONAL_DIMENSIONS)
        if not set(self.dimension_scores).issubset(allowed):
            raise ValueError("人工标签包含未知评分维度。")
        for score in self.dimension_scores.values():
            if score is not None and not 0 <= score <= 4:
                raise ValueError("人工维度分必须在 0 到 4 之间。")
        if len(self.reviewer_ids) != len(set(self.reviewer_ids)):
            raise ValueError("人工标签的复核人不能重复。")
        if self.lifecycle is not EvaluationLifecycle.CONFIRMED:
            return self
        if len(self.reviewer_ids) < 2:
            raise ValueError("确认标签必须包含两名独立复核人。")
        if self.status is None or self.expected_semantic_quality_state is None:
            raise ValueError("确认标签必须包含裁判状态与期望质量状态。")
        if not (self.adjudication_note or "").strip():
            raise ValueError("确认标签必须包含复核说明。")
        if self.status is JudgeStatus.SCORED:
            if not set(REQUIRED_DIMENSIONS).issubset(self.dimension_scores):
                raise ValueError("已评分标签缺少必需维度。")
        elif self.dimension_scores:
            raise ValueError("未评分人工标签不能包含维度分。")
        if self.expected_semantic_quality_state is QualityState.NOT_COMPARABLE:
            raise ValueError("确认校准标签不能以不可比较作为期望质量状态。")
        return self


class CalibrationCase(CalibrationModel):
    """One human-labelled pair converted into the production judge input."""

    calibration_case_id: str = Field(pattern=CASE_ID_PATTERN.pattern)
    knowledge_type: StructuredKnowledgeType
    scope_kind: CalibrationScope
    error_mode: Literal[
        "correct",
        "omission",
        "hallucination",
        "contradiction",
        "future_leakage",
        "wrong_merge",
    ]
    source_chapter_path: str = Field(min_length=1)
    expected_card: dict[str, Any]
    actual_card: dict[str, Any]
    expected_claims: list[ExpectedClaim] = Field(min_length=1)
    source_quotes: list[SourceEvidence] = Field(min_length=1)
    human_label: HumanLabel

    @model_validator(mode="after")
    def _cards_and_references_are_consistent(self) -> Self:
        for card_name, card in (
            ("expected_card", self.expected_card),
            ("actual_card", self.actual_card),
        ):
            if card.get("type") != self.knowledge_type.value:
                raise ValueError(f"{card_name}.type 与 knowledge_type 不一致。")
            if not isinstance(card.get("name"), str) or not card["name"].strip():
                raise ValueError(f"{card_name} 必须包含非空名称。")
        quote_ids = [quote.quote_id for quote in self.source_quotes]
        if len(quote_ids) != len(set(quote_ids)):
            raise ValueError("同一校准样本不能包含重复 quote_id。")
        known_quotes = set(quote_ids)
        claim_ids = [claim.claim_id for claim in self.expected_claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("同一校准样本不能包含重复 claim_id。")
        for claim in self.expected_claims:
            if not set(claim.source_quote_ids).issubset(known_quotes):
                raise ValueError("ExpectedClaim 引用了未知 quote_id。")
        return self


class HumanLabelProtocol(CalibrationModel):
    """Machine-checkable declaration of the human review workflow."""

    required_reviewers: int = Field(ge=2)
    independent_annotation: bool
    adjudication_required: bool
    seed_status: str = Field(min_length=1)
    instruction: str = Field(min_length=1)


class CalibrationManifest(CalibrationModel):
    """Manifest for the manually reviewed semantic calibration bundle."""

    calibration_id: str = Field(pattern=CALIBRATION_ID_PATTERN.pattern)
    lifecycle: EvaluationLifecycle
    prompt_contract_id: str = Field(min_length=1)
    knowledge_types: list[StructuredKnowledgeType] = Field(min_length=1)
    error_modes: list[str] = Field(min_length=1)
    case_count: int = Field(ge=1)
    cases_path: str = Field(min_length=1)
    checksums_path: str = Field(min_length=1)
    annotations_path: str = Field(min_length=1)
    human_label_protocol: HumanLabelProtocol

    @model_validator(mode="after")
    def _lists_are_unique(self) -> Self:
        if len(self.knowledge_types) != len(set(self.knowledge_types)):
            raise ValueError("knowledge_types 不能重复。")
        if len(self.error_modes) != len(set(self.error_modes)):
            raise ValueError("error_modes 不能重复。")
        if not set(self.error_modes).issubset(ERROR_MODES):
            raise ValueError("manifest 包含未知错误模式。")
        return self


class CalibrationMetrics(CalibrationModel):
    """Four fixed, measured calibration gate values."""

    semantic_quality_state_accuracy: float = Field(ge=0, le=1)
    critical_issue_recall: float = Field(ge=0, le=1)
    verdict_consistency: float = Field(ge=0, le=1)
    dimension_mean_absolute_error: float = Field(ge=0, le=4)


class CalibrationReportSummary(CalibrationModel):
    """Integrity-protected calibration report summary."""

    calibration_report_id: str = Field(pattern=REPORT_ID_PATTERN.pattern)
    lifecycle: EvaluationLifecycle
    status: Literal["completed", "failed"]
    calibration_id: str = Field(min_length=1)
    manifest_checksum: str = Field(pattern=SHA256_PATTERN.pattern)
    dataset_checksum: str = Field(pattern=SHA256_PATTERN.pattern)
    prompt_contract_id: str = Field(min_length=1)
    prompt_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    judge_model_identity: LLMModelIdentity
    repetitions: int = Field(ge=3)
    metrics: CalibrationMetrics | None = None
    thresholds: dict[str, float]
    passed: bool
    warnings: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str]
    created_at: datetime
    confirmed_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    summary_hash: str = Field(pattern=SHA256_PATTERN.pattern)


class LoadedCalibrationBundle(CalibrationModel):
    """Validated material consumed by a real model run."""

    manifest_path: Path
    manifest: CalibrationManifest
    cases: list[CalibrationCase]
    annotations: dict[str, Any]
    manifest_checksum: str
    dataset_checksum: str


class JudgeFactory(Protocol):
    """Injectable factory used to keep unit tests offline."""

    def __call__(self) -> EvaluationJudge:
        """Create the configured judge adapter."""
        ...


def calibration_case_to_judge_input(case: CalibrationCase) -> JudgeInputCase:
    """Deterministically convert a calibration case into production input."""
    run_id = f"calibration_run_{case.calibration_case_id}"
    review_item_id = f"calibration_review_{case.calibration_case_id}"
    expected_card_id = f"calibration_expected_{case.calibration_case_id}"
    result = JudgeInputCase(
        case_id=f"{run_id}::{review_item_id}::{expected_card_id}",
        run_id=run_id,
        expected_card_id=expected_card_id,
        actual_review_item_id=review_item_id,
        knowledge_type=case.knowledge_type.value,
        expected_fields=case.expected_card,
        actual_fields=case.actual_card,
        expected_claims=[
            claim.model_dump(mode="json") for claim in case.expected_claims
        ],
        source_quotes=[quote.model_dump(mode="json") for quote in case.source_quotes],
        deterministic_diff={"calibration_error_mode": case.error_mode},
    )
    # A second validation through the production schema guards accidental drift.
    return JudgeInputCase.model_validate(result.model_dump(mode="json"))


def current_prompt_hash() -> str:
    """Return the production-owned Prompt contract fingerprint."""
    return prompt_contract_hash()


def load_calibration_bundle(
    manifest_path: Path,
    *,
    require_confirmed: bool = True,
) -> LoadedCalibrationBundle:
    """Load, checksum, and validate all calibration material fail-closed."""
    path = manifest_path.resolve()
    if not path.is_file():
        raise CalibrationError("校准 manifest 不存在。")
    root = path.parent
    try:
        manifest = CalibrationManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise CalibrationError("校准 manifest 格式不正确。") from exc
    if manifest.prompt_contract_id != PROMPT_CONTRACT_ID:
        raise CalibrationError("校准集的 Prompt 契约与当前实现不一致。")
    if require_confirmed and manifest.lifecycle is not EvaluationLifecycle.CONFIRMED:
        raise CalibrationError("校准集尚未完成人工复核，不能调用真实裁判。")

    cases_path = _safe_relative_file(root, manifest.cases_path)
    checksums_path = _safe_relative_file(root, manifest.checksums_path)
    annotations_path = _safe_relative_file(root, manifest.annotations_path)
    try:
        raw_cases = _read_json(cases_path)
        annotations = _read_json(annotations_path)
        checksum_records = _read_json(checksums_path)
        cases = [CalibrationCase.model_validate(item) for item in raw_cases]
    except (OSError, ValidationError, ValueError, TypeError) as exc:
        raise CalibrationError("校准样本或标注元数据格式不正确。") from exc
    if not isinstance(checksum_records, dict):
        raise CalibrationError("校准 checksum 文件格式不正确。")

    material_paths = {cases_path, annotations_path}
    sources_root = (root / "sources").resolve()
    if not sources_root.is_dir() or not sources_root.is_relative_to(root):
        raise CalibrationError("校准集缺少安全的 sources 目录。")
    material_paths.update(
        item.resolve() for item in sources_root.rglob("*") if item.is_file()
    )
    expected_relative = {item.relative_to(root).as_posix() for item in material_paths}
    if set(checksum_records) != expected_relative:
        raise CalibrationError("校准 checksum 清单与实际材料不一致。")
    for relative, expected in checksum_records.items():
        if not isinstance(expected, str) or not SHA256_PATTERN.fullmatch(expected):
            raise CalibrationError("校准 checksum 值格式不正确。")
        material = _safe_relative_file(root, relative)
        if _hash_bytes(material.read_bytes()) != expected:
            raise CalibrationError(f"校准材料哈希不匹配：{relative}")

    if len(cases) != manifest.case_count:
        raise CalibrationError("manifest 登记的样本数与 cases.json 不一致。")
    case_ids = [case.calibration_case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise CalibrationError("校准 case 标识必须全局唯一。")
    if set(case.knowledge_type for case in cases) != set(manifest.knowledge_types):
        raise CalibrationError("校准样本类型覆盖与 manifest 不一致。")
    if set(case.error_mode for case in cases) != set(manifest.error_modes):
        raise CalibrationError("校准错误模式覆盖与 manifest 不一致。")
    if require_confirmed:
        _validate_confirmed_annotations(cases, annotations, manifest)
    for case in cases:
        _validate_source_evidence(root, case)
        first = calibration_case_to_judge_input(case)
        second = calibration_case_to_judge_input(case)
        if _canonical_json(first.model_dump(mode="json")) != _canonical_json(
            second.model_dump(mode="json")
        ):
            raise CalibrationError("校准样本转换结果不稳定。")

    normalized_checksums = "\n".join(
        f"{key}:{checksum_records[key]}" for key in sorted(checksum_records)
    )
    return LoadedCalibrationBundle(
        manifest_path=path,
        manifest=manifest,
        cases=cases,
        annotations=annotations,
        manifest_checksum=_hash_bytes(path.read_bytes()),
        dataset_checksum=_hash_text(normalized_checksums),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    judge_factory: JudgeFactory | None = None,
) -> int:
    """Execute the CLI and return its fixed 0/1/2 exit code."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    factory = judge_factory or _default_judge_factory
    try:
        if args.command == "run":
            return asyncio.run(
                _run_command(
                    Path(args.manifest),
                    repetitions=args.repetitions,
                    report_root=Path(args.report_root),
                    judge_factory=factory,
                )
            )
        if args.command == "confirm":
            return _confirm_command(
                args.report_id,
                report_root=Path(args.report_root),
                judge_factory=factory,
            )
        if args.command == "reject":
            return _reject_command(
                args.report_id,
                reason=args.reason,
                report_root=Path(args.report_root),
            )
        if args.command == "check":
            return _check_command(
                args.report_id,
                report_root=Path(args.report_root),
                judge_factory=factory,
            )
    except ReportCorruptedError as exc:
        print(f"校准报告损坏：{exc}", file=sys.stderr)
        return 2
    except GateNotPassedError as exc:
        print(f"校准门禁未通过：{exc}", file=sys.stderr)
        return 1
    except (CalibrationError, OSError, ValidationError, ValueError) as exc:
        print(f"校准执行失败：{exc}", file=sys.stderr)
        return 2
    print("未知校准命令。", file=sys.stderr)
    return 2


async def _run_command(
    manifest_path: Path,
    *,
    repetitions: int,
    report_root: Path,
    judge_factory: JudgeFactory,
) -> int:
    if repetitions < 3:
        raise CalibrationError("真实校准至少需要三次重复裁判。")
    bundle = load_calibration_bundle(manifest_path)
    judge = judge_factory()
    if not judge.available:
        raise CalibrationError("语义裁判未配置，未发起真实模型调用。")
    model_identity = judge.model_identity
    if not model_identity.known:
        raise CalibrationError("语义裁判模型身份未知，不能执行校准。")

    report_id = _new_report_id()
    created_at = datetime.now(UTC)
    report_cases: list[dict[str, Any]] = []
    call_documents: dict[str, dict[str, Any]] = {}
    execution_errors: list[str] = []

    for case in bundle.cases:
        judge_input = calibration_case_to_judge_input(case)
        samples: list[JudgeItem] = []
        call_ids: list[str] = []
        for repetition in range(1, repetitions + 1):
            call_id = _call_id(report_id, case.calibration_case_id, repetition)
            call_ids.append(call_id)
            prompt = build_judge_prompt([judge_input])
            call: dict[str, Any] = {
                "call_id": call_id,
                "calibration_case_id": case.calibration_case_id,
                "repetition": repetition,
                "prompt": prompt,
                "prompt_hash": _hash_text(prompt),
                "judge_model_identity": model_identity.model_dump(mode="json"),
                "raw_response": None,
                "parsed_output": None,
                "error": None,
            }
            try:
                response = await judge.complete(
                    prompt,
                    output_schema=JudgeBatchOutput,
                )
                call["raw_response"] = response.raw_response
                call["judge_model_identity"] = response.model_identity.model_dump(
                    mode="json"
                )
                if response.model_identity != model_identity:
                    raise CalibrationError("裁判调用期间模型身份发生变化。")
                if not isinstance(response.output, JudgeBatchOutput):
                    raise CalibrationError("裁判返回了错误的结构化输出类型。")
                parsed = validate_judge_output(response.output, [judge_input])
                item = parsed.items[0]
                call["parsed_output"] = item.model_dump(mode="json")
                samples.append(item)
            except Exception as exc:  # noqa: BLE001 - audit every model failure
                call["error"] = f"{type(exc).__name__}: {exc}"
                execution_errors.append(
                    f"{case.calibration_case_id} 第 {repetition} 次裁判失败"
                )
            call_documents[f"judge_calls/{call_id}.json"] = call

        aggregated = (
            aggregate_judge_samples(samples[:3])
            if len(samples) == repetitions
            else None
        )
        report_cases.append(
            {
                "calibration_case": case.model_dump(mode="json"),
                "judge_input": judge_input.model_dump(mode="json"),
                "call_ids": call_ids,
                "aggregated_output": (
                    aggregated.model_dump(mode="json") if aggregated else None
                ),
            }
        )

    metrics = (
        None if execution_errors else _calculate_metrics(report_cases, call_documents)
    )
    passed = metrics is not None and _metrics_pass(metrics)
    warnings = list(dict.fromkeys(execution_errors))
    if metrics is not None and not passed:
        warnings.append("至少一项人工裁判校准阈值未达到。")
    summary = _persist_new_report(
        report_root=report_root,
        report_id=report_id,
        bundle=bundle,
        report_cases=report_cases,
        call_documents=call_documents,
        model_identity=model_identity,
        repetitions=repetitions,
        metrics=metrics,
        passed=passed,
        warnings=warnings,
        created_at=created_at,
        status="failed" if execution_errors else "completed",
    )
    print(
        f"校准报告已保存：{summary.calibration_report_id}，"
        f"人工确认状态：{summary.lifecycle.value}，通过：{summary.passed}"
    )
    if execution_errors:
        return 2
    return 0 if passed else 1


def _confirm_command(
    report_id: str,
    *,
    report_root: Path,
    judge_factory: JudgeFactory,
) -> int:
    report_dir, summary = _load_and_validate_report(report_root, report_id)
    if summary.lifecycle is not EvaluationLifecycle.DRAFT:
        raise GateNotPassedError("只有草稿报告可以确认。")
    _verify_current_gates(summary, judge_factory)
    if summary.status != "completed" or not summary.passed:
        raise GateNotPassedError("报告尚未达到全部校准阈值。")
    updated = summary.model_copy(
        update={
            "lifecycle": EvaluationLifecycle.CONFIRMED,
            "confirmed_at": datetime.now(UTC),
        }
    )
    _write_summary(report_dir, updated)
    print(f"校准报告已确认：{report_id}")
    return 0


def _reject_command(
    report_id: str,
    *,
    reason: str,
    report_root: Path,
) -> int:
    report_dir, summary = _load_and_validate_report(report_root, report_id)
    if summary.lifecycle is EvaluationLifecycle.REJECTED:
        raise GateNotPassedError("已废弃报告不可再次变更。")
    if not reason.strip():
        raise CalibrationError("废弃报告必须填写原因。")
    updated = summary.model_copy(
        update={
            "lifecycle": EvaluationLifecycle.REJECTED,
            "rejected_at": datetime.now(UTC),
            "rejection_reason": reason.strip(),
        }
    )
    _write_summary(report_dir, updated)
    print(f"校准报告已废弃：{report_id}")
    return 0


def _check_command(
    report_id: str,
    *,
    report_root: Path,
    judge_factory: JudgeFactory,
) -> int:
    _, summary = _load_and_validate_report(report_root, report_id)
    if summary.lifecycle is not EvaluationLifecycle.CONFIRMED:
        raise GateNotPassedError("报告尚未确认或已经废弃。")
    if summary.status != "completed" or not summary.passed:
        raise GateNotPassedError("报告没有通过全部校准阈值。")
    _verify_current_gates(summary, judge_factory)
    print(f"校准门禁通过：{report_id}")
    return 0


def _calculate_metrics(
    report_cases: list[dict[str, Any]],
    call_documents: dict[str, dict[str, Any]],
) -> CalibrationMetrics:
    state_matches = 0
    state_total = 0
    expected_critical: set[str] = set()
    found_critical: set[str] = set()
    consistent_dimensions = 0
    compared_dimensions = 0
    absolute_errors: list[float] = []

    calls_by_id = {
        document["call_id"]: document for document in call_documents.values()
    }
    for report_case in report_cases:
        case = CalibrationCase.model_validate(report_case["calibration_case"])
        aggregated_raw = report_case.get("aggregated_output")
        if aggregated_raw is None:
            continue
        aggregated = JudgeItem.model_validate(aggregated_raw)
        predicted_state = _semantic_state_for_item(aggregated)
        expected_state = case.human_label.expected_semantic_quality_state
        if expected_state is not None:
            state_total += 1
            state_matches += int(predicted_state is expected_state)

        expected_critical.update(_human_critical_keys(case.human_label))
        found_critical.update(_judge_critical_keys(aggregated))

        samples = [
            JudgeItem.model_validate(calls_by_id[call_id]["parsed_output"])
            for call_id in report_case["call_ids"]
            if calls_by_id[call_id]["parsed_output"] is not None
        ]
        dimension_names = sorted(
            set().union(*(_judge_dimensions(sample).keys() for sample in samples))
        )
        for dimension_name in dimension_names:
            verdicts = []
            for sample in samples:
                dimension = _judge_dimensions(sample).get(dimension_name)
                if dimension is not None:
                    verdicts.append(dimension.verdict.value)
            if len(verdicts) == len(samples) and verdicts:
                compared_dimensions += 1
                consistent_dimensions += int(len(set(verdicts)) == 1)

        for dimension_name, expected_score in case.human_label.dimension_scores.items():
            if expected_score is None or not aggregated.dimensions:
                continue
            predicted = _judge_dimensions(aggregated).get(dimension_name)
            if predicted is not None:
                absolute_errors.append(abs(predicted.score - expected_score))

    if state_total == 0:
        raise CalibrationError("校准报告没有可比较的人工质量状态。")
    if compared_dimensions == 0:
        raise CalibrationError("校准报告没有可比较的重复 verdict。")
    if not absolute_errors:
        raise CalibrationError("校准报告没有可比较的人工维度分。")
    critical_recall = (
        len(expected_critical & found_critical) / len(expected_critical)
        if expected_critical
        else 1.0
    )
    return CalibrationMetrics(
        semantic_quality_state_accuracy=round(state_matches / state_total, 4),
        critical_issue_recall=round(critical_recall, 4),
        verdict_consistency=round(
            consistent_dimensions / compared_dimensions,
            4,
        ),
        dimension_mean_absolute_error=round(
            sum(absolute_errors) / len(absolute_errors),
            4,
        ),
    )


def _semantic_state_for_item(item: JudgeItem) -> QualityState:
    if item.status is not JudgeStatus.SCORED:
        return QualityState.NEEDS_REVIEW
    return semantic_quality_state(
        SemanticQualityInputs(
            semantic_score=semantic_score(item),
            judge_coverage=1,
            critical_claims_covered=True,
            confirmed_hard_risk=bool(item.critical_flags),
            reference_conflict=False,
            has_formal_critical_flag=bool(item.critical_flags),
        )
    )


def _human_critical_keys(label: HumanLabel) -> set[str]:
    keys = {
        "finding:" + ":".join([finding.kind, finding.field, finding.claim_id or ""])
        for finding in label.critical_findings
    }
    keys.update(f"flag:{code}" for code in label.critical_flag_codes)
    return keys


def _judge_critical_keys(item: JudgeItem) -> set[str]:
    keys = {
        "finding:" + ":".join([finding.kind, finding.field, finding.claim_id or ""])
        for finding in item.findings
        if finding.severity == "critical"
    }
    keys.update(f"flag:{flag.code}" for flag in item.critical_flags)
    return keys


def _metrics_pass(metrics: CalibrationMetrics) -> bool:
    return (
        metrics.semantic_quality_state_accuracy
        >= THRESHOLDS["semantic_quality_state_accuracy"]
        and metrics.critical_issue_recall >= THRESHOLDS["critical_issue_recall"]
        and metrics.verdict_consistency >= THRESHOLDS["verdict_consistency"]
        and metrics.dimension_mean_absolute_error
        <= THRESHOLDS["dimension_mean_absolute_error"]
    )


def _persist_new_report(
    *,
    report_root: Path,
    report_id: str,
    bundle: LoadedCalibrationBundle,
    report_cases: list[dict[str, Any]],
    call_documents: dict[str, dict[str, Any]],
    model_identity: LLMModelIdentity,
    repetitions: int,
    metrics: CalibrationMetrics | None,
    passed: bool,
    warnings: list[str],
    created_at: datetime,
    status: Literal["completed", "failed"],
) -> CalibrationReportSummary:
    root = report_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    report_dir = _safe_report_dir(root, report_id)
    if report_dir.exists():
        raise CalibrationError("校准报告标识发生冲突。")
    temporary = root / f".{report_id}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    (temporary / "judge_calls").mkdir(parents=True)
    artifacts: dict[str, str] = {}
    cases_document = {
        "manifest": bundle.manifest.model_dump(mode="json"),
        "cases": report_cases,
    }
    cases_bytes = _render_json(cases_document)
    (temporary / "cases.json").write_bytes(cases_bytes)
    artifacts["cases.json"] = _hash_bytes(cases_bytes)
    for relative, document in sorted(call_documents.items()):
        payload = _render_json(document)
        destination = temporary / relative
        destination.write_bytes(payload)
        artifacts[relative] = _hash_bytes(payload)

    summary = CalibrationReportSummary(
        calibration_report_id=report_id,
        lifecycle=EvaluationLifecycle.DRAFT,
        status=status,
        calibration_id=bundle.manifest.calibration_id,
        manifest_checksum=bundle.manifest_checksum,
        dataset_checksum=bundle.dataset_checksum,
        prompt_contract_id=PROMPT_CONTRACT_ID,
        prompt_hash=current_prompt_hash(),
        judge_model_identity=model_identity,
        repetitions=repetitions,
        metrics=metrics,
        thresholds=THRESHOLDS,
        passed=passed,
        warnings=warnings,
        artifact_checksums=artifacts,
        created_at=created_at,
        summary_hash="0" * 64,
    )
    _write_summary(temporary, summary)
    os.replace(temporary, report_dir)
    return CalibrationReportSummary.model_validate_json(
        (report_dir / "summary.json").read_text(encoding="utf-8")
    )


def _load_and_validate_report(
    report_root: Path,
    report_id: str,
) -> tuple[Path, CalibrationReportSummary]:
    root = report_root.resolve()
    report_dir = _safe_report_dir(root, report_id)
    summary_path = report_dir / "summary.json"
    if not summary_path.is_file():
        raise ReportCorruptedError("报告不存在或缺少 summary.json。")
    try:
        summary = CalibrationReportSummary.model_validate_json(
            summary_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise ReportCorruptedError("summary.json 格式不正确。") from exc
    if summary.calibration_report_id != report_id:
        raise ReportCorruptedError("报告标识与目录不一致。")
    if _summary_hash(summary) != summary.summary_hash:
        raise ReportCorruptedError("summary.json 完整性校验失败。")
    expected_artifacts = set(summary.artifact_checksums)
    actual_artifacts = {
        "cases.json" if path.name == "cases.json" else f"judge_calls/{path.name}"
        for path in report_dir.rglob("*.json")
        if path.name != "summary.json"
    }
    if actual_artifacts != expected_artifacts:
        raise ReportCorruptedError("报告明细文件集合与摘要不一致。")
    for relative, expected_hash in summary.artifact_checksums.items():
        if not SHA256_PATTERN.fullmatch(expected_hash):
            raise ReportCorruptedError("报告明细哈希格式不正确。")
        artifact = _safe_relative_file(report_dir, relative)
        if _hash_bytes(artifact.read_bytes()) != expected_hash:
            raise ReportCorruptedError(f"报告明细哈希不匹配：{relative}")
    _validate_report_calls(report_dir, summary)
    if summary.thresholds != THRESHOLDS:
        raise ReportCorruptedError("报告阈值不是当前固定校准阈值。")
    if summary.metrics is None:
        if summary.passed:
            raise ReportCorruptedError("无实测指标的报告不能标记为通过。")
    elif _metrics_pass(summary.metrics) != summary.passed:
        raise ReportCorruptedError("报告通过标记与四项实测指标不一致。")
    return report_dir, summary


def _validate_report_calls(
    report_dir: Path,
    summary: CalibrationReportSummary,
) -> None:
    for relative in summary.artifact_checksums:
        if not relative.startswith("judge_calls/"):
            continue
        try:
            call = _read_json(_safe_relative_file(report_dir, relative))
            identity = LLMModelIdentity.model_validate(call["judge_model_identity"])
        except (KeyError, TypeError, ValidationError, ValueError) as exc:
            raise ReportCorruptedError("裁判调用审计记录格式不正确。") from exc
        if identity != summary.judge_model_identity:
            raise ReportCorruptedError("裁判调用模型身份与摘要不一致。")
        prompt = call.get("prompt")
        if not isinstance(prompt, str) or call.get("prompt_hash") != _hash_text(prompt):
            raise ReportCorruptedError("裁判调用 Prompt 哈希不匹配。")


def _verify_current_gates(
    summary: CalibrationReportSummary,
    judge_factory: JudgeFactory,
) -> None:
    if summary.prompt_contract_id != PROMPT_CONTRACT_ID:
        raise GateNotPassedError("Prompt 契约标识已经变化，需要重新校准。")
    if summary.prompt_hash != current_prompt_hash():
        raise GateNotPassedError("Prompt 契约内容已经变化，需要重新校准。")
    judge = judge_factory()
    if not judge.available or not judge.model_identity.known:
        raise GateNotPassedError("当前裁判不可用或模型身份未知。")
    if judge.model_identity != summary.judge_model_identity:
        raise GateNotPassedError("当前裁判模型身份与校准报告不一致。")


def _validate_confirmed_annotations(
    cases: list[CalibrationCase],
    annotations: dict[str, Any],
    manifest: CalibrationManifest,
) -> None:
    if not isinstance(annotations, dict):
        raise CalibrationError("annotations.json 必须是对象。")
    entries = annotations.get("cases")
    if not isinstance(entries, list):
        raise CalibrationError("annotations.json 缺少 cases。")
    by_id = {
        item.get("calibration_case_id"): item
        for item in entries
        if isinstance(item, dict)
    }
    if set(by_id) != {case.calibration_case_id for case in cases}:
        raise CalibrationError("人工标注元数据与校准 case 不一致。")
    required_reviewers = manifest.human_label_protocol.required_reviewers
    for case in cases:
        if case.human_label.lifecycle is not EvaluationLifecycle.CONFIRMED:
            raise CalibrationError(
                f"样本 {case.calibration_case_id} 尚未完成人工标签确认。"
            )
        entry = by_id[case.calibration_case_id]
        reviews = entry.get("independent_reviews")
        adjudication = entry.get("adjudication")
        if (
            not isinstance(reviews, list)
            or len(reviews) < required_reviewers
            or any(not isinstance(review, dict) for review in reviews)
        ):
            raise CalibrationError("每个样本必须至少有两份独立人工标注。")
        reviewer_ids = [review.get("reviewer_id") for review in reviews]
        if (
            len(reviewer_ids) < required_reviewers
            or len(reviewer_ids) != len(set(reviewer_ids))
            or any(review.get("status") != "completed" for review in reviews)
        ):
            raise CalibrationError("独立人工标注记录不完整或复核人重复。")
        if (
            not isinstance(adjudication, dict)
            or adjudication.get("status") != "confirmed"
        ):
            raise CalibrationError("人工标签尚未完成最终复核。")


def _validate_source_evidence(root: Path, case: CalibrationCase) -> None:
    source_path = _safe_relative_file(root, case.source_chapter_path)
    sources_root = (root / "sources").resolve()
    if not source_path.is_relative_to(sources_root):
        raise CalibrationError("source_chapter_path 必须位于 sources 目录。")
    markdown = source_path.read_text(encoding="utf-8")
    source_hash = _hash_text(markdown)
    for quote in case.source_quotes:
        if quote.source_hash != source_hash:
            raise CalibrationError("SourceEvidence 的正文哈希不匹配。")
        if (
            quote.end_offset > len(markdown)
            or markdown[quote.start_offset : quote.end_offset] != quote.text
        ):
            raise CalibrationError("SourceEvidence 无法在 Markdown 中精确复核。")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="知识沉淀语义裁判人工校准工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="执行真实裁判并生成草稿报告")
    run.add_argument("--manifest", required=True)
    run.add_argument("--repetitions", type=int, default=3)
    _add_report_root(run)
    for name, help_text in (
        ("confirm", "确认已经通过阈值的草稿报告"),
        ("check", "检查确认报告是否匹配当前裁判与 Prompt"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--report-id", required=True)
        _add_report_root(command)
    reject = subparsers.add_parser("reject", help="废弃草稿或确认报告")
    reject.add_argument("--report-id", required=True)
    reject.add_argument("--reason", default="人工复核未通过。")
    _add_report_root(reject)
    return parser


def _add_report_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-root", default=str(DEFAULT_REPORT_ROOT))


def _default_judge_factory() -> EvaluationJudge:
    # Kept lazy so offline checks and unit-test imports never initialize a model.
    from taichu.infrastructure.evaluations.judge_factory import (
        create_evaluation_judge,
    )
    from taichu.infrastructure.llm.adapter import GatewayChatModel
    from taichu.infrastructure.llm.catalog import LLMModelCatalog
    from taichu.infrastructure.llm.rightcode import RightCodeLLMGateway
    from taichu.infrastructure.llm_replays import JsonLLMCallReplayRepository
    from taichu.infrastructure.llm_usage import JsonlLLMUsageRepository

    settings = Settings()
    gateway = RightCodeLLMGateway(
        settings,
        LLMModelCatalog(settings),
        JsonlLLMUsageRepository(settings.project_assets_dir),
        replay_repository=JsonLLMCallReplayRepository(settings.project_assets_dir),
    )
    return create_evaluation_judge(
        settings,
        GatewayChatModel(gateway, model_id=gateway.default_model_id),
        gateway,
        configured=gateway.configured,
    )


def _judge_dimensions(
    item: JudgeItem,
) -> dict[str, JudgeDimensionResult | None]:
    return cast(
        dict[str, JudgeDimensionResult | None],
        item.dimensions or {},
    )


def _write_summary(
    report_dir: Path,
    summary: CalibrationReportSummary,
) -> None:
    unsigned = summary.model_copy(update={"summary_hash": "0" * 64})
    signed = unsigned.model_copy(update={"summary_hash": _summary_hash(unsigned)})
    _atomic_write(
        report_dir / "summary.json", _render_json(signed.model_dump(mode="json"))
    )


def _summary_hash(summary: CalibrationReportSummary) -> str:
    payload = summary.model_dump(mode="json")
    payload.pop("summary_hash", None)
    return _hash_bytes(_canonical_json(payload))


def _safe_report_dir(root: Path, report_id: str) -> Path:
    if not REPORT_ID_PATTERN.fullmatch(report_id):
        raise CalibrationError("calibration_report_id 格式不正确。")
    candidate = (root / report_id).resolve()
    if candidate.parent != root:
        raise CalibrationError("calibration_report_id 不能越过报告目录。")
    return candidate


def _safe_relative_file(root: Path, raw_path: str) -> Path:
    value = Path(raw_path)
    if value.is_absolute():
        raise CalibrationError("校准材料路径必须是相对路径。")
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        raise CalibrationError("校准材料路径不存在或越过根目录。")
    return candidate


def _new_report_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"judge_calibration_{timestamp}_{secrets.token_hex(3)}"


def _call_id(report_id: str, case_id: str, repetition: int) -> str:
    digest = _hash_text(f"{report_id}:{case_id}:{repetition}")[:12]
    return f"judge_call_{digest}"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_json(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{secrets.token_hex(4)}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _hash_text(value: str) -> str:
    return _hash_bytes(value.encode())


def _hash_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
