"""需求 1.1、1.2、1.3、2.1、3.1、11.2：Suite@2 严格合同。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    GateKind,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    load_authored_suite,
    load_fixture_manifest,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_MANIFEST_PATH = (
    _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"
)

_EXPECTED_CASES = (
    ("direct_answer_current_request", "当前请求直接回答"),
    ("single_manuscript_search", "单次正文检索"),
    ("structure_coverage_read", "结构与覆盖读取"),
    ("single_knowledge_retrieval", "单次知识检索"),
    ("knowledge_catalog_identity_read", "知识目录身份读取"),
    ("external_research_grounded", "外部资料有据研究"),
    ("single_canon_evidence", "单次设定证据"),
    ("summary_world_character", "摘要驱动世界与人物分析"),
    ("architecture_scene_draft", "架构场景与草稿流水线"),
    ("parallel_review_triad", "三类独立审查"),
    ("revision_from_reviews", "依据审查修订"),
    ("manuscript_preview_only", "正文补丁仅预览"),
    ("manuscript_patch_authorized_resume", "授权后应用确认预览"),
    ("structure_create_update", "结构创建并精确更新"),
    ("structure_delete_second_confirmation", "结构删除二次确认"),
    ("knowledge_create_update", "知识创建并精确更新"),
    ("write_authorization_denied", "写授权拒绝"),
    ("memory_active_projection", "有效运行工作记忆生效"),
    ("memory_stale_dependency", "过期记忆依赖排除"),
    ("memory_rejected_parallel_isolation", "被拒绝记忆分支隔离"),
    ("memory_superseded_repair", "被替代记忆修复"),
    ("recovery_after_plan_before_execution", "规划后执行前恢复"),
    ("recovery_tool_result_before_consumption", "Tool 结果未消费前恢复"),
    ("recovery_subagent_interrupted", "Subagent 中断恢复"),
    ("recovery_waiting_authorization", "授权等待中恢复"),
    ("recovery_after_write_before_effect_success", "写入后效果确认前恢复"),
    ("recovery_verification_interruption", "校验阶段中断恢复"),
    ("recovery_multiple_interruptions", "多次中断恢复"),
    ("recovery_checkpoint_integrity_or_version", "Checkpoint 完整性与版本恢复"),
    ("context_long_history_fact_retention", "长历史关键事实保持"),
    ("context_long_working_memory_priority", "长工作记忆优先裁剪"),
    ("context_large_node_output_projection", "大节点输出投影"),
    ("context_multi_source_overflow", "多来源上下文共同超限"),
    ("context_compression_result_equivalence", "压缩前后结果等价"),
    ("context_invalid_memory_pressure_isolation", "无效记忆压力隔离"),
    ("context_long_current_request_preserved", "长当前请求完整保留"),
    ("context_unsafe_compression_refusal", "无法安全压缩时拒绝"),
)


def _suite_payload() -> dict[str, object]:
    return json.loads(_SUITE_PATH.read_text(encoding="utf-8"))


def _write_suite(tmp_path: Path, payload: dict[str, object]) -> Path:
    payload["content_hash"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_hash"}
    )
    path = tmp_path / "suite.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _load(path: Path = _SUITE_PATH):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return load_authored_suite(
        path,
        expected_capability_catalog_hash=payload["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )


def test_requirement_1_1_suite_v2_declares_exact_37_typed_contracts() -> None:
    suite = _load()

    assert suite.schema_ == "taichu.general_agent_benchmark.suite@2"
    assert tuple((case.case_id, case.name) for case in suite.cases) == (
        _EXPECTED_CASES
    )
    assert suite.case_order == tuple(case_id for case_id, _ in _EXPECTED_CASES)
    assert "external_access_denied" not in suite.case_order
    assert "runtime_checkpoint_recovery" not in suite.case_order

    live_ids = tuple(
        case.case_id
        for case in suite.cases
        if TrackKind.LIVE_PROVIDER in case.applicable_tracks
    )
    synthetic_ids = tuple(
        case.case_id
        for case in suite.cases
        if TrackKind.SYNTHETIC in case.applicable_tracks
    )
    assert synthetic_ids == suite.case_order
    assert live_ids == suite.case_order[:21]

    all_gates = frozenset(GateKind)
    for index, case in enumerate(suite.cases, start=1):
        assert case.summary
        assert case.scenario.scenario_id == case.case_id
        assert case.setup.fixture_ref == "core_novel"
        assert case.expected_terminal.reason_code
        assert case.behavior_assertions
        assert frozenset(item.gate for item in case.required_evidence) == all_gates
        assert case.scenario.rag_placeholder is (2 <= index <= 6)


def test_requirement_1_2_suite_v2_rejects_unknown_union_and_extra_fields(
    tmp_path: Path,
) -> None:
    unknown_kind = _suite_payload()
    unknown_kind["cases"][0]["behavior_assertions"][0]["kind"] = "unknown_kind"
    with pytest.raises(ValueError):
        _load(_write_suite(tmp_path, unknown_kind))

    extra_field = _suite_payload()
    extra_field["cases"][0]["unexpected_contract"] = True
    with pytest.raises(ValueError):
        _load(_write_suite(tmp_path, extra_field))


def test_requirement_11_2_bad_fixture_reference_is_rejected_before_execution(
    tmp_path: Path,
) -> None:
    payload = _suite_payload()
    payload["cases"][0]["setup"]["resource_snapshot_refs"] = [
        "missing_resource_snapshot"
    ]

    with pytest.raises(ValueError, match="夹具引用"):
        _load(_write_suite(tmp_path, payload))


def test_requirement_11_2_fixture_manifest_v2_has_typed_execution_identity() -> None:
    manifest = load_fixture_manifest(_MANIFEST_PATH)

    assert manifest.schema_ == "taichu.general_agent_benchmark.fixture@2"
    assert manifest.content_hash
    assert tuple(item.path for item in manifest.suite_manifest_entries) == (
        "claim-catalog.json",
    )
    assert {item.kind for item in manifest.scenario_assets} == {
        "resource_snapshot",
        "memory_seed",
        "human_decision",
        "fault_plan",
        "pressure_plan",
        "expected_post_state",
    }
