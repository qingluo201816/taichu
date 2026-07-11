"""Offline tests for the explicit knowledge-judge calibration command."""

from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from taichu.application.contracts.evaluation_judge import (
    EvaluationJudgeResponse,
)
from taichu.application.contracts.llm import LLMModelIdentity
from taichu.application.evaluations.knowledge_extraction.judge import (
    JudgeInputCase,
)
from taichu.application.evaluations.knowledge_extraction.models import (
    ExpectedClaim,
    SourceEvidence,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "taichu_calibrate_knowledge_judge",
    REPOSITORY_ROOT / "scripts" / "evaluations" / "calibrate_knowledge_judge.py",
)
assert _SPEC is not None and _SPEC.loader is not None
calibration = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = calibration
_SPEC.loader.exec_module(calibration)


class FakeEvaluationJudge:
    """Deterministic judge used without network access or model quota."""

    def __init__(
        self,
        *,
        score: int = 4,
        model_id: str = "judge-test",
        available: bool = True,
        invalid_output: bool = False,
    ) -> None:
        self.score = score
        self.available = available
        self.invalid_output = invalid_output
        self.model_identity = LLMModelIdentity(
            provider="fake",
            model_id=model_id,
            family="fake-judge",
            endpoint_kind="offline",
            known=True,
        )

    async def complete(self, prompt: str) -> EvaluationJudgeResponse:
        if self.invalid_output:
            raw = "这不是 JSON"
        else:
            case = _prompt_case(prompt)
            verdict = "equivalent" if self.score == 4 else "contradictory"
            quote_id = case["source_quotes"][0]["quote_id"]
            dimensions = {
                name: {
                    "score": self.score,
                    "verdict": verdict,
                    "quote_ids": [quote_id],
                    "reason": "离线校准测试。",
                }
                for name in calibration.REQUIRED_DIMENSIONS
            }
            raw = json.dumps(
                {
                    "items": [
                        {
                            "case_id": case["case_id"],
                            "expected_card_id": case["expected_card_id"],
                            "actual_review_item_id": case["actual_review_item_id"],
                            "status": "scored",
                            "dimensions": dimensions,
                            "findings": [],
                            "critical_flags": [],
                            "reference_issues": [],
                            "missing_quote_ids": [],
                            "confidence": 0.95,
                            "reason": None,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        return EvaluationJudgeResponse(
            raw_response=raw,
            model_identity=self.model_identity,
        )


def test_case_conversion_reuses_production_schemas_and_is_stable(
    tmp_path: Path,
) -> None:
    manifest = _write_bundle(tmp_path / "dataset")
    loaded = calibration.load_calibration_bundle(manifest)
    case = loaded.cases[0]

    first = calibration.calibration_case_to_judge_input(case)
    second = calibration.calibration_case_to_judge_input(case)

    assert isinstance(case.expected_claims[0], ExpectedClaim)
    assert isinstance(case.source_quotes[0], SourceEvidence)
    assert isinstance(first, JudgeInputCase)
    assert first.model_dump_json() == second.model_dump_json()


def test_run_creates_passing_draft_then_confirm_check_and_reject(
    tmp_path: Path,
) -> None:
    manifest = _write_bundle(tmp_path / "dataset")
    reports = tmp_path / "reports"
    judge = FakeEvaluationJudge()

    assert _run(manifest, reports, judge) == 0
    report_id = _only_report_id(reports)
    summary = _summary(reports, report_id)
    assert summary["lifecycle"] == "draft"
    assert summary["status"] == "completed"
    assert summary["passed"] is True
    assert set(summary["metrics"]) == set(calibration.THRESHOLDS)

    assert _command("confirm", report_id, reports, judge) == 0
    assert _command("check", report_id, reports, judge) == 0
    assert _command("confirm", report_id, reports, judge) == 1
    assert _command("reject", report_id, reports, judge) == 0
    assert _command("check", report_id, reports, judge) == 1
    assert _command("reject", report_id, reports, judge) == 1
    assert _summary(reports, report_id)["lifecycle"] == "rejected"


def test_threshold_failure_returns_one_and_keeps_draft_report(
    tmp_path: Path,
) -> None:
    manifest = _write_bundle(tmp_path / "dataset")
    reports = tmp_path / "reports"

    assert _run(manifest, reports, FakeEvaluationJudge(score=0)) == 1

    summary = _summary(reports, _only_report_id(reports))
    assert summary["lifecycle"] == "draft"
    assert summary["status"] == "completed"
    assert summary["passed"] is False
    assert summary["metrics"]["semantic_quality_state_accuracy"] == 0


def test_execution_error_returns_two_but_keeps_failed_audit_report(
    tmp_path: Path,
) -> None:
    manifest = _write_bundle(tmp_path / "dataset")
    reports = tmp_path / "reports"

    assert (
        _run(
            manifest,
            reports,
            FakeEvaluationJudge(invalid_output=True),
        )
        == 2
    )

    summary = _summary(reports, _only_report_id(reports))
    assert summary["lifecycle"] == "draft"
    assert summary["status"] == "failed"
    assert summary["passed"] is False
    assert summary["metrics"] is None


def test_draft_seed_and_unavailable_judge_fail_before_model_calls(
    tmp_path: Path,
) -> None:
    draft_manifest = _write_bundle(tmp_path / "draft", lifecycle="draft")
    confirmed_manifest = _write_bundle(tmp_path / "confirmed")

    assert _run(draft_manifest, tmp_path / "draft-reports", FakeEvaluationJudge()) == 2
    assert (
        _run(
            confirmed_manifest,
            tmp_path / "unavailable-reports",
            FakeEvaluationJudge(available=False),
        )
        == 2
    )
    assert not (tmp_path / "draft-reports").exists()
    assert not (tmp_path / "unavailable-reports").exists()


def test_confirm_rejects_report_artifact_hash_corruption(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "dataset")
    reports = tmp_path / "reports"
    judge = FakeEvaluationJudge()
    assert _run(manifest, reports, judge) == 0
    report_id = _only_report_id(reports)
    cases_path = reports / report_id / "cases.json"
    cases_path.write_text(
        cases_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
    )

    assert _command("confirm", report_id, reports, judge) == 2


def test_model_identity_and_prompt_hash_are_confirmation_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_bundle(tmp_path / "dataset")
    reports = tmp_path / "reports"
    judge = FakeEvaluationJudge(model_id="judge-a")
    assert _run(manifest, reports, judge) == 0
    report_id = _only_report_id(reports)

    assert (
        _command(
            "confirm",
            report_id,
            reports,
            FakeEvaluationJudge(model_id="judge-b"),
        )
        == 1
    )
    monkeypatch.setattr(calibration, "current_prompt_hash", lambda: "f" * 64)
    assert _command("confirm", report_id, reports, judge) == 1


def test_report_id_path_traversal_and_cli_argument_errors_return_two(
    tmp_path: Path,
) -> None:
    judge = FakeEvaluationJudge()
    assert _command("check", "../summary", tmp_path, judge) == 2
    assert calibration.main(["run"], judge_factory=lambda: judge) == 2
    assert calibration.main(["unknown"], judge_factory=lambda: judge) == 2


def test_contradiction_and_hallucination_labels_keep_distinct_keys() -> None:
    contradiction = calibration.HumanLabel(
        critical_findings=[
            calibration.HumanCriticalFinding(
                kind="contradictory_fact",
                field="summary",
                claim_id="claim-1",
            )
        ]
    )
    hallucination = calibration.HumanLabel(
        critical_findings=[
            calibration.HumanCriticalFinding(
                kind="unsupported_fact",
                field="summary",
                claim_id="claim-1",
            )
        ]
    )

    contradiction_keys = calibration._human_critical_keys(contradiction)
    hallucination_keys = calibration._human_critical_keys(hallucination)

    assert contradiction_keys != hallucination_keys
    assert not contradiction_keys & hallucination_keys


def test_repository_seed_has_48_draft_cases_and_full_cross_coverage() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "evaluations"
        / "calibration"
        / "knowledge_extraction_judge"
    )
    bundle = calibration.load_calibration_bundle(
        root / "manifest.json",
        require_confirmed=False,
    )

    assert bundle.manifest.lifecycle.value == "draft"
    assert len(bundle.cases) == 48
    assert {(case.knowledge_type.value, case.error_mode) for case in bundle.cases} == {
        (knowledge_type.value, error_mode)
        for knowledge_type in bundle.manifest.knowledge_types
        for error_mode in calibration.ERROR_MODES
    }
    assert all(case.human_label.lifecycle.value == "draft" for case in bundle.cases)
    assert all(not case.human_label.reviewer_ids for case in bundle.cases)


def _run(
    manifest: Path,
    reports: Path,
    judge: FakeEvaluationJudge,
) -> int:
    return calibration.main(
        [
            "run",
            "--manifest",
            str(manifest),
            "--repetitions",
            "3",
            "--report-root",
            str(reports),
        ],
        judge_factory=lambda: judge,
    )


def _command(
    command: str,
    report_id: str,
    reports: Path,
    judge: FakeEvaluationJudge,
) -> int:
    arguments = [
        command,
        "--report-id",
        report_id,
        "--report-root",
        str(reports),
    ]
    return calibration.main(arguments, judge_factory=lambda: judge)


def _only_report_id(reports: Path) -> str:
    entries = [path.name for path in reports.iterdir() if path.is_dir()]
    assert len(entries) == 1
    return entries[0]


def _summary(reports: Path, report_id: str) -> dict[str, Any]:
    return json.loads(
        (reports / report_id / "summary.json").read_text(encoding="utf-8")
    )


def _prompt_case(prompt: str) -> dict[str, Any]:
    start_marker = "<UNTRUSTED_EVALUATION_DATA>\n"
    end_marker = "\n</UNTRUSTED_EVALUATION_DATA>"
    start = prompt.index(start_marker) + len(start_marker)
    end = prompt.index(end_marker)
    return json.loads(prompt[start:end])[0]


def _write_bundle(root: Path, *, lifecycle: str = "confirmed") -> Path:
    root.mkdir(parents=True)
    source_text = "秦照是大田镇猎户学徒，随身佩着一把木弓。"
    source_path = root / "sources" / "character_correct_001.md"
    source_path.parent.mkdir()
    source_path.write_text(source_text, encoding="utf-8")
    source_hash = sha256(source_text.encode()).hexdigest()
    human_label = {
        "lifecycle": lifecycle,
        "status": "scored" if lifecycle == "confirmed" else None,
        "dimension_scores": (
            {name: 4 for name in calibration.REQUIRED_DIMENSIONS}
            if lifecycle == "confirmed"
            else {}
        ),
        "expected_semantic_quality_state": (
            "stable" if lifecycle == "confirmed" else None
        ),
        "critical_findings": [],
        "critical_flag_codes": [],
        "reviewer_ids": ["reviewer-a", "reviewer-b"]
        if lifecycle == "confirmed"
        else [],
        "adjudication_note": (
            "两名复核人完成独立标注后达成一致。" if lifecycle == "confirmed" else None
        ),
    }
    cases = [
        {
            "calibration_case_id": "character_correct_001",
            "knowledge_type": "character",
            "scope_kind": "single_chapter",
            "error_mode": "correct",
            "source_chapter_path": "sources/character_correct_001.md",
            "expected_card": {
                "type": "character",
                "name": "秦照",
                "summary": source_text,
            },
            "actual_card": {
                "type": "character",
                "name": "秦照",
                "summary": source_text,
            },
            "expected_claims": [
                {
                    "claim_id": "claim_character_correct_001",
                    "field": "summary",
                    "importance": "critical",
                    "description": source_text,
                    "source_quote_ids": ["quote_character_correct_001"],
                }
            ],
            "source_quotes": [
                {
                    "quote_id": "quote_character_correct_001",
                    "chapter_id": "chapter_character_correct_001",
                    "text": source_text,
                    "start_offset": 0,
                    "end_offset": len(source_text),
                    "source_hash": source_hash,
                }
            ],
            "human_label": human_label,
        }
    ]
    annotations = {
        "lifecycle": lifecycle,
        "cases": [
            {
                "calibration_case_id": "character_correct_001",
                "independent_reviews": (
                    [
                        {"reviewer_id": "reviewer-a", "status": "completed"},
                        {"reviewer_id": "reviewer-b", "status": "completed"},
                    ]
                    if lifecycle == "confirmed"
                    else [
                        {"reviewer_id": None, "status": "pending"},
                        {"reviewer_id": None, "status": "pending"},
                    ]
                ),
                "adjudication": {
                    "status": "confirmed" if lifecycle == "confirmed" else "pending"
                },
            }
        ],
    }
    _write_json(root / "cases.json", cases)
    metadata = root / "_metadata"
    metadata.mkdir()
    _write_json(metadata / "annotations.json", annotations)
    checksum_records = {
        "cases.json": _file_hash(root / "cases.json"),
        "_metadata/annotations.json": _file_hash(metadata / "annotations.json"),
        "sources/character_correct_001.md": _file_hash(source_path),
    }
    _write_json(root / "checksums.sha256.json", checksum_records)
    manifest = {
        "calibration_id": "knowledge_extraction_judge_test",
        "lifecycle": lifecycle,
        "prompt_contract_id": calibration.PROMPT_CONTRACT_ID,
        "knowledge_types": ["character"],
        "error_modes": ["correct"],
        "case_count": 1,
        "cases_path": "cases.json",
        "checksums_path": "checksums.sha256.json",
        "annotations_path": "_metadata/annotations.json",
        "human_label_protocol": {
            "required_reviewers": 2,
            "independent_annotation": True,
            "adjudication_required": True,
            "seed_status": "confirmed" if lifecycle == "confirmed" else "pending",
            "instruction": "两人独立标注，并由第三步复核形成唯一标签。",
        },
    }
    _write_json(root / "manifest.json", manifest)
    return root / "manifest.json"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
