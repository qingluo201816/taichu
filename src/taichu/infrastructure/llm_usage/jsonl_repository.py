"""追加写入的本地 LLM 调用遥测仓储。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, TypeVar

from taichu.application.models.llm_usage import (
    LLMCallRecord,
    LLMUsageGroup,
    LLMUsagePage,
    LLMUsageQuery,
    LLMUsageSummary,
    LLMTokenTrendPoint,
)


_GroupKey = TypeVar("_GroupKey", bound=str)


class JsonlLLMUsageRepository:
    """将每次完成或失败的调用作为单行 JSON 追加保存。"""

    def __init__(self, assets_root: Path) -> None:
        self._path = assets_root / "derived" / "llm_usage" / "calls.jsonl"
        self._write_lock = asyncio.Lock()

    async def append(self, record: LLMCallRecord) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self._append_sync, record)

    async def get(self, call_id: str) -> LLMCallRecord | None:
        records = await self._read_all()
        return next((item for item in records if item.call_id == call_id), None)

    async def list_calls(self, query: LLMUsageQuery) -> LLMUsagePage:
        records = self._filter(await self._read_all(), query)
        records.sort(key=lambda item: item.started_at, reverse=True)
        start = (query.page - 1) * query.page_size
        return LLMUsagePage(
            items=records[start : start + query.page_size],
            page=query.page,
            page_size=query.page_size,
            total=len(records),
        )

    async def summarize(self, query: LLMUsageQuery) -> LLMUsageSummary:
        records = self._filter(await self._read_all(), query)
        totals = _aggregate(records, key="all", display_name="全部调用")
        return LLMUsageSummary(
            total_calls=totals.total_calls,
            completed_calls=totals.completed_calls,
            failed_calls=totals.failed_calls,
            input_tokens=totals.input_tokens,
            cached_input_tokens=totals.cached_input_tokens,
            output_tokens=totals.output_tokens,
            reasoning_tokens=totals.reasoning_tokens,
            total_tokens=totals.total_tokens,
            actual_cost=totals.actual_cost,
            estimated_cost=totals.estimated_cost,
            unavailable_cost_calls=totals.unavailable_cost_calls,
            average_duration_ms=totals.average_duration_ms,
            by_model=_group(
                records,
                lambda item: item.model_id,
                lambda item: item.model_display_name,
            ),
            by_task_type=_group(
                records,
                lambda item: item.task_type,
                lambda item: item.task_name or item.task_type,
            ),
        )

    async def token_trend(
        self, query: LLMUsageQuery, bucket: Literal["hour", "day"]
    ) -> list[LLMTokenTrendPoint]:
        records = self._filter(await self._read_all(), query)
        buckets: dict[str, list[LLMCallRecord]] = {}
        for record in records:
            bucket_start = _bucket_start(record.started_at, bucket)
            if bucket_start is not None:
                buckets.setdefault(bucket_start, []).append(record)
        return [
            _trend_point(bucket_start, buckets[bucket_start])
            for bucket_start in sorted(buckets)
        ]

    def _append_sync(self, record: LLMCallRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record.model_dump_json())
            stream.write("\n")

    async def _read_all(self) -> list[LLMCallRecord]:
        return await asyncio.to_thread(self._read_all_sync)

    def _read_all_sync(self) -> list[LLMCallRecord]:
        if not self._path.exists():
            return []
        records: list[LLMCallRecord] = []
        with self._path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    records.append(LLMCallRecord.model_validate_json(line))
        return records

    @staticmethod
    def _filter(
        records: list[LLMCallRecord], query: LLMUsageQuery
    ) -> list[LLMCallRecord]:
        return [
            item
            for item in records
            if (query.started_from is None or item.started_at >= query.started_from)
            and (query.started_to is None or item.started_at <= query.started_to)
            and (query.model_id is None or item.model_id == query.model_id)
            and (query.task_type is None or item.task_type == query.task_type)
            and (query.status is None or item.status == query.status)
        ]


def _group(
    records: list[LLMCallRecord],
    key_getter: Callable[[LLMCallRecord], str],
    label_getter: Callable[[LLMCallRecord], str],
) -> list[LLMUsageGroup]:
    buckets: dict[str, list[LLMCallRecord]] = {}
    labels: dict[str, str] = {}
    for record in records:
        key = key_getter(record)
        buckets.setdefault(key, []).append(record)
        labels.setdefault(key, label_getter(record))
    return [
        _aggregate(items, key=key, display_name=labels[key])
        for key, items in sorted(buckets.items())
    ]


def _aggregate(
    records: list[LLMCallRecord], *, key: str, display_name: str
) -> LLMUsageGroup:
    def token_sum(field: str) -> int | None:
        values = [getattr(item, field) for item in records]
        present = [value for value in values if value is not None]
        return sum(present) if present else None

    durations = [item.duration_ms for item in records]
    return LLMUsageGroup(
        key=key,
        display_name=display_name,
        total_calls=len(records),
        completed_calls=sum(item.status == "completed" for item in records),
        failed_calls=sum(item.status == "failed" for item in records),
        input_tokens=token_sum("input_tokens"),
        cached_input_tokens=token_sum("cached_input_tokens"),
        output_tokens=token_sum("output_tokens"),
        reasoning_tokens=token_sum("reasoning_tokens"),
        total_tokens=token_sum("total_tokens"),
        actual_cost=sum(
            (
                item.cost_amount or Decimal("0")
                for item in records
                if item.cost_kind == "actual"
            ),
            Decimal("0"),
        ),
        estimated_cost=sum(
            (
                item.cost_amount or Decimal("0")
                for item in records
                if item.cost_kind == "estimated"
            ),
            Decimal("0"),
        ),
        unavailable_cost_calls=sum(
            item.cost_kind == "unavailable" for item in records
        ),
        average_duration_ms=(sum(durations) // len(durations) if durations else 0),
    )


def _bucket_start(value: str, bucket: Literal["hour", "day"]) -> str | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    parsed = parsed.astimezone(UTC)
    if bucket == "hour":
        parsed = parsed.replace(minute=0, second=0, microsecond=0)
    else:
        parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed.isoformat().replace("+00:00", "Z")


def _trend_point(
    bucket_start: str, records: list[LLMCallRecord]
) -> LLMTokenTrendPoint:
    def token_sum(field: str) -> int | None:
        values = [getattr(record, field) for record in records]
        present = [value for value in values if value is not None]
        return sum(present) if present else None

    return LLMTokenTrendPoint(
        bucket_start=bucket_start,
        call_count=len(records),
        input_tokens=token_sum("input_tokens"),
        cached_input_tokens=token_sum("cached_input_tokens"),
        output_tokens=token_sum("output_tokens"),
        reasoning_tokens=token_sum("reasoning_tokens"),
        total_tokens=token_sum("total_tokens"),
    )
