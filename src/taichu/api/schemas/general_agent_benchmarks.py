"""通用写作智能体固定基准 API 契约。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    StableId,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.closure import (
    ModelComparisonRecord,
    ModelComparisonRequest,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ExperimentRecord,
    ExperimentSpec,
)
from taichu.application.evaluations.general_agent_benchmark.first_live import (
    FirstLiveIterationManifest,
)
from taichu.application.evaluations.general_agent_benchmark.issue_correlations import (
    IssueCorrelationStatus,
    IssueReconciliationReport,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseResultRow,
    EvidenceBundle,
    SuiteArtifact,
    SuiteRun,
)
from taichu.application.evaluations.general_agent_benchmark.observability import (
    BenchmarkObservabilitySnapshot,
)
from taichu.application.evaluations.general_agent_benchmark.services import (
    BenchmarkCatalogEntry,
    BenchmarkSuiteDetailEntry,
)

T = TypeVar("T")


class PaginatedResponse(BenchmarkModel, Generic[T]):
    items: tuple[T, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    index_revision: int = Field(ge=0)
    total_snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")


class SuiteSummaryResponse(BenchmarkCatalogEntry):
    pass


class SuiteDetailResponse(BenchmarkModel):
    suite: BenchmarkSuiteDetailEntry


class BenchmarkObservabilityResponse(BenchmarkObservabilitySnapshot):
    pass


class RunSubmissionRequest(BenchmarkModel):
    idempotency_key: str = Field(min_length=1, max_length=300)
    run_id: str = Field(pattern=r"^benchmark_run_\d{8}T\d{6}Z_[a-f0-9]{12}$")
    suite_id: StableId
    suite_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    track: TrackKind


class RunSubmissionResponse(BenchmarkModel):
    run: SuiteRun


class RunSummaryResponse(SuiteRun):
    pass


class RunDetailResponse(BenchmarkModel):
    run: SuiteRun


class LifecycleCommandRequest(BenchmarkModel):
    expected_revision: int = Field(ge=0)


class LifecycleCommandResponse(BenchmarkModel):
    run: SuiteRun


class CaseResultResponse(BenchmarkModel):
    case: CaseResultRow


class EvidenceBundleResponse(BenchmarkModel):
    evidence: EvidenceBundle


class SuiteArtifactResponse(BenchmarkModel):
    artifact: SuiteArtifact


class ExperimentSubmissionRequest(ExperimentSpec):
    pass


class ExperimentSubmissionResponse(BenchmarkModel):
    experiment: ExperimentRecord


class ExperimentDetailResponse(BenchmarkModel):
    experiment: ExperimentRecord


class FirstLiveIterationCreateRequest(BenchmarkModel):
    iteration_id: StableId
    code_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    suite_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    fixture_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    capability_catalog_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    synthetic_qualification_artifact_refs: tuple[str, ...] = Field(min_length=1)
    synthetic_suite_passed: bool
    core_gates_passed: bool
    memory_gates_passed: bool
    mechanism_gates_passed: bool
    prior_iteration_ids: tuple[StableId, ...] = ()


class FirstLiveIterationResponse(BenchmarkModel):
    iteration: FirstLiveIterationManifest


class IssueCorrelationStatusResponse(BenchmarkModel):
    status: IssueCorrelationStatus


class IssueCorrelationCommandRequest(BenchmarkModel):
    subject_id: str = Field(pattern=r"^[a-f0-9]{64}$")


class IssueCorrelationCommandResponse(BenchmarkModel):
    report: IssueReconciliationReport


class ModelComparisonSubmissionRequest(ModelComparisonRequest):
    pass


class ModelComparisonDetailResponse(BenchmarkModel):
    comparison: ModelComparisonRecord
