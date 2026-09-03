"""由网页控制面启动的隔离 Synthetic Benchmark 执行适配器。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    load_claim_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    CapabilityCatalogSnapshot,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.resources import (
    BenchmarkRunResourceService,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    SuiteArtifact,
    SuiteConclusion,
    SuiteRun,
)
from taichu.application.evaluations.general_agent_benchmark.suite_artifact_builder import (
    build_synthetic_suite_artifact,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
    FinalClaimsAssertionSpec,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    SyntheticSuiteBaselineResult,
    SyntheticSuiteRunner,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_environment import (
    SyntheticFixtureRuntime,
)


class InteractiveSyntheticExecution:
    """把完整隔离套件接入通用生命周期 Runner。

    生命周期逐案登记结果；真实 Synthetic Runtime 首次取案时一次执行本次选择，
    随后逐案返回已冻结的案例引用，最终注册唯一终态工件。
    """

    def __init__(
        self,
        *,
        suite: AuthoredSuiteSpec,
        fixture_root: Path,
        claim_catalog_path: Path,
        workspaces_root: Path,
        mongodb_uri: str,
        capability_catalog: CapabilityCatalogSnapshot,
    ) -> None:
        self._suite = suite
        self._fixture_root = fixture_root
        self._workspaces_root = workspaces_root
        self._mongodb_uri = mongodb_uri
        self._capability_catalog = capability_catalog
        self._oracle = TypedOracle(
            catalog=load_synthetic_oracle_catalog(
                suite=suite,
                fixture_root=fixture_root,
                claim_catalog_path=claim_catalog_path,
            )
        )
        self._results: dict[str, SuiteArtifact] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._resources: BenchmarkRunResourceService | None = None

    def bind_resources(self, resources: BenchmarkRunResourceService) -> None:
        self._resources = resources

    async def execute_case(self, run: SuiteRun, case_id: str) -> str:
        artifact = await self._artifact_for(run)
        position = next(
            index
            for index, row in enumerate(artifact.case_rows)
            if row.case_id == case_id
        )
        return f"{artifact.artifact_id}#/case_rows/{position}"

    async def finalize(
        self,
        run: SuiteRun,
    ) -> tuple[SuiteConclusion, str]:
        artifact = self._results.pop(run.run_id)
        self._locks.pop(run.run_id, None)
        if self._resources is None:
            raise RuntimeError("评测终态资源服务尚未绑定。")
        self._resources.register(artifact)
        return artifact.conclusion, artifact.artifact_id

    async def _artifact_for(self, run: SuiteRun) -> SuiteArtifact:
        existing = self._results.get(run.run_id)
        if existing is not None:
            return existing
        lock = self._locks.setdefault(run.run_id, asyncio.Lock())
        async with lock:
            existing = self._results.get(run.run_id)
            if existing is not None:
                return existing
            runtime_identity = canonical_sha256(
                {
                    "track": run.track,
                    "suite_hash": self._suite.content_hash,
                    "run_id": run.run_id,
                    "mode": "interactive_synthetic",
                }
            )
            runner = SyntheticSuiteRunner(
                runtime=SyntheticFixtureRuntime(
                    sealed_fixture_root=self._fixture_root,
                    workspaces_root=self._workspaces_root / run.run_id,
                    mongodb_uri=self._mongodb_uri,
                ),
                runtime_config_identity=runtime_identity,
                capability_catalog=self._capability_catalog,
                oracle=self._oracle,
            )
            result = await runner.run(
                self._suite,
                requested_case_ids=run.selected_case_ids,
            )
            if not isinstance(result, SyntheticSuiteBaselineResult):
                raise ValueError(result.message)
            built = build_synthetic_suite_artifact(
                suite=self._suite,
                result=result,
            )
            content = built.artifact.model_dump(
                mode="python",
                exclude={"artifact_hash", "run_id"},
            )
            content["run_id"] = run.run_id
            artifact = SuiteArtifact(
                **content,
                artifact_hash=canonical_sha256(content),
            )
            self._results[run.run_id] = artifact
            return artifact


def load_synthetic_oracle_catalog(
    *,
    suite: AuthoredSuiteSpec,
    fixture_root: Path,
    claim_catalog_path: Path,
):
    fixture_manifest = json.loads(
        (fixture_root / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    return load_claim_catalog(
        claim_catalog_path,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=tuple(
            item["asset_id"] for item in fixture_manifest["scenario_assets"]
        ),
        referenced_claim_ids=tuple(
            dict.fromkeys(
                claim_id
                for case in suite.cases
                for assertion in case.behavior_assertions
                if isinstance(assertion, FinalClaimsAssertionSpec)
                for claim_id in (
                    *assertion.required_claim_refs,
                    *assertion.forbidden_claim_refs,
                )
            )
        ),
    )
