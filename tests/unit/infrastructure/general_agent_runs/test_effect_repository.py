"""通用 Agent 写副作用追加日志测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from taichu.application.general_agent.recovery import EffectRecord, EffectStatus
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentEffectRepository,
)


def test_effect_journal_appends_and_restores_latest_event(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = JsonGeneralAgentEffectRepository(tmp_path)
        started = _record(EffectStatus.STARTED, event_suffix="1")
        succeeded = _record(
            EffectStatus.SUCCEEDED,
            event_suffix="2",
            output={"chapter_id": "chapter-8"},
        )

        await repository.append(started)
        await repository.append(succeeded)

        restored = JsonGeneralAgentEffectRepository(tmp_path)
        events = await restored.list_effects(started.run_id)
        assert [event.status for event in events] == [
            EffectStatus.STARTED,
            EffectStatus.SUCCEEDED,
        ]
        assert await restored.latest(started.effect_id) == succeeded

    asyncio.run(scenario())


def test_effect_journal_delete_is_scoped_to_run(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = JsonGeneralAgentEffectRepository(tmp_path)
        record = _record(EffectStatus.PREPARED, event_suffix="3")
        await repository.append(record)

        assert await repository.delete_run(record.run_id)
        assert await repository.list_effects(record.run_id) == []
        assert not await repository.delete_run(record.run_id)

    asyncio.run(scenario())


def _record(
    status: EffectStatus,
    *,
    event_suffix: str,
    output: dict[str, object] | None = None,
) -> EffectRecord:
    return EffectRecord(
        event_id=f"effect_event_{event_suffix.zfill(32)}",
        effect_id="effect_00000000000000000000000000000001",
        attempt_id="attempt_00000000000000000000000000000001",
        run_id="general_run_20260720_030303_abcdef",
        plan_revision=1,
        node_id="write_chapter",
        tool_name="apply_manuscript_patch",
        status=status,
        input_sha256="0" * 64,
        idempotency_key="run:1:write_chapter",
        resource_scopes=["manuscript:chapter-8"],
        authorization_reference="grant-1",
        output=output or {},
        created_at="2026-07-20T03:03:03Z",
    )
