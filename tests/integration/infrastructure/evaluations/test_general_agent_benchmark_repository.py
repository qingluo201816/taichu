"""需求 2.1-2.16：append-only 工件、索引、幂等和闭包租约。"""

from __future__ import annotations

from pathlib import Path

import pytest

from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    ArtifactConflictError,
    GeneralAgentBenchmarkArtifactRepository,
    LeaseConflictError,
)


def test_repository_creates_only_declared_benchmark_layout(tmp_path: Path) -> None:
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path / "benchmarks")
    repository.ensure_layout()
    assert {path.name for path in repository.root.iterdir()} == {
        "runs",
        "experiments",
        "iterations",
        "issue-correlations",
        "comparisons",
        "closure-leases",
        "indexes",
        "idempotency",
        "workspaces",
    }


def test_immutable_artifact_cannot_be_overwritten(tmp_path: Path) -> None:
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path / "benchmarks")
    first = repository.append_immutable(
        collection="runs",
        object_id="run_alpha",
        payload={"revision": 1, "state": "completed"},
    )
    replay = repository.append_immutable(
        collection="runs",
        object_id="run_alpha",
        payload={"state": "completed", "revision": 1},
    )
    assert replay == first

    with pytest.raises(ArtifactConflictError):
        repository.append_immutable(
            collection="runs",
            object_id="run_alpha",
            payload={"revision": 2, "state": "changed"},
        )
    assert repository.read("runs", "run_alpha")["revision"] == 1


def test_idempotency_claim_returns_same_result_and_hides_raw_key(
    tmp_path: Path,
) -> None:
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path / "benchmarks")
    first = repository.claim_idempotency(
        key="作者传入的敏感幂等键",
        submission_hash="a" * 64,
        result_ref="runs/run_alpha.json",
    )
    second = repository.claim_idempotency(
        key="作者传入的敏感幂等键",
        submission_hash="a" * 64,
        result_ref="runs/run_alpha.json",
    )
    assert first == second
    names = [path.name for path in (repository.root / "idempotency").iterdir()]
    assert all("敏感" not in name for name in names)

    with pytest.raises(ArtifactConflictError):
        repository.claim_idempotency(
            key="作者传入的敏感幂等键",
            submission_hash="b" * 64,
            result_ref="runs/run_beta.json",
        )


def test_index_replace_is_atomic_and_closure_lease_is_revisioned(
    tmp_path: Path,
) -> None:
    repository = GeneralAgentBenchmarkArtifactRepository(tmp_path / "benchmarks")
    repository.replace_index("latest_runs", {"revision": 1})
    repository.replace_index("latest_runs", {"revision": 2})
    assert repository.read("indexes", "latest_runs") == {"revision": 2}

    lease = repository.acquire_closure_lease(
        lease_key="suite_hash:defect_hash",
        owner="worker_a",
        expected_revision=0,
        expires_at="2026-07-27T01:00:00Z",
    )
    assert lease["revision"] == 1
    with pytest.raises(LeaseConflictError):
        repository.acquire_closure_lease(
            lease_key="suite_hash:defect_hash",
            owner="worker_b",
            expected_revision=0,
            expires_at="2026-07-27T01:00:00Z",
        )
