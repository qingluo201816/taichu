"""由权威 Suite 合同派生轨道案例选择。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    AuthoredSuiteSpec,
)

SelectionErrorCode: TypeAlias = Literal[
    "invalid_track",
    "empty_case_selection",
    "invalid_case_ids",
    "unknown_case_ids",
    "duplicate_or_out_of_order_case_ids",
    "case_track_not_applicable",
]


class SelectionError(BenchmarkModel):
    """调用方可在创建运行、工作区或调用 provider 前处理的失败对象。"""

    code: SelectionErrorCode
    message: str = Field(min_length=1, max_length=4_000)
    track: str
    case_ids: tuple[str, ...] = ()
    expected_case_ids: tuple[StableId, ...] = ()


class CaseSelection(BenchmarkModel):
    """与 Suite 身份绑定、保持权威顺序的不可变案例选择。"""

    suite_id: StableId
    suite_content_hash: Sha256
    track: TrackKind
    applicable_case_ids: tuple[StableId, ...] = Field(min_length=1)
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    cases: tuple[AuthoredCaseSpec, ...] = Field(min_length=1)
    is_full_selection: bool
    complete_admission: bool

    @model_validator(mode="after")
    def _selection_contract_is_consistent(self) -> CaseSelection:
        case_ids = tuple(case.case_id for case in self.cases)
        if case_ids != self.selected_case_ids:
            raise ValueError("选择案例必须与 selected_case_ids 顺序一致。")
        applicable_set = frozenset(self.applicable_case_ids)
        if not set(self.selected_case_ids) <= applicable_set:
            raise ValueError("选择案例必须全部适用于所选轨道。")
        selected_in_track_order = tuple(
            case_id
            for case_id in self.applicable_case_ids
            if case_id in set(self.selected_case_ids)
        )
        if selected_in_track_order != self.selected_case_ids:
            raise ValueError("选择案例必须保持套件轨道顺序。")
        expected_full = self.selected_case_ids == self.applicable_case_ids
        if self.is_full_selection is not expected_full:
            raise ValueError("is_full_selection 必须由轨道适用集派生。")
        expected_admission = self.track is TrackKind.SYNTHETIC and expected_full
        if self.complete_admission is not expected_admission:
            raise ValueError("完整准入选择只允许完整 synthetic 轨道。")
        return self

    @property
    def case_ids(self) -> tuple[StableId, ...]:
        """兼容以案例集合命名的只读访问。"""

        return self.selected_case_ids

    @property
    def selected_cases(self) -> tuple[AuthoredCaseSpec, ...]:
        """返回已经按 Suite 权威顺序排列的案例。"""

        return self.cases

    @property
    def case_count(self) -> int:
        return len(self.selected_case_ids)


class SuiteSelectionValidator:
    """只读取 AuthoredSuiteSpec，不维护案例或轨道的第二份清单。"""

    @staticmethod
    def full_selection(
        suite: AuthoredSuiteSpec,
        track: TrackKind | str,
    ) -> CaseSelection | SelectionError:
        return SuiteSelectionValidator.validate(suite, track, None)

    @staticmethod
    def validate(
        suite: AuthoredSuiteSpec,
        track: TrackKind | str,
        requested_case_ids: Iterable[str] | None = None,
    ) -> CaseSelection | SelectionError:
        normalized_track = _normalize_track(track)
        if normalized_track is None:
            return SelectionError(
                code="invalid_track",
                message=f"未知的 Benchmark 轨道：{track}。",
                track=str(track),
            )

        declared_tracks = frozenset(item.kind for item in suite.tracks)
        if normalized_track not in declared_tracks:
            return SelectionError(
                code="invalid_track",
                message=f"当前套件未声明轨道：{normalized_track.value}。",
                track=normalized_track.value,
            )

        cases_by_id = {case.case_id: case for case in suite.cases}
        applicable_cases = tuple(
            case for case in suite.cases if normalized_track in case.applicable_tracks
        )
        applicable_case_ids = tuple(case.case_id for case in applicable_cases)

        requested = _materialize_requested_ids(requested_case_ids)
        if requested is None:
            return SelectionError(
                code="invalid_case_ids",
                message="案例选择必须是案例 ID 的可迭代集合。",
                track=normalized_track.value,
            )
        if requested_case_ids is None:
            requested = applicable_case_ids
        if not requested:
            return SelectionError(
                code="empty_case_selection",
                message="案例选择不能为空。",
                track=normalized_track.value,
                expected_case_ids=applicable_case_ids,
            )
        if any(not isinstance(case_id, str) or not case_id for case_id in requested):
            return SelectionError(
                code="invalid_case_ids",
                message="案例选择只能包含非空案例 ID。",
                track=normalized_track.value,
                case_ids=tuple(str(case_id) for case_id in requested),
                expected_case_ids=applicable_case_ids,
            )

        unknown = _unique_in_order(
            case_id for case_id in requested if case_id not in cases_by_id
        )
        if unknown:
            return SelectionError(
                code="unknown_case_ids",
                message="案例选择包含未知 ID：" + _format_ids(unknown) + "。",
                track=normalized_track.value,
                case_ids=unknown,
                expected_case_ids=applicable_case_ids,
            )

        duplicates = _duplicate_ids(requested)
        if duplicates:
            return SelectionError(
                code="duplicate_or_out_of_order_case_ids",
                message="案例选择包含重复 ID：" + _format_ids(duplicates) + "。",
                track=normalized_track.value,
                case_ids=duplicates,
                expected_case_ids=applicable_case_ids,
            )

        requested_set = frozenset(requested)
        canonical_requested = tuple(
            case_id for case_id in suite.case_order if case_id in requested_set
        )
        if requested != canonical_requested:
            return SelectionError(
                code="duplicate_or_out_of_order_case_ids",
                message="案例选择顺序必须与 Suite 权威顺序一致；正确顺序为："
                + _format_ids(canonical_requested)
                + "。",
                track=normalized_track.value,
                case_ids=requested,
                expected_case_ids=canonical_requested,
            )

        applicable_set = frozenset(applicable_case_ids)
        not_applicable = tuple(
            case_id for case_id in requested if case_id not in applicable_set
        )
        if not_applicable:
            return SelectionError(
                code="case_track_not_applicable",
                message=f"以下案例不适用于 {normalized_track.value} 轨道："
                + _format_ids(not_applicable)
                + "。",
                track=normalized_track.value,
                case_ids=not_applicable,
                expected_case_ids=applicable_case_ids,
            )

        selected_cases = tuple(cases_by_id[case_id] for case_id in requested)
        is_full_selection = requested == applicable_case_ids
        return CaseSelection(
            suite_id=suite.suite_id,
            suite_content_hash=suite.content_hash,
            track=normalized_track,
            applicable_case_ids=applicable_case_ids,
            selected_case_ids=requested,
            cases=selected_cases,
            is_full_selection=is_full_selection,
            complete_admission=(
                normalized_track is TrackKind.SYNTHETIC and is_full_selection
            ),
        )


def _normalize_track(track: TrackKind | str) -> TrackKind | None:
    try:
        return TrackKind(track)
    except (TypeError, ValueError):
        return None


def _materialize_requested_ids(
    requested_case_ids: Iterable[str] | None,
) -> tuple[str, ...] | None:
    if requested_case_ids is None:
        return ()
    if isinstance(requested_case_ids, str):
        return (requested_case_ids,)
    try:
        return tuple(requested_case_ids)
    except TypeError:
        return None


def _duplicate_ids(case_ids: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for case_id in case_ids:
        if case_id in seen and case_id not in duplicates:
            duplicates.append(case_id)
        seen.add(case_id)
    return tuple(duplicates)


def _unique_in_order(case_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(case_ids))


def _format_ids(case_ids: tuple[str, ...]) -> str:
    return "、".join(f"`{case_id}`" for case_id in case_ids)
