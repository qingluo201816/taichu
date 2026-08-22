"""需求 16.1-16.3：冻结评测查询状态的只读恢复契约。"""

from __future__ import annotations

from enum import StrEnum

from taichu.application.evaluations.general_agent_benchmark.closure import (
    ModelComparisonRecord,
)
from taichu.application.evaluations.general_agent_benchmark.first_live import (
    FirstLiveArtifact,
    FirstLiveIterationManifest,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ArtifactIdentity,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    SuiteArtifact,
    SuiteRun,
)


class QueryHydrationStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class HydratedSuiteLineage(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"


class ArtifactHydrationStatus(StrEnum):
    HYDRATED = "hydrated"
    HYDRATED_READ_ONLY_IDENTITY_INCOMPLETE = (
        "hydrated_read_only_identity_incomplete"
    )
    UNAVAILABLE_ARTIFACT_IDENTITY_MISMATCH = (
        "unavailable_artifact_identity_mismatch"
    )
    UNAVAILABLE_IDENTITY_SUBSTITUTION_FORBIDDEN = (
        "unavailable_identity_substitution_forbidden"
    )


class HydratedSyntheticArtifact(BenchmarkModel):
    lineage: HydratedSuiteLineage
    status: ArtifactHydrationStatus
    source_ref: str
    identity: ArtifactIdentity
    missing_identity_fields: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    suite_run: SuiteRun | None = None
    suite_artifact: SuiteArtifact | None = None

    @classmethod
    def historical_incomplete(
        cls,
        *,
        source_ref: str,
        identity: ArtifactIdentity,
        missing_identity_fields: tuple[str, ...],
        suite_run: SuiteRun,
        suite_artifact: SuiteArtifact,
    ) -> HydratedSyntheticArtifact:
        return cls(
            lineage=HydratedSuiteLineage.HISTORICAL,
            status=(
                ArtifactHydrationStatus.HYDRATED_READ_ONLY_IDENTITY_INCOMPLETE
            ),
            source_ref=source_ref,
            identity=identity,
            missing_identity_fields=missing_identity_fields,
            suite_run=suite_run,
            suite_artifact=suite_artifact,
        )


class BenchmarkQueryHydration(BenchmarkModel):
    status: QueryHydrationStatus
    source_refs: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    suite_run: SuiteRun | None = None
    suite_artifact: SuiteArtifact | None = None
    first_live_iteration: FirstLiveIterationManifest | None = None
    first_live_artifact: FirstLiveArtifact | None = None
    blocked_comparison: ModelComparisonRecord | None = None
    synthetic_entries: tuple[HydratedSyntheticArtifact, ...] = ()

    @classmethod
    def not_configured(cls) -> BenchmarkQueryHydration:
        return cls(status=QueryHydrationStatus.NOT_CONFIGURED)
