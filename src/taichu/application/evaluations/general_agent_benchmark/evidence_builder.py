"""从八类既有 Runtime 只读事实构建最小类型化证据包。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from taichu.application.contracts.runtime_evidence import (
    EvidenceItem as SourceEvidenceItem,
    EvidenceProblem,
    RuntimeEvidenceReader,
)
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    ArtifactType,
    BenchmarkModel,
    FixtureSnapshotId,
    StableId,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    EvidenceAvailability,
    EvidenceBundle,
    EvidenceBundleIdentity,
)


class EvidenceBuildRequest(BenchmarkModel):
    suite_id: StableId
    case_id: StableId
    case_execution_id: str = Field(pattern=r"^benchmark_case_[a-f0-9]{32}$")
    run_id: str = Field(min_length=1, max_length=200)
    checkpoint_thread_id: str = Field(min_length=1, max_length=200)
    track: TrackKind
    fixture_snapshot_id: FixtureSnapshotId


class ObservedArtifactAvailability(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"


class ObservedArtifact(BenchmarkModel):
    artifact_type: ArtifactType
    availability: ObservedArtifactAvailability
    identity: dict[str, str | int | bool | None]
    evidence_refs: tuple[StableId, ...]
    explanation: str = Field(min_length=1, max_length=1_000)


class BuiltEvidenceBundle(BenchmarkModel):
    bundle: EvidenceBundle
    artifacts: tuple[ObservedArtifact, ...] = Field(min_length=5, max_length=5)
    source_records: dict[StableId, tuple[dict[str, object], ...]]

    @model_validator(mode="after")
    def _all_artifact_slots_are_unique(self) -> BuiltEvidenceBundle:
        kinds = tuple(item.artifact_type for item in self.artifacts)
        if len(set(kinds)) != len(ArtifactType):
            raise ValueError("观察工件必须恰好覆盖五种类型。")
        return self


class EvidenceBundleBuilder:
    def __init__(self, reader: RuntimeEvidenceReader) -> None:
        self._reader = reader

    async def build(
        self,
        request: EvidenceBuildRequest,
    ) -> BuiltEvidenceBundle:
        (
            run_item,
            node_item,
            invocation_item,
            checkpoint_item,
            effect_item,
            replay_item,
        ) = await asyncio.gather(
            self._capture("run", lambda: self._reader.read_run(request.run_id)),
            self._capture(
                "nodes",
                lambda: self._reader.read_nodes(request.run_id),
            ),
            self._capture(
                "invocations",
                lambda: self._reader.read_invocations(request.run_id),
            ),
            self._capture(
                "checkpoint",
                lambda: self._reader.read_checkpoint(
                    request.checkpoint_thread_id
                ),
            ),
            self._capture(
                "effects",
                lambda: self._reader.read_effects(request.run_id),
            ),
            self._capture(
                "replays",
                lambda: self._reader.read_llm_replays(request.run_id),
            ),
        )
        run_item = _require_owner(
            "run",
            run_item,
            lambda value: getattr(value, "run_id", None) == request.run_id,
            "run_id 与案例运行不一致",
        )
        node_item = _require_owner(
            "nodes",
            node_item,
            lambda values: all(
                getattr(value, "run_id", None) == request.run_id
                for value in values
            ),
            "node run_id 与案例运行不一致",
        )
        invocation_item = _require_owner(
            "invocations",
            invocation_item,
            lambda values: all(
                getattr(value, "run_id", None) == request.run_id
                for value in values
            ),
            "invocation run_id 与案例运行不一致",
        )
        checkpoint_item = _require_owner(
            "checkpoint",
            checkpoint_item,
            lambda values: all(
                getattr(value, "thread_id", None)
                == request.checkpoint_thread_id
                for value in values
            ),
            "checkpoint thread_id 与请求不一致",
        )
        effect_item = _require_owner(
            "effects",
            effect_item,
            lambda values: all(
                getattr(value, "run_id", None) == request.run_id
                for value in values
            ),
            "effect run_id 与案例运行不一致",
        )
        replay_item = _require_owner(
            "replays",
            replay_item,
            lambda values: all(
                getattr(value, "run_id", None) == request.run_id
                for value in values
            ),
            "replay run_id 与案例运行不一致",
        )

        context_item = await self._context_item(request, run_item)
        llm_call_ids = (
            tuple(
                record.call_id
                for record in (invocation_item.value or ())
                if getattr(record, "capability_type", None) == "llm"
            )
            if invocation_item.availability is EvidenceAvailability.AVAILABLE
            else ()
        )
        usage_item = (
            await self._capture(
                "usage",
                lambda: self._reader.read_llm_usage(llm_call_ids),
            )
            if llm_call_ids
            else _missing_item("usage", "缺少可关联的 LLM call_id")
        )
        usage_item = _require_owner(
            "usage",
            usage_item,
            lambda values: all(
                getattr(value, "run_id", None) in {None, request.run_id}
                for value in values
            ),
            "usage run_id 与案例运行不一致",
        )

        items = {
            "run": run_item,
            "nodes": node_item,
            "invocations": invocation_item,
            "context": context_item,
            "checkpoint": checkpoint_item,
            "effects": effect_item,
            "replays": replay_item,
            "usage": usage_item,
        }
        availability = {
            kind: item.availability for kind, item in items.items()
        }
        problems = tuple(
            f"{kind}:{problem.code}:{problem.message}"
            for kind, item in items.items()
            for problem in item.problems
        )
        source_records = {
            kind: _records(item)
            for kind, item in items.items()
        }
        artifacts = _observed_artifacts(items)
        content_payload = {
            "request": request.model_dump(mode="json"),
            "availability": {
                key: value.value for key, value in availability.items()
            },
            "problems": problems,
            "source_records": source_records,
            "artifacts": [
                artifact.model_dump(mode="json") for artifact in artifacts
            ],
        }
        bundle_hash = canonical_sha256(content_payload)
        bundle = EvidenceBundle(
            identity=EvidenceBundleIdentity(
                bundle_id=f"evidence_{bundle_hash}",
                bundle_hash=bundle_hash,
                suite_id=request.suite_id,
                case_id=request.case_id,
                run_id=request.run_id,
                case_execution_id=request.case_execution_id,
                track=request.track,
                fixture_snapshot_id=request.fixture_snapshot_id,
            ),
            availability=availability,
            problems=problems,
        )
        return BuiltEvidenceBundle(
            bundle=bundle,
            artifacts=artifacts,
            source_records=source_records,
        )

    async def _context_item(
        self,
        request: EvidenceBuildRequest,
        run_item: SourceEvidenceItem[Any],
    ) -> SourceEvidenceItem[Any]:
        if (
            run_item.availability is not EvidenceAvailability.AVAILABLE
            or run_item.value is None
        ):
            return _missing_item("context", "运行证据不可用，无法定位快照")
        snapshot_id = getattr(run_item.value, "context_snapshot_id", None)
        if not snapshot_id:
            return _missing_item("context", "运行记录缺少 context_snapshot_id")
        item = await self._capture(
            "context",
            lambda: self._reader.read_context(snapshot_id, request.run_id),
        )
        return _require_owner(
            "context",
            item,
            lambda value: (
                getattr(value, "run_id", None) == request.run_id
                and getattr(value, "snapshot_id", None) == snapshot_id
            ),
            "context run_id 或 snapshot_id 与运行记录不一致",
        )

    async def _capture(
        self,
        kind: str,
        read: Callable[[], Awaitable[SourceEvidenceItem[Any]]],
    ) -> SourceEvidenceItem[Any]:
        try:
            return await read()
        except Exception as error:
            return SourceEvidenceItem(
                value=None,
                availability=EvidenceAvailability.CORRUPT,
                problems=(
                    EvidenceProblem(
                        code="read_failed",
                        message=f"{kind} 证据不可读取：{type(error).__name__}",
                    ),
                ),
            )


def _require_owner(
    kind: str,
    item: SourceEvidenceItem[Any],
    matches: Callable[[Any], bool],
    message: str,
) -> SourceEvidenceItem[Any]:
    if (
        item.availability is not EvidenceAvailability.AVAILABLE
        or item.value is None
        or matches(item.value)
    ):
        return item
    return SourceEvidenceItem(
        value=None,
        availability=EvidenceAvailability.CONFLICTING,
        problems=(
            EvidenceProblem(
                code="owner_mismatch",
                message=message,
                locator=kind,
            ),
        ),
    )


def _missing_item(kind: str, message: str) -> SourceEvidenceItem[Any]:
    return SourceEvidenceItem(
        value=None,
        availability=EvidenceAvailability.MISSING,
        problems=(
            EvidenceProblem(
                code="missing",
                message=message,
                locator=kind,
            ),
        ),
    )


def _records(item: SourceEvidenceItem[Any]) -> tuple[dict[str, object], ...]:
    if item.availability is not EvidenceAvailability.AVAILABLE:
        return ()
    value = item.value
    values = value if isinstance(value, tuple) else (value,)
    return tuple(
        record.model_dump(mode="json")
        for record in values
        if record is not None
    )


def _observed_artifacts(
    items: dict[str, SourceEvidenceItem[Any]],
) -> tuple[ObservedArtifact, ...]:
    run_item = items["run"]
    invocation_item = items["invocations"]
    effect_item = items["effects"]
    run_available = run_item.availability is EvidenceAvailability.AVAILABLE
    invocations_available = (
        invocation_item.availability is EvidenceAvailability.AVAILABLE
    )
    effects_available = (
        effect_item.availability is EvidenceAvailability.AVAILABLE
    )
    capability_names = tuple(
        record.capability_name
        for record in (invocation_item.value or ())
        if record.capability_type in {"tool", "subagent"}
    )
    human_waiting = (
        run_available
        and run_item.value is not None
        and getattr(run_item.value, "status", None) == "waiting_human"
    )
    return (
        ObservedArtifact(
            artifact_type=ArtifactType.FINAL_ANSWER,
            availability=ObservedArtifactAvailability.UNAVAILABLE,
            identity={},
            evidence_refs=("evidence_run",),
            explanation="运行只读摘要不复制最终回答正文，等待专用工件来源。",
        ),
        ObservedArtifact(
            artifact_type=ArtifactType.SOURCE_REFERENCE,
            availability=ObservedArtifactAvailability.UNAVAILABLE,
            identity={},
            evidence_refs=("evidence_nodes",),
            explanation="节点只读摘要未复制来源引用，不能推测来源工件。",
        ),
        ObservedArtifact(
            artifact_type=ArtifactType.CAPABILITY_ARTIFACT,
            availability=(
                ObservedArtifactAvailability.PRESENT
                if invocations_available and capability_names
                else (
                    ObservedArtifactAvailability.ABSENT
                    if invocations_available
                    else ObservedArtifactAvailability.UNAVAILABLE
                )
            ),
            identity={
                "capability_count": len(capability_names),
                "capability_names": ",".join(capability_names),
            },
            evidence_refs=("evidence_invocations",),
            explanation="仅保存真实 invocation 中的能力名称与数量。",
        ),
        ObservedArtifact(
            artifact_type=ArtifactType.WRITE_CANDIDATE,
            availability=ObservedArtifactAvailability.UNAVAILABLE,
            identity={"effect_count": len(effect_item.value or ())},
            evidence_refs=("evidence_effects",),
            explanation=(
                "effect 摘要不包含候选类型，"
                + ("不能把 effect 推测成写候选。" if effects_available else "证据不可用。")
            ),
        ),
        ObservedArtifact(
            artifact_type=ArtifactType.HUMAN_INTERVENTION,
            availability=(
                ObservedArtifactAvailability.PRESENT
                if human_waiting
                else (
                    ObservedArtifactAvailability.ABSENT
                    if run_available
                    else ObservedArtifactAvailability.UNAVAILABLE
                )
            ),
            identity={
                "run_status": (
                    getattr(run_item.value, "status", None)
                    if run_item.value is not None
                    else None
                )
            },
            evidence_refs=("evidence_run",),
            explanation="只按运行状态观察人工介入，不补造请求正文。",
        ),
    )
