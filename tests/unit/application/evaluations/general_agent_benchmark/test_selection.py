"""需求 1.5、1.6、1.7、12.2、12.3、12.7：共享轨道选择。"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from taichu.application.evaluations.general_agent_benchmark.models import (
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.selection import (
    CaseSelection,
    SelectionError,
    SuiteSelectionValidator,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
    load_authored_suite,
)

_FIXTURE_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _FIXTURE_ROOT / "suite.json"
_MANIFEST_PATH = _FIXTURE_ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"


@pytest.fixture(scope="module")
def suite() -> AuthoredSuiteSpec:
    payload = json.loads(_SUITE_PATH.read_text(encoding="utf-8"))
    return load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=payload["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )


def test_requirements_1_5_1_6_full_selection_is_derived_from_suite_tracks(
    suite: AuthoredSuiteSpec,
) -> None:
    synthetic = SuiteSelectionValidator.full_selection(
        suite,
        TrackKind.SYNTHETIC,
    )
    live = SuiteSelectionValidator.full_selection(
        suite,
        TrackKind.LIVE_PROVIDER,
    )

    assert isinstance(synthetic, CaseSelection)
    assert synthetic.selected_case_ids == suite.case_order
    assert synthetic.case_count == 37
    assert synthetic.is_full_selection is True
    assert synthetic.complete_admission is True
    assert tuple(case.case_id for case in synthetic.cases) == (
        synthetic.selected_case_ids
    )

    assert isinstance(live, CaseSelection)
    assert live.selected_case_ids == suite.case_order[:21]
    assert live.case_count == 21
    assert live.is_full_selection is True
    assert live.complete_admission is False
    assert tuple(case.case_id for case in live.cases) == live.selected_case_ids


def test_requirements_12_2_12_3_partial_selection_is_never_complete_admission(
    suite: AuthoredSuiteSpec,
) -> None:
    requested = (
        suite.case_order[0],
        suite.case_order[5],
        suite.case_order[20],
    )

    selection = SuiteSelectionValidator.validate(
        suite,
        TrackKind.SYNTHETIC,
        requested,
    )

    assert isinstance(selection, CaseSelection)
    assert selection.selected_case_ids == requested
    assert selection.is_full_selection is False
    assert selection.complete_admission is False


@pytest.mark.parametrize(
    ("requested", "track", "code", "message_fragment", "offending"),
    (
        (
            lambda suite: (suite.case_order[0], "unknown_benchmark_case"),
            TrackKind.SYNTHETIC,
            "unknown_case_ids",
            "未知",
            ("unknown_benchmark_case",),
        ),
        (
            lambda suite: (suite.case_order[0], suite.case_order[0]),
            TrackKind.SYNTHETIC,
            "duplicate_or_out_of_order_case_ids",
            "重复",
            None,
        ),
        (
            lambda suite: (suite.case_order[1], suite.case_order[0]),
            TrackKind.SYNTHETIC,
            "duplicate_or_out_of_order_case_ids",
            "顺序",
            None,
        ),
        (
            lambda suite: (suite.case_order[21],),
            TrackKind.LIVE_PROVIDER,
            "case_track_not_applicable",
            "不适用",
            None,
        ),
    ),
)
def test_requirement_1_7_invalid_selection_returns_typed_chinese_error(
    suite: AuthoredSuiteSpec,
    requested: Callable[[AuthoredSuiteSpec], tuple[str, ...]],
    track: TrackKind,
    code: str,
    message_fragment: str,
    offending: tuple[str, ...] | None,
) -> None:
    selected_ids = requested(suite)

    result = SuiteSelectionValidator.validate(suite, track, selected_ids)

    assert isinstance(result, SelectionError)
    assert result.code == code
    assert message_fragment in result.message
    assert any("\u4e00" <= character <= "\u9fff" for character in result.message)
    assert result.track == track
    if offending is not None:
        assert result.case_ids == offending


def test_requirement_1_7_caller_can_reject_before_workspace_or_provider(
    suite: AuthoredSuiteSpec,
) -> None:
    workspace_calls: list[str] = []
    provider_calls: list[str] = []

    def execute_after_validation(
        requested_case_ids: tuple[str, ...],
    ) -> CaseSelection | SelectionError:
        result = SuiteSelectionValidator.validate(
            suite,
            TrackKind.LIVE_PROVIDER,
            requested_case_ids,
        )
        if isinstance(result, SelectionError):
            return result
        workspace_calls.append("created")
        provider_calls.append("called")
        return result

    result = execute_after_validation((suite.case_order[21],))

    assert isinstance(result, SelectionError)
    assert result.code == "case_track_not_applicable"
    assert workspace_calls == []
    assert provider_calls == []
