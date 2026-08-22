"""评测资源前后态的规范化快照与确定性差异投影。"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    ObservedResourceSnapshot,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    ResourceDiffObservation,
)


class ResourceStateItem(BenchmarkModel):
    """一个业务资源在指定阶段的存在性和内容身份。"""

    resource_ref: str = Field(min_length=1, max_length=512)
    state: Literal["present", "absent"]
    content_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def _content_matches_state(self) -> ResourceStateItem:
        if (self.state == "present") is (self.content_sha256 is None):
            raise ValueError("存在的资源必须有内容哈希，不存在的资源不得伪造哈希。")
        return self


class ResourceStatePayload(BenchmarkModel):
    """ObservedResourceSnapshot.payload 使用的固定 schema。"""

    schema_: Literal[
        "taichu.general_agent_benchmark.resource_state@1"
    ] = Field(alias="schema")
    resources: tuple[ResourceStateItem, ...]
    target_refs: tuple[str, ...] = ()
    protected_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _refs_are_canonical(self) -> ResourceStatePayload:
        resource_refs = tuple(item.resource_ref for item in self.resources)
        if resource_refs != tuple(sorted(set(resource_refs))):
            raise ValueError("资源状态必须按 resource_ref 排序且不得重复。")
        for field_name in ("target_refs", "protected_refs"):
            refs = getattr(self, field_name)
            if refs != tuple(sorted(set(refs))):
                raise ValueError(f"{field_name} 必须排序且不得重复。")
        if set(self.target_refs) & set(self.protected_refs):
            raise ValueError("目标资源和受保护资源不得重叠。")
        return self


def project_resource_diffs(
    snapshots: tuple[ObservedResourceSnapshot, ...],
) -> tuple[ResourceDiffObservation, ...]:
    """只从同 ref 的唯一 before/after 规范快照派生资源差异。"""

    grouped: dict[
        str,
        dict[str, list[ObservedResourceSnapshot]],
    ] = defaultdict(lambda: defaultdict(list))
    for snapshot in snapshots:
        grouped[snapshot.snapshot_ref][snapshot.phase].append(snapshot)

    projected: list[ResourceDiffObservation] = []
    for snapshot_ref in sorted(grouped):
        phases = grouped[snapshot_ref]
        before_rows = phases.get("before", [])
        after_rows = phases.get("after", [])
        if len(before_rows) != 1 or len(after_rows) != 1:
            continue
        before = before_rows[0]
        after = after_rows[0]
        try:
            before_payload = ResourceStatePayload.model_validate(before.payload)
            after_payload = ResourceStatePayload.model_validate(after.payload)
        except ValueError:
            continue
        before_map = {
            item.resource_ref: item for item in before_payload.resources
        }
        after_map = {
            item.resource_ref: item for item in after_payload.resources
        }
        all_refs = tuple(sorted(set(before_map) | set(after_map)))
        changed_refs = tuple(
            resource_ref
            for resource_ref in all_refs
            if before_map.get(resource_ref) != after_map.get(resource_ref)
        )
        targets = tuple(
            sorted(
                set(before_payload.target_refs)
                | set(after_payload.target_refs)
            )
        )
        protected = tuple(
            sorted(
                set(before_payload.protected_refs)
                | set(after_payload.protected_refs)
            )
        )
        actual_change = _actual_change(
            changed_refs=changed_refs,
            target_refs=targets,
            before=before_map,
            after=after_map,
        )
        projected.append(
            ResourceDiffObservation(
                resource_snapshot_ref=snapshot_ref,
                actual_change=actual_change,
                before_sha256=before.content_sha256,
                after_sha256=after.content_sha256,
                target_refs=targets,
                changed_refs=changed_refs,
                protected_refs=protected,
                protected_changed_refs=tuple(
                    item for item in changed_refs if item in set(protected)
                ),
            )
        )
    return tuple(projected)


def _actual_change(
    *,
    changed_refs: tuple[str, ...],
    target_refs: tuple[str, ...],
    before: dict[str, ResourceStateItem],
    after: dict[str, ResourceStateItem],
) -> Literal["unchanged", "target_only", "created", "updated", "deleted"]:
    if not changed_refs:
        return "unchanged"
    if all(
        before.get(item, ResourceStateItem(resource_ref=item, state="absent"))
        .state
        == "absent"
        and after[item].state == "present"
        for item in changed_refs
    ):
        return "created"
    if all(
        before.get(
            item,
            ResourceStateItem(resource_ref=item, state="absent"),
        ).state
        == "present"
        and after.get(
            item,
            ResourceStateItem(resource_ref=item, state="absent"),
        ).state
        == "absent"
        for item in changed_refs
    ):
        return "deleted"
    if all(
        before.get(
            item,
            ResourceStateItem(resource_ref=item, state="absent"),
        ).state
        == "present"
        and after.get(
            item,
            ResourceStateItem(resource_ref=item, state="absent"),
        ).state
        == "present"
        for item in changed_refs
    ):
        return "updated"
    if target_refs and set(changed_refs) <= set(target_refs):
        return "target_only"
    return "updated"


__all__ = [
    "ResourceStateItem",
    "ResourceStatePayload",
    "project_resource_diffs",
]
