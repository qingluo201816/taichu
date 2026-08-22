"""案例 12—17：用真实 Runtime 核验预览、授权与持久化后态。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    ScriptedMatcher,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    load_authored_suite,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_environment import (
    SyntheticFixtureRuntime,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_FIXTURE_ROOT = _ROOT / "fixtures" / "core_novel"


def _tool_records(observation: Any) -> dict[str, Any]:
    return {
        record.interaction.name: record
        for record in observation.interactions
        if record.interaction.kind.value == "tool"
    }


def _human_decisions(observation: Any) -> list[tuple[str, bool]]:
    return [
        (
            record.interaction.name,
            bool(record.interaction.payload["approved"]),
        )
        for record in observation.interactions
        if record.interaction.kind.value == "human"
    ]


def _tool_human_sequence(observation: Any) -> list[tuple[str, str]]:
    return [
        (record.interaction.kind.value, record.interaction.name)
        for record in observation.interactions
        if record.interaction.kind.value in {"tool", "human"}
    ]


def _snapshot_pair(observation: Any, snapshot_ref: str) -> tuple[Any, Any]:
    by_phase = {
        snapshot.phase: snapshot
        for snapshot in observation.runtime_facts.resource_snapshots
        if snapshot.snapshot_ref == snapshot_ref
    }
    return by_phase["before"], by_phase["after"]


def _resource_states(snapshot: Any) -> dict[str, tuple[str, str]]:
    return {
        item["resource_ref"]: (item["state"], item["content_sha256"])
        for item in snapshot.payload["resources"]
    }


def _changed_refs(before: Any, after: Any) -> set[str]:
    before_states = _resource_states(before)
    after_states = _resource_states(after)
    return {
        ref
        for ref in before_states.keys() | after_states.keys()
        if before_states.get(ref) != after_states.get(ref)
    }


def _chapter_hash(snapshot: Any) -> str:
    matches = [
        content_sha256
        for ref, (_, content_sha256) in _resource_states(snapshot).items()
        if ref == "manuscript:chapter_001" or ref.endswith("/chapter_001.md")
    ]
    assert len(matches) == 1
    return matches[0]


async def _run_cases(tmp_path: Path) -> dict[str, Any]:
    capability_catalog = production_capability_catalog_snapshot()
    suite = load_authored_suite(
        _ROOT / "suite.json",
        expected_capability_catalog_hash=capability_catalog.canonical_hash,
    )
    observations: dict[str, Any] = {}
    for case in suite.cases[11:17]:
        runtime = SyntheticFixtureRuntime(
            sealed_fixture_root=_FIXTURE_ROOT,
            workspaces_root=tmp_path / case.case_id,
        )
        observations[case.case_id] = await runtime.execute(case)
    delete_case = suite.cases[14]
    cancel_step = delete_case.scripted_steps[1].model_copy(
        update={
            "matchers": (
                ScriptedMatcher(path="/approved", expected=False),
            ),
        }
    )
    cancelled_case = delete_case.model_copy(
        update={
            "required_invocations": (),
            "scripted_steps": (
                delete_case.scripted_steps[0],
                cancel_step,
            ),
        }
    )
    cancelled_runtime = SyntheticFixtureRuntime(
        sealed_fixture_root=_FIXTURE_ROOT,
        workspaces_root=tmp_path / "structure_delete_cancelled_probe",
    )
    observations["structure_delete_cancelled_probe"] = (
        await cancelled_runtime.execute(cancelled_case)
    )
    return observations


def test_cases_12_17_execute_real_runtime_and_prove_final_state(
    tmp_path: Path,
) -> None:
    observations = asyncio.run(_run_cases(tmp_path))

    preview = observations["manuscript_preview_only"]
    preview_before, preview_after = _snapshot_pair(
        preview,
        "resource_snapshot_manuscript_chapter_001",
    )
    assert preview.runtime_facts.terminal.run_status == "preview_only"
    assert [
        item.capability_name for item in preview.runtime_facts.invocations
    ] == ["preview_manuscript_patch"]
    assert preview.normalized_result["effect_tools"] == []
    assert _changed_refs(preview_before, preview_after) == set()
    assert _chapter_hash(preview_before) == _chapter_hash(preview_after)
    assert _chapter_hash(preview_after) == (
        "286809efcafe03e89df8d905f2ad2953fc84f4ee55860f5f676b5dbff65f1bad"
    )

    authorized = observations["manuscript_patch_authorized_resume"]
    authorized_tools = _tool_records(authorized)
    authorized_before, authorized_after = _snapshot_pair(
        authorized,
        "resource_snapshot_manuscript_chapter_001",
    )
    preview_output = authorized_tools[
        "preview_manuscript_patch"
    ].response_payload
    apply_input = authorized_tools["apply_manuscript_patch"].request_payload
    assert _human_decisions(authorized) == [("write_authorization", True)]
    assert _tool_human_sequence(authorized) == [
        ("tool", "preview_manuscript_patch"),
        ("human", "write_authorization"),
        ("tool", "apply_manuscript_patch"),
    ]
    assert authorized.normalized_result["effect_tools"] == [
        "apply_manuscript_patch"
    ]
    assert {
        "patch_id": apply_input["patch_id"],
        "chapter_id": apply_input["chapter_id"],
        "base_content_sha256": apply_input["base_content_sha256"],
        "expected_content_sha256": apply_input["expected_content_sha256"],
        "normalized_operations": apply_input["operations"],
    } == {
        key: preview_output[key]
        for key in (
            "patch_id",
            "chapter_id",
            "base_content_sha256",
            "expected_content_sha256",
            "normalized_operations",
        )
    }
    assert _changed_refs(authorized_before, authorized_after) == {
        "manuscript:chapter_001"
    }
    assert _chapter_hash(authorized_after) == (
        "6e639102a05eec96ba700d759bca83e01f1df69d98085071b7fc8cc95e1e9ba9"
    )

    structure = observations["structure_create_update"]
    structure_tools = _tool_records(structure)
    structure_create = structure_tools[
        "create_novel_structure_items"
    ].response_payload
    structure_update = structure_tools[
        "update_novel_structure"
    ].request_payload
    structure_update_output = structure_tools[
        "update_novel_structure"
    ].response_payload
    structure_before, structure_after = _snapshot_pair(
        structure,
        "resource_snapshot_novel_structure",
    )
    assert _human_decisions(structure) == [
        ("write_authorization", True),
        ("write_authorization", True),
    ]
    assert _tool_human_sequence(structure) == [
        ("human", "write_authorization"),
        ("tool", "create_novel_structure_items"),
        ("human", "write_authorization"),
        ("tool", "update_novel_structure"),
    ]
    assert structure_update["operations"][0]["target_id"] == (
        structure_create["changes"][0]["item_id"]
    )
    assert structure_update["expected_structure_version"] == (
        structure_create["structure_version"]
    )
    assert structure_update_output["changes"] == [
        {
            "kind": "volume",
            "item_id": structure_create["changes"][0]["item_id"],
            "action": "renamed",
            "title": "旧档案馆查档场景",
        }
    ]
    assert _changed_refs(structure_before, structure_after) == set(
        structure_after.payload["target_refs"]
    )

    deleted = observations["structure_delete_second_confirmation"]
    deleted_tool = _tool_records(deleted)["delete_novel_structure_items"]
    deleted_before, deleted_after = _snapshot_pair(
        deleted,
        "resource_snapshot_novel_structure",
    )
    assert _human_decisions(deleted) == [("write_authorization", True)]
    assert _tool_human_sequence(deleted) == [
        ("human", "write_authorization"),
        ("tool", "delete_novel_structure_items"),
    ]
    deleted_decision = next(
        record
        for record in deleted.interactions
        if record.interaction.kind.value == "human"
    )
    assert deleted_decision.human_second_confirmation_required is True
    assert deleted_decision.human_second_confirmation is True
    assert deleted.normalized_result["effect_tools"] == [
        "delete_novel_structure_items"
    ]
    assert deleted_tool.response_payload["changes"] == [
        {
            "kind": "volume",
            "item_id": "fixture_delete_volume",
            "action": "archived",
            "title": "fixture_delete",
        }
    ]
    assert _changed_refs(deleted_before, deleted_after) == set(
        deleted_after.payload["target_refs"]
    )

    cancelled = observations["structure_delete_cancelled_probe"]
    cancelled_before, cancelled_after = _snapshot_pair(
        cancelled,
        "resource_snapshot_novel_structure",
    )
    assert _human_decisions(cancelled) == [("write_authorization", False)]
    assert _tool_human_sequence(cancelled) == [
        ("human", "write_authorization")
    ]
    cancelled_decision = next(
        record
        for record in cancelled.interactions
        if record.interaction.kind.value == "human"
    )
    assert cancelled_decision.human_second_confirmation_required is True
    assert cancelled_decision.human_second_confirmation is False
    assert cancelled.run.final_answer == (
        "已按你的决定拒绝写入，本次没有修改正文。"
    )
    assert cancelled.runtime_facts.invocations == ()
    assert cancelled.normalized_result["effect_tools"] == []
    assert _changed_refs(cancelled_before, cancelled_after) == set()

    knowledge = observations["knowledge_create_update"]
    knowledge_tools = _tool_records(knowledge)
    knowledge_create = knowledge_tools[
        "create_confirmed_knowledge"
    ].response_payload
    knowledge_update_input = knowledge_tools[
        "update_confirmed_knowledge"
    ].request_payload
    knowledge_update_output = knowledge_tools[
        "update_confirmed_knowledge"
    ].response_payload
    knowledge_before, knowledge_after = _snapshot_pair(
        knowledge,
        "resource_snapshot_confirmed_knowledge",
    )
    assert _human_decisions(knowledge) == [
        ("write_authorization", True),
        ("write_authorization", True),
    ]
    assert _tool_human_sequence(knowledge) == [
        ("human", "write_authorization"),
        ("tool", "create_confirmed_knowledge"),
        ("human", "write_authorization"),
        ("tool", "update_confirmed_knowledge"),
    ]
    assert knowledge_update_input["card_id"] == knowledge_create["card"]["id"]
    assert knowledge_update_input["expected_updated_at"] == (
        knowledge_create["card"]["updated_at"]
    )
    assert knowledge_update_output["card"]["summary"] == (
        "雾港保存守灯记录与港务旧档的场所。"
    )
    assert knowledge_update_output["card"]["lifecycle"] == "confirmed"
    assert _changed_refs(knowledge_before, knowledge_after) == set(
        knowledge_after.payload["target_refs"]
    )

    denied = observations["write_authorization_denied"]
    denied_before, denied_after = _snapshot_pair(
        denied,
        "resource_snapshot_manuscript_chapter_001",
    )
    assert denied.runtime_facts.terminal.run_status == "write_rejected"
    assert denied.runtime_facts.terminal.stop_reason == "write_rejected"
    assert _human_decisions(denied) == [("write_authorization", False)]
    assert _tool_human_sequence(denied) == [
        ("tool", "preview_manuscript_patch"),
        ("human", "write_authorization"),
    ]
    assert [
        item.capability_name for item in denied.runtime_facts.invocations
    ] == ["preview_manuscript_patch"]
    assert denied.normalized_result["effect_tools"] == []
    assert denied.run.final_answer == (
        "已按你的决定拒绝写入，本次没有修改正文。"
    )
    assert _changed_refs(denied_before, denied_after) == set()
    assert _chapter_hash(denied_before) == _chapter_hash(denied_after)
