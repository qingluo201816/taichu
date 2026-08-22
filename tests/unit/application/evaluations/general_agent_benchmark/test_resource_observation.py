"""业务资源快照必须由真实 before/after 内容确定性派生。"""

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    ObservedResourceSnapshot,
)
from taichu.application.evaluations.general_agent_benchmark.resource_observation import (
    ResourceStateItem,
    ResourceStatePayload,
    project_resource_diffs,
)


def _snapshot(
    *,
    phase: str,
    resources: tuple[ResourceStateItem, ...],
    targets: tuple[str, ...] = (),
    protected: tuple[str, ...] = (),
) -> ObservedResourceSnapshot:
    payload = ResourceStatePayload(
        schema="taichu.general_agent_benchmark.resource_state@1",
        resources=resources,
        target_refs=targets,
        protected_refs=protected,
    ).model_dump(mode="json", by_alias=True)
    return ObservedResourceSnapshot(
        snapshot_ref="resource_snapshot_core_novel",
        phase=phase,
        content_sha256=canonical_sha256(payload),
        payload=payload,
    )


def test_unchanged_resources_are_projected_from_equal_snapshots() -> None:
    resource = ResourceStateItem(
        resource_ref="manuscript:chapter_001",
        state="present",
        content_sha256="1" * 64,
    )

    diff = project_resource_diffs(
        (
            _snapshot(phase="before", resources=(resource,)),
            _snapshot(phase="after", resources=(resource,)),
        )
    )

    assert len(diff) == 1
    assert diff[0].actual_change == "unchanged"
    assert diff[0].changed_refs == ()


def test_target_only_change_keeps_protected_resources_unchanged() -> None:
    before = (
        ResourceStateItem(
            resource_ref="manuscript:chapter_001",
            state="present",
            content_sha256="1" * 64,
        ),
        ResourceStateItem(
            resource_ref="manuscript:chapter_002",
            state="present",
            content_sha256="2" * 64,
        ),
    )
    after = (
        before[0].model_copy(update={"content_sha256": "3" * 64}),
        before[1],
    )

    diff = project_resource_diffs(
        (
            _snapshot(
                phase="before",
                resources=before,
                targets=("manuscript:chapter_001",),
                protected=("manuscript:chapter_002",),
            ),
            _snapshot(
                phase="after",
                resources=after,
                targets=("manuscript:chapter_001",),
                protected=("manuscript:chapter_002",),
            ),
        )
    )[0]

    assert diff.actual_change == "updated"
    assert diff.changed_refs == ("manuscript:chapter_001",)
    assert diff.protected_changed_refs == ()


def test_malformed_or_incomplete_pairs_do_not_manufacture_a_diff() -> None:
    payload = {
        "schema": "unknown",
        "resources": [],
    }
    malformed = ObservedResourceSnapshot(
        snapshot_ref="resource_snapshot_core_novel",
        phase="before",
        content_sha256=canonical_sha256(payload),
        payload=payload,
    )

    assert project_resource_diffs((malformed,)) == ()


def test_mixed_created_and_updated_targets_are_projected_without_key_error() -> None:
    existing_before = ResourceStateItem(
        resource_ref="structure:volume:existing",
        state="present",
        content_sha256="1" * 64,
    )
    existing_after = existing_before.model_copy(
        update={"content_sha256": "2" * 64}
    )
    created = ResourceStateItem(
        resource_ref="structure:volume:created",
        state="present",
        content_sha256="3" * 64,
    )
    targets = (
        "structure:volume:created",
        "structure:volume:existing",
    )

    diff = project_resource_diffs(
        (
            _snapshot(
                phase="before",
                resources=(existing_before,),
                targets=targets,
            ),
            _snapshot(
                phase="after",
                resources=(created, existing_after),
                targets=targets,
            ),
        )
    )[0]

    assert diff.actual_change == "target_only"
