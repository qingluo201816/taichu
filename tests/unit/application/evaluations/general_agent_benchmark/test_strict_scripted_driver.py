"""需求 4.9—4.15：严格合成脚本协议。"""

from __future__ import annotations

import pytest

from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ObservedInteraction,
    ScriptedMatcher,
    ScriptedStep,
    StrictScriptedDriver,
    SyntheticNormalizationArtifact,
    SyntheticProtocolError,
    assert_normalization_stable,
)


def _step(
    step_id: str,
    sequence: int,
    kind: InteractionKind,
    name: str,
    *,
    expected: object,
) -> ScriptedStep:
    return ScriptedStep(
        step_id=step_id,
        sequence=sequence,
        kind=kind,
        name=name,
        matchers=(ScriptedMatcher(path="/input", expected=expected),),
        evidence_projection=("/input",),
    )


def _observed(
    kind: InteractionKind,
    name: str,
    value: object,
) -> ObservedInteraction:
    return ObservedInteraction(kind=kind, name=name, payload={"input": value})


def _error_code(callable_: object) -> str:
    with pytest.raises(SyntheticProtocolError) as captured:
        callable_()  # type: ignore[operator]
    return captured.value.evidence.error_code


def test_six_protocol_failures_are_independent_and_structured() -> None:
    expected = _step("model_first", 0, InteractionKind.MODEL, "chat", expected="甲")
    later = _step("tool_second", 1, InteractionKind.TOOL, "read_manuscript", expected=1)

    unexpected = StrictScriptedDriver((expected,))
    assert (
        _error_code(
            lambda: unexpected.observe(
                _observed(InteractionKind.TOOL, "unknown_tool", "甲")
            )
        )
        == "SYNTHETIC_UNEXPECTED_INTERACTION"
    )

    out_of_order = StrictScriptedDriver((expected, later))
    assert (
        _error_code(
            lambda: out_of_order.observe(
                _observed(InteractionKind.TOOL, "read_manuscript", 1)
            )
        )
        == "SYNTHETIC_OUT_OF_ORDER"
    )

    mismatch = StrictScriptedDriver((expected,))
    with pytest.raises(SyntheticProtocolError) as captured:
        mismatch.observe(_observed(InteractionKind.MODEL, "chat", "乙"))
    assert captured.value.evidence.error_code == "SYNTHETIC_CONTENT_MISMATCH"
    assert captured.value.evidence.matcher_path == "/input"
    assert captured.value.evidence.expected == {"input": "甲"}
    assert captured.value.evidence.observed == {"input": "乙"}

    exhausted = StrictScriptedDriver(())
    assert (
        _error_code(
            lambda: exhausted.observe(
                _observed(InteractionKind.MODEL, "chat", "甲")
            )
        )
        == "SYNTHETIC_SCRIPT_EXHAUSTED"
    )

    remaining = StrictScriptedDriver((expected, later))
    with pytest.raises(SyntheticProtocolError) as captured:
        remaining.finalize()
    assert captured.value.evidence.error_code == "SYNTHETIC_REMAINING_STEPS"
    assert captured.value.evidence.remaining_step_ids == (
        "model_first",
        "tool_second",
    )

    baseline = SyntheticNormalizationArtifact.create(
        script_identity="a" * 64,
        runtime_config_identity="b" * 64,
        consumption_trace=({"step_id": "model_first", "outcome": "completed"},),
        normalized_result={"stop_reason": "completed", "hard_gates": [True]},
    )
    changed = SyntheticNormalizationArtifact.create(
        script_identity="a" * 64,
        runtime_config_identity="b" * 64,
        consumption_trace=({"step_id": "model_first", "outcome": "completed"},),
        normalized_result={"stop_reason": "completed", "hard_gates": [False]},
    )
    with pytest.raises(SyntheticProtocolError) as captured:
        assert_normalization_stable(baseline, changed)
    assert captured.value.evidence.error_code == "SYNTHETIC_NORMALIZATION_DRIFT"
    assert captured.value.evidence.matcher_path == "/normalized_result/hard_gates/0"


def test_ordered_consumption_finalize_and_replay_are_byte_stable() -> None:
    steps = (
        _step("model_first", 0, InteractionKind.MODEL, "chat", expected="甲"),
        _step("tool_second", 1, InteractionKind.TOOL, "read_manuscript", expected=1),
    )

    artifacts = []
    for _ in range(2):
        driver = StrictScriptedDriver(steps)
        assert driver.observe(_observed(InteractionKind.MODEL, "chat", "甲")).step_id == (
            "model_first"
        )
        assert driver.observe(
            _observed(InteractionKind.TOOL, "read_manuscript", 1)
        ).step_id == "tool_second"
        artifacts.append(
            driver.finalize(
                script_identity="a" * 64,
                runtime_config_identity="b" * 64,
                normalized_result={
                    "stop_reason": "completed",
                    "node_states": ["completed"],
                },
            )
        )

    assert artifacts[0].canonical_bytes() == artifacts[1].canonical_bytes()
    assert_normalization_stable(artifacts[0], artifacts[1])


def test_normalization_excludes_only_declared_volatile_runtime_values() -> None:
    left = SyntheticNormalizationArtifact.create(
        script_identity="a" * 64,
        runtime_config_identity="b" * 64,
        consumption_trace=(),
        normalized_result={
            "run_id": "48eac492-a79a-41c1-ab31-93e2bb9fcd46",
            "run_id_before": "general_run_first",
            "checkpoint_content_sha256": "1" * 64,
            "created_at": "2026-07-27T01:00:00Z",
            "workspace_path": "C:/Temp/case-a",
            "node_states": ["completed"],
            "stop_reason": "completed",
        },
    )
    right = SyntheticNormalizationArtifact.create(
        script_identity="a" * 64,
        runtime_config_identity="b" * 64,
        consumption_trace=(),
        normalized_result={
            "run_id": "91fbf5dd-cfbf-4610-8411-e2cdaf16bea4",
            "run_id_before": "general_run_second",
            "checkpoint_content_sha256": "2" * 64,
            "created_at": "2026-07-27T02:00:00Z",
            "workspace_path": "D:/Temp/case-b",
            "node_states": ["completed"],
            "stop_reason": "completed",
        },
    )

    assert left.normalization_hash == right.normalization_hash
    assert left.normalized_result["node_states"] == ["completed"]
    assert (
        left.normalized_result["checkpoint_content_sha256"]
        == "<volatile-runtime-value>"
    )
    assert "created_at" not in left.normalized_result
    assert_normalization_stable(left, right)


def test_protocol_error_bytes_are_stable_for_same_minimal_counterexample() -> None:
    payloads = []
    for _ in range(2):
        driver = StrictScriptedDriver(
            (_step("model_first", 0, InteractionKind.MODEL, "chat", expected="甲"),)
        )
        with pytest.raises(SyntheticProtocolError) as captured:
            driver.observe(_observed(InteractionKind.MODEL, "chat", "乙"))
        payloads.append(captured.value.canonical_bytes())

    assert payloads[0] == payloads[1]


def test_parallel_group_accepts_any_stream_schedule_but_preserves_stream_order() -> None:
    steps = (
        _step("a_model", 0, InteractionKind.MODEL, "a_model", expected="a").model_copy(
            update={"parallel_group": "reviews", "stream_id": "a"}
        ),
        _step("a_agent", 1, InteractionKind.SUBAGENT, "aaa", expected="a").model_copy(
            update={"parallel_group": "reviews", "stream_id": "a"}
        ),
        _step("b_model", 2, InteractionKind.MODEL, "b_model", expected="b").model_copy(
            update={"parallel_group": "reviews", "stream_id": "b"}
        ),
        _step("b_agent", 3, InteractionKind.SUBAGENT, "bbb", expected="b").model_copy(
            update={"parallel_group": "reviews", "stream_id": "b"}
        ),
    )
    driver = StrictScriptedDriver(steps)

    assert driver.observe(
        _observed(InteractionKind.MODEL, "b_model", "b")
    ).step_id == "b_model"
    assert driver.observe(
        _observed(InteractionKind.SUBAGENT, "bbb", "b")
    ).step_id == "b_agent"
    with pytest.raises(SyntheticProtocolError) as captured:
        driver.observe(_observed(InteractionKind.SUBAGENT, "aaa", "a"))
    assert captured.value.evidence.error_code == "SYNTHETIC_OUT_OF_ORDER"
