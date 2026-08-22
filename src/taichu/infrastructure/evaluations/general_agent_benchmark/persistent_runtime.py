"""网页发起 Benchmark 的持久化运行与终态工件存储。"""

from __future__ import annotations

import json
from pathlib import Path

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    InMemorySuiteRunStore,
)
from taichu.application.evaluations.general_agent_benchmark.resources import (
    BenchmarkRunResourceService,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    SuiteArtifact,
    SuiteRun,
)


class JsonSuiteRunStore(InMemorySuiteRunStore):
    """保留内存快照语义，同时把网页运行逐条原子落盘。"""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        for path in sorted(self._root.glob("benchmark_run_*.json")):
            self.restore_frozen(
                SuiteRun.model_validate_json(path.read_text(encoding="utf-8"))
            )

    async def create(self, run: SuiteRun) -> SuiteRun:
        created = await super().create(run)
        self._persist(created)
        return created

    async def save(
        self,
        run: SuiteRun,
        *,
        expected_revision: int,
    ) -> SuiteRun:
        saved = await super().save(
            run,
            expected_revision=expected_revision,
        )
        self._persist(saved)
        return saved

    def _record_snapshot(self) -> None:
        self._index_revision += 1
        runs = tuple(
            sorted(
                self._runs.values(),
                key=lambda item: item.run_id,
                reverse=True,
            )
        )
        token = canonical_sha256(
            {
                "index_revision": self._index_revision,
                "runs": [
                    {
                        "run_id": item.run_id,
                        "revision": item.revision,
                    }
                    for item in runs
                ],
            }
        )
        self._snapshots[token] = (runs, self._index_revision)

    def _persist(self, run: SuiteRun) -> None:
        target = self._root / f"{run.run_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                run.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)


class JsonBenchmarkRunResourceService(BenchmarkRunResourceService):
    """持久化网页运行的终态案例、证据与套件工件。"""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._loading = True
        for path in sorted(self._root.glob("*.json")):
            super().register(
                SuiteArtifact.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            )
        self._loading = False

    def register(self, artifact: SuiteArtifact) -> SuiteArtifact:
        registered = super().register(artifact)
        if not self._loading and artifact.run_id.startswith("benchmark_run_20"):
            self._persist(registered)
        return registered

    def _persist(self, artifact: SuiteArtifact) -> None:
        target = self._root / f"{artifact.run_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                artifact.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
