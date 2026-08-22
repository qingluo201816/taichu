from __future__ import annotations

import asyncio

from taichu.application.evaluations.general_agent_benchmark.models import (
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    ProviderExecutionState,
    SuiteArtifact,
    SuiteConclusion,
    SuiteRun,
    SuiteRunLifecycle,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.persistent_runtime import (
    JsonBenchmarkRunResourceService,
    JsonSuiteRunStore,
)


def _run(run_id: str, *, revision: int = 0) -> SuiteRun:
    return SuiteRun(
        run_id=run_id,
        revision=revision,
        lifecycle=SuiteRunLifecycle.QUEUED,
        conclusion=None,
        suite_content_hash="a" * 64,
        selected_case_ids=("case_a",),
        track=TrackKind.SYNTHETIC,
        provider_state=ProviderExecutionState.NOT_APPLICABLE,
        case_row_refs=(),
        pending_case_ids=("case_a",),
        terminal_artifact_ref=None,
    )


def test_interactive_runs_survive_restart_and_remain_newest(tmp_path) -> None:
    async def scenario() -> None:
        root = tmp_path / "runs"
        store = JsonSuiteRunStore(root)
        interactive = _run(
            "benchmark_run_20260806T010203Z_abcdef123456"
        )
        await store.create(interactive)

        reloaded = JsonSuiteRunStore(root)
        assert await reloaded.get(interactive.run_id) == interactive
        reloaded.restore_frozen(
            _run("benchmark_run_19700101T000000Z_abcdef123455")
        )
        runs, _, _ = await reloaded.list_snapshot()
        assert tuple(item.run_id for item in runs) == (
            interactive.run_id,
            "benchmark_run_19700101T000000Z_abcdef123455",
        )

    asyncio.run(scenario())


def test_interactive_terminal_artifact_survives_restart(tmp_path) -> None:
    root = tmp_path / "artifacts"
    artifact = SuiteArtifact(
        artifact_id="interactive_artifact",
        run_id="benchmark_run_20260806T010203Z_abcdef123456",
        conclusion=SuiteConclusion.FAILED,
        case_rows=(),
        evidence_bundles=(),
        provider_state=ProviderExecutionState.NOT_APPLICABLE,
        artifact_hash="b" * 64,
    )
    JsonBenchmarkRunResourceService(root).register(artifact)

    reloaded = JsonBenchmarkRunResourceService(root)
    assert reloaded.get_artifact(artifact.run_id) == artifact
