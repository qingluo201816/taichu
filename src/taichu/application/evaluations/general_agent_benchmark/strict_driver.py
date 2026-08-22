"""全局有序、完全确定的 synthetic 交互脚本驱动器。"""

from __future__ import annotations

from enum import StrEnum
import re
from typing import Any

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_json_bytes,
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
)

_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_VOLATILE_TIME_KEYS = frozenset(
    {
        "timestamp",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "observed_at",
    }
)
_VOLATILE_PATH_KEYS = frozenset(
    {
        "workspace_path",
        "database_path",
        "temp_path",
        "temporary_path",
    }
)
_VOLATILE_DATABASE_KEYS = frozenset({"database_name", "temporary_database"})
_VOLATILE_RUNTIME_VALUE_KEYS = frozenset(
    {
        "run_id_before",
        "run_id_after",
        "checkpoint_content_sha256",
    }
)


class InteractionKind(StrEnum):
    """真实 Runtime 中可观察的五类交互。"""

    MODEL = "model"
    TOOL = "tool"
    SUBAGENT = "subagent"
    HUMAN = "human"
    TASK = "task"


class ScriptedMatcher(BenchmarkModel):
    """对观察 payload 中一个 JSON Pointer 的精确匹配。"""

    path: str = Field(pattern=r"^/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])+)*$")
    expected: Any


class ScriptedStep(BenchmarkModel):
    """全局脚本中的一个有序交互声明。"""

    step_id: StableId
    sequence: int = Field(ge=0)
    kind: InteractionKind
    name: StableId
    matchers: tuple[ScriptedMatcher, ...]
    evidence_projection: tuple[str, ...]
    response: Any | None = None
    parallel_group: StableId | None = None
    stream_id: StableId | None = None

    @model_validator(mode="after")
    def _paths_are_unique(self) -> ScriptedStep:
        matcher_paths = [matcher.path for matcher in self.matchers]
        if len(matcher_paths) != len(set(matcher_paths)):
            raise ValueError("同一步骤的 matcher path 不得重复。")
        if len(self.evidence_projection) != len(set(self.evidence_projection)):
            raise ValueError("同一步骤的 evidence projection 不得重复。")
        if (self.parallel_group is None) != (self.stream_id is None):
            raise ValueError("parallel_group 与 stream_id 必须成对声明。")
        return self


class ObservedInteraction(BenchmarkModel):
    """Runtime wrapper 交给驱动器的真实交互观察。"""

    kind: InteractionKind
    name: StableId
    payload: dict[str, Any]
    outcome: str = Field(default="completed", min_length=1)


class SyntheticProtocolEvidence(BenchmarkModel):
    """可持久化且字节稳定的 synthetic 协议失败证据。"""

    error_code: str
    step_id: str | None
    step_index: int | None
    expected: Any | None
    observed: Any | None
    matcher_path: str | None
    remaining_step_ids: tuple[str, ...]


class SyntheticProtocolError(RuntimeError):
    """严格驱动器拒绝继续运行时的结构化错误。"""

    def __init__(self, evidence: SyntheticProtocolEvidence) -> None:
        self.evidence = evidence
        super().__init__(evidence.error_code)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.evidence)


class SyntheticNormalizationArtifact(BenchmarkModel):
    """同脚本、同 Runtime 配置重复运行的规范化结果。"""

    script_identity: Sha256
    runtime_config_identity: Sha256
    consumption_trace: tuple[dict[str, Any], ...]
    normalized_result: Any
    normalization_hash: Sha256

    @classmethod
    def create(
        cls,
        *,
        script_identity: str,
        runtime_config_identity: str,
        consumption_trace: tuple[dict[str, Any], ...],
        normalized_result: Any,
    ) -> SyntheticNormalizationArtifact:
        stable_trace = _normalize_runtime_value(consumption_trace)
        stable_result = _normalize_runtime_value(normalized_result)
        return cls(
            script_identity=script_identity,
            runtime_config_identity=runtime_config_identity,
            consumption_trace=stable_trace,
            normalized_result=stable_result,
            normalization_hash=canonical_sha256(
                {
                    "consumption_trace": stable_trace,
                    "normalized_result": stable_result,
                }
            ),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self)


class StrictScriptedDriver:
    """只消费当前流首，禁止模糊匹配和静默跳步。"""

    def __init__(self, steps: tuple[ScriptedStep, ...]) -> None:
        sequences = [step.sequence for step in steps]
        step_ids = [step.step_id for step in steps]
        if sequences != list(range(len(steps))):
            raise ValueError("scripted step sequence 必须从 0 开始连续递增。")
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("scripted step_id 必须唯一。")
        self._steps = steps
        self._cursor = 0
        self._consumed: set[int] = set()
        self._trace: list[dict[str, Any]] = []

    @property
    def steps(self) -> tuple[ScriptedStep, ...]:
        return self._steps

    @property
    def current_step(self) -> ScriptedStep | None:
        eligible = self._eligible_indices()
        if not eligible:
            return None
        return self._steps[eligible[0]]

    def select_step(
        self,
        *,
        kind: InteractionKind,
        payload: dict[str, Any],
    ) -> ScriptedStep | None:
        """为并行独立 stream 选择当前可消费步骤，不依赖调度先后。"""
        matches = [
            self._steps[index]
            for index in self._eligible_indices()
            if self._steps[index].kind is kind
            and _matchers_match(self._steps[index], payload)
        ]
        if len(matches) > 1:
            raise ValueError("并行 strict group 存在无法唯一选择的步骤。")
        return matches[0] if matches else None

    def observe(self, observed: ObservedInteraction) -> ScriptedStep:
        """精确匹配并消费当前步骤；任何偏差均 fail closed。"""
        eligible = self._eligible_indices()
        if not eligible:
            self._raise(
                "SYNTHETIC_SCRIPT_EXHAUSTED",
                expected=None,
                observed=observed.payload,
                matcher_path=None,
                current=None,
            )

        current_index = eligible[0]
        current = self._steps[current_index]
        same_identity = next(
            (
                self._steps[index]
                for index in eligible
                if self._steps[index].kind is observed.kind
                and self._steps[index].name == observed.name
            ),
            None,
        )
        mismatch_path = (
            _first_mismatch_path(same_identity, observed)
            if same_identity is not None
            else None
        )
        if same_identity is not None and mismatch_path is not None:
            self._raise(
                "SYNTHETIC_CONTENT_MISMATCH",
                expected=_expected_payload(same_identity),
                observed=observed.payload,
                matcher_path=mismatch_path,
                current=same_identity,
            )

        matched_index = next(
            (
                index
                for index in eligible
                if _step_matches(self._steps[index], observed)
            ),
            None,
        )
        if matched_index is not None:
            matched = self._steps[matched_index]
            self._trace.append(
                {
                    "step_id": matched.step_id,
                    "step_index": matched_index,
                    "kind": matched.kind,
                    "name": matched.name,
                    "outcome": observed.outcome,
                    "evidence": _project(observed.payload, matched.evidence_projection),
                }
            )
            self._consumed.add(matched_index)
            self._advance_cursor()
            return matched

        later_match = next(
            (
                self._steps[index]
                for index in range(self._cursor, len(self._steps))
                if index not in self._consumed
                and index not in eligible
                and _step_matches(self._steps[index], observed)
            ),
            None,
        )
        if later_match is not None:
            self._raise(
                "SYNTHETIC_OUT_OF_ORDER",
                expected=_expected_payload(current),
                observed=observed.payload,
                matcher_path=None,
                current=current,
            )

        self._raise(
            "SYNTHETIC_UNEXPECTED_INTERACTION",
            expected=_expected_payload(current),
            observed=observed.payload,
            matcher_path=None,
            current=current,
        )

    def finalize(
        self,
        *,
        script_identity: str | None = None,
        runtime_config_identity: str | None = None,
        normalized_result: Any | None = None,
    ) -> SyntheticNormalizationArtifact:
        """Runtime 停止后的强制收尾；未消费步骤不可被忽略。"""
        if len(self._consumed) < len(self._steps):
            current = self.current_step
            self._raise(
                "SYNTHETIC_REMAINING_STEPS",
                expected=(
                    _expected_payload(current) if current is not None else None
                ),
                observed=None,
                matcher_path=None,
                current=current,
            )
        if script_identity is None or runtime_config_identity is None:
            raise ValueError("脚本完全消费后必须提供 script/runtime config identity。")
        return SyntheticNormalizationArtifact.create(
            script_identity=script_identity,
            runtime_config_identity=runtime_config_identity,
            consumption_trace=tuple(
                sorted(self._trace, key=lambda item: int(item["step_index"]))
            ),
            normalized_result=normalized_result,
        )

    def _eligible_indices(self) -> list[int]:
        self._advance_cursor()
        if self._cursor >= len(self._steps):
            return []
        current = self._steps[self._cursor]
        if current.parallel_group is None:
            return [self._cursor]
        group = current.parallel_group
        group_indices: list[int] = []
        for index in range(self._cursor, len(self._steps)):
            step = self._steps[index]
            if step.parallel_group != group:
                break
            if index not in self._consumed:
                group_indices.append(index)
        eligible: list[int] = []
        seen_streams: set[str] = set()
        for index in group_indices:
            stream_id = self._steps[index].stream_id
            assert stream_id is not None
            if stream_id in seen_streams:
                continue
            seen_streams.add(stream_id)
            eligible.append(index)
        return eligible

    def _advance_cursor(self) -> None:
        while self._cursor in self._consumed:
            self._cursor += 1

    def _raise(
        self,
        error_code: str,
        *,
        expected: Any | None,
        observed: Any | None,
        matcher_path: str | None,
        current: ScriptedStep | None,
    ) -> None:
        raise SyntheticProtocolError(
            SyntheticProtocolEvidence(
                error_code=error_code,
                step_id=current.step_id if current is not None else None,
                step_index=self._cursor,
                expected=expected,
                observed=observed,
                matcher_path=matcher_path,
                remaining_step_ids=tuple(
                    step.step_id
                    for index, step in enumerate(self._steps)
                    if index not in self._consumed
                ),
            )
        )


def assert_normalization_stable(
    baseline: SyntheticNormalizationArtifact,
    repeated: SyntheticNormalizationArtifact,
) -> None:
    """同身份重放必须得到相同规范化 hash，否则给出首个稳定差异路径。"""
    if (
        baseline.script_identity != repeated.script_identity
        or baseline.runtime_config_identity != repeated.runtime_config_identity
    ):
        raise ValueError("只能比较相同脚本和 Runtime 配置身份的规范化工件。")
    if baseline.normalization_hash == repeated.normalization_hash:
        return
    baseline_payload = {
        "consumption_trace": baseline.consumption_trace,
        "normalized_result": baseline.normalized_result,
    }
    repeated_payload = {
        "consumption_trace": repeated.consumption_trace,
        "normalized_result": repeated.normalized_result,
    }
    raise SyntheticProtocolError(
        SyntheticProtocolEvidence(
            error_code="SYNTHETIC_NORMALIZATION_DRIFT",
            step_id=None,
            step_index=None,
            expected=baseline_payload,
            observed=repeated_payload,
            matcher_path=_first_diff_path(baseline_payload, repeated_payload),
            remaining_step_ids=(),
        )
    )


def _step_matches(step: ScriptedStep, observed: ObservedInteraction) -> bool:
    return (
        step.kind is observed.kind
        and step.name == observed.name
        and _first_mismatch_path(step, observed) is None
    )


def _matchers_match(step: ScriptedStep, payload: dict[str, Any]) -> bool:
    return all(
        _resolve_pointer(payload, matcher.path) == matcher.expected
        for matcher in step.matchers
    )


def _first_mismatch_path(
    step: ScriptedStep,
    observed: ObservedInteraction,
) -> str | None:
    for matcher in step.matchers:
        try:
            actual = _resolve_pointer(observed.payload, matcher.path)
        except (KeyError, IndexError, TypeError, ValueError):
            return matcher.path
        if canonical_json_bytes(actual) != canonical_json_bytes(matcher.expected):
            return matcher.path
    return None


def _expected_payload(step: ScriptedStep) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for matcher in step.matchers:
        _assign_pointer(payload, matcher.path, matcher.expected)
    return payload


def _project(payload: dict[str, Any], paths: tuple[str, ...]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for path in paths:
        try:
            value = _resolve_pointer(payload, path)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        _assign_pointer(projected, path, value)
    return projected


def _resolve_pointer(value: Any, path: str) -> Any:
    current = value
    for raw_part in path.removeprefix("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise TypeError(path)
    return current


def _assign_pointer(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [
        part.replace("~1", "/").replace("~0", "~")
        for part in path.removeprefix("/").split("/")
    ]
    current = target
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError(path)
        current = child
    current[parts[-1]] = value


def _first_diff_path(left: Any, right: Any, path: str = "") -> str:
    if type(left) is not type(right):
        return path or "/"
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            child_path = f"{path}/{_escape_pointer(str(key))}"
            if key not in left or key not in right:
                return child_path
            difference = _first_diff_path(left[key], right[key], child_path)
            if difference:
                return difference
        return ""
    if isinstance(left, (list, tuple)):
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
            difference = _first_diff_path(
                left_item,
                right_item,
                f"{path}/{index}",
            )
            if difference:
                return difference
        if len(left) != len(right):
            return f"{path}/{min(len(left), len(right))}"
        return ""
    return "" if left == right else (path or "/")


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _normalize_runtime_value(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            item_key: _normalize_runtime_value(item_value, key=item_key)
            for item_key, item_value in value.items()
            if item_key not in _VOLATILE_TIME_KEYS
        }
    if isinstance(value, tuple):
        return tuple(_normalize_runtime_value(item) for item in value)
    if isinstance(value, list):
        return [_normalize_runtime_value(item) for item in value]
    if isinstance(value, str):
        if key in _VOLATILE_RUNTIME_VALUE_KEYS:
            return "<volatile-runtime-value>"
        if key in _VOLATILE_PATH_KEYS:
            return "<volatile-path>"
        if key in _VOLATILE_DATABASE_KEYS:
            return "<volatile-database>"
        if key is not None and key.endswith("_id") and _UUID.fullmatch(value):
            return "<volatile-uuid>"
    return value
