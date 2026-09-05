"""LLM 调用 JSONL 仓储分页、筛选与聚合测试。"""

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from typing import Literal

from taichu.application.models.llm_usage import LLMCallRecord, LLMUsageQuery
from taichu.infrastructure.llm_usage import JsonlLLMUsageRepository


class JsonlLLMUsageRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_date_filters_compare_instants_not_timestamp_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = JsonlLLMUsageRepository(Path(temporary_directory))
            for index, stamp in enumerate([
                "2026-07-11T23:59:59Z",
                "2026-07-12T00:00:00.000000Z",
                "2026-07-12T07:59:59+08:00",
            ], start=1):
                await repository.append(_record(f"call-{index}", "model-a", "completed").model_copy(update={"started_at": stamp}))
            query = LLMUsageQuery(started_from="2026-07-11T00:00:00.000Z", started_to="2026-07-11T23:59:59.999Z")
            page = await repository.list_calls(query)
            summary = await repository.summarize(query)
            trend = await repository.token_trend(query, "day")
        self.assertEqual({record.call_id for record in page.items}, {"call-1", "call-3"})
        self.assertEqual(summary.total_calls, 2)
        self.assertEqual(trend[0].call_count, 2)

    async def test_pagination_filtering_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = JsonlLLMUsageRepository(Path(temporary_directory))
            await repository.append(_record("call-1", "model-a", "completed"))
            await repository.append(_record("call-2", "model-b", "failed"))
            await repository.append(_record("call-3", "model-a", "completed"))
            await repository.append(
                _record("call-4", "model-a", "completed").model_copy(
                    update={
                        "started_at": "2026-07-12T08:30:00Z",
                        "finished_at": "2026-07-12T08:30:01Z",
                    }
                )
            )

            page = await repository.list_calls(
                LLMUsageQuery(page=1, page_size=1, model_id="model-a")
            )
            summary = await repository.summarize(LLMUsageQuery())
            trend = await repository.token_trend(LLMUsageQuery(), "day")

        self.assertEqual(page.total, 3)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(summary.total_calls, 4)
        self.assertEqual(summary.completed_calls, 3)
        self.assertEqual(summary.failed_calls, 1)
        self.assertEqual(summary.total_tokens, 40)
        self.assertEqual(summary.actual_cost, Decimal("0.2"))
        self.assertEqual(summary.estimated_cost, Decimal("0.1"))
        self.assertEqual(summary.unavailable_cost_calls, 2)
        self.assertEqual(len(summary.by_model), 2)
        self.assertEqual(len(trend), 2)
        self.assertEqual(trend[0].bucket_start, "2026-07-11T00:00:00Z")
        self.assertEqual(trend[0].total_tokens, 30)
        self.assertEqual(trend[1].total_tokens, 10)


def _record(
    call_id: str,
    model_id: str,
    status: Literal["running", "completed", "failed"],
) -> LLMCallRecord:
    cost_kind: Literal["actual", "estimated", "unavailable"]
    if call_id == "call-1":
        cost_kind = "actual"
    elif call_id == "call-3":
        cost_kind = "estimated"
    else:
        cost_kind = "unavailable"
    return LLMCallRecord(
        call_id=call_id,
        task_type="writing",
        task_name="写作",
        model_id=model_id,
        model_display_name=model_id,
        upstream_model=model_id,
        wire_protocol="openai_responses",
        status=status,
        started_at=f"2026-07-11T00:00:0{call_id[-1]}Z",
        finished_at=f"2026-07-11T00:00:0{call_id[-1]}Z",
        duration_ms=100,
        input_tokens=5,
        output_tokens=5,
        total_tokens=10,
        cost_amount=(
            Decimal("0.2")
            if call_id == "call-1"
            else Decimal("0.1") if call_id == "call-3" else None
        ),
        cost_kind=cost_kind,
    )
