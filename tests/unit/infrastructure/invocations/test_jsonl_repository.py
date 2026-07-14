"""脱敏能力调用记录读取测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from taichu.application.invocations.models import (
    InvocationStatus,
    InvocationTraceRecord,
)
from taichu.infrastructure.invocations import JsonlInvocationTraceRepository


def test_list_for_run_filters_orders_limits_and_skips_bad_lines(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = JsonlInvocationTraceRepository(tmp_path)
        await repository.append(_record("trace_2", "run_a", "2026-07-14T00:00:02Z"))
        await repository.append(_record("trace_other", "run_b", "2026-07-14T00:00:01Z"))
        await repository.append(_record("trace_1", "run_a", "2026-07-14T00:00:01Z"))
        path = tmp_path / "derived" / "capability_invocations" / "calls.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write("不是合法 JSON\n")

        records, total = await repository.list_for_run("run_a", limit=1)

        assert total == 2
        assert [item.trace_id for item in records] == ["trace_2"]

    asyncio.run(scenario())


def _record(trace_id: str, run_id: str, started_at: str) -> InvocationTraceRecord:
    return InvocationTraceRecord(
        trace_id=trace_id,
        capability_type="tool",
        capability_name="read_manuscript",
        task_id="task_test",
        run_id=run_id,
        call_id=f"call_{trace_id}",
        caller_type="orchestrator",
        caller_name="general_writing_orchestrator",
        status=InvocationStatus.COMPLETED,
        input_sha256="a" * 64,
        input_char_count=10,
        started_at=started_at,
        finished_at=started_at,
        duration_ms=1,
    )
