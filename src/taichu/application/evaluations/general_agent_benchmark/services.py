"""固定基准目录、幂等提交与快照分页查询服务。"""

from __future__ import annotations

import asyncio
from math import ceil

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    BenchmarkLifecycleService,
    SuiteRunRevisionConflict,
    SuiteRunStore,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    ResourceBudget,
    Sha256,
    StableId,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    SuiteRun,
)
from taichu.application.evaluations.general_agent_benchmark.selection import (
    SelectionError,
    SuiteSelectionValidator,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
    ExpectedTerminalSpec,
)


class BenchmarkCaseCatalogEntry(BenchmarkModel):
    ordinal: int = Field(ge=1)
    case_id: StableId
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1_000)
    tracks: tuple[TrackKind, ...] = Field(min_length=1)


class BenchmarkCatalogEntry(BenchmarkModel):
    suite_id: StableId
    name: str = Field(min_length=1, max_length=200)
    content_hash: Sha256
    case_count: int = Field(gt=0)
    case_order: tuple[StableId, ...] = ()
    track_case_counts: dict[TrackKind, int] = Field(default_factory=dict)
    cases: tuple[BenchmarkCaseCatalogEntry, ...] = ()

    @classmethod
    def from_suite(cls, suite: AuthoredSuiteSpec) -> BenchmarkCatalogEntry:
        return cls(
            suite_id=suite.suite_id,
            name=suite.name,
            content_hash=suite.content_hash,
            case_count=len(suite.cases),
            case_order=suite.case_order,
            track_case_counts={
                track.kind: sum(
                    track.kind in case.applicable_tracks
                    for case in suite.cases
                )
                for track in suite.tracks
            },
            cases=tuple(
                BenchmarkCaseCatalogEntry(
                    ordinal=ordinal,
                    case_id=case.case_id,
                    name=case.name,
                    summary=case.summary,
                    tracks=tuple(
                        track.kind
                        for track in suite.tracks
                        if track.kind in case.applicable_tracks
                    ),
                )
                for ordinal, case in enumerate(suite.cases, start=1)
            ),
        )


class BenchmarkCaseExpectationEntry(BenchmarkModel):
    ordinal: int = Field(ge=1)
    case_id: StableId
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1_000)
    user_request: str = Field(min_length=1, max_length=100_000)
    tracks: tuple[TrackKind, ...] = Field(min_length=1)
    objective: str = Field(min_length=1, max_length=2_000)
    target_final_artifact: str = Field(min_length=1, max_length=1_000)
    behavior_expectations: tuple[str, ...] = Field(min_length=1)
    expected_terminal: ExpectedTerminalSpec
    budget_limits: ResourceBudget
    capability_domain_id: StableId


class BenchmarkCapabilityDomainEntry(BenchmarkModel):
    domain_id: StableId
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=500)
    case_ids: tuple[StableId, ...] = Field(min_length=1)


_BENCHMARK_CAPABILITY_DOMAINS = (
    BenchmarkCapabilityDomainEntry(
        domain_id="routing_and_retrieval",
        name="简单路由与检索",
        purpose="验证小任务采用最小充分路径，并能从正文、结构、知识库和许可外部资料中取得正确依据。",
        case_ids=(
            "direct_answer_current_request",
            "single_manuscript_search",
            "structure_coverage_read",
            "single_knowledge_retrieval",
            "knowledge_catalog_identity_read",
            "external_research_grounded",
        ),
    ),
    BenchmarkCapabilityDomainEntry(
        domain_id="evidence_and_multi_agent",
        name="证据与多智能体协作",
        purpose="验证事实边界、并行分支、创作流水线和审查修订之间真实且正确的数据交接。",
        case_ids=(
            "single_canon_evidence",
            "summary_world_character",
            "architecture_scene_draft",
            "parallel_review_triad",
            "revision_from_reviews",
        ),
    ),
    BenchmarkCapabilityDomainEntry(
        domain_id="authorization_and_persistence",
        name="预览、授权与持久化资源",
        purpose="验证人工介入前后的因果与安全边界，确保批准、拒绝和高风险变更不会误写或漂移目标。",
        case_ids=(
            "manuscript_preview_only",
            "manuscript_patch_authorized_resume",
            "structure_create_update",
            "structure_delete_second_confirmation",
            "knowledge_create_update",
            "write_authorization_denied",
        ),
    ),
    BenchmarkCapabilityDomainEntry(
        domain_id="runtime_working_memory",
        name="运行工作记忆",
        purpose="验证有效、过期、被拒绝和被替代的运行工作记忆，只在正确分支与最终答案中产生应有影响。",
        case_ids=(
            "memory_active_projection",
            "memory_stale_dependency",
            "memory_rejected_parallel_isolation",
            "memory_superseded_repair",
        ),
    ),
    BenchmarkCapabilityDomainEntry(
        domain_id="checkpoint_and_recovery",
        name="检查点、中断与恢复",
        purpose="验证不同故障窗口中的结果复用、幂等执行、副作用对账和官方检查点可用性。",
        case_ids=(
            "recovery_after_plan_before_execution",
            "recovery_tool_result_before_consumption",
            "recovery_subagent_interrupted",
            "recovery_waiting_authorization",
            "recovery_after_write_before_effect_success",
            "recovery_verification_interruption",
            "recovery_multiple_interruptions",
            "recovery_checkpoint_unavailable",
        ),
    ),
    BenchmarkCapabilityDomainEntry(
        domain_id="five_layer_context_governance",
        name="五层上下文治理",
        purpose="验证上下文压力下的事实保持、裁剪与投影优先级、结果等价、隔离保护和安全拒绝。",
        case_ids=(
            "context_long_history_fact_retention",
            "context_long_working_memory_priority",
            "context_large_node_output_projection",
            "context_multi_source_overflow",
            "context_compression_result_equivalence",
            "context_invalid_memory_pressure_isolation",
            "context_long_current_request_preserved",
            "context_unsafe_compression_refusal",
        ),
    ),
)
_CAPABILITY_DOMAIN_BY_CASE_ID = {
    case_id: domain.domain_id
    for domain in _BENCHMARK_CAPABILITY_DOMAINS
    for case_id in domain.case_ids
}


class BenchmarkSuiteDetailEntry(BenchmarkModel):
    suite_id: StableId
    name: str = Field(min_length=1, max_length=200)
    content_hash: Sha256
    case_count: int = Field(gt=0)
    case_order: tuple[StableId, ...]
    track_case_counts: dict[TrackKind, int]
    capability_domains: tuple[BenchmarkCapabilityDomainEntry, ...]
    cases: tuple[BenchmarkCaseExpectationEntry, ...]

    @classmethod
    def from_suite(
        cls,
        suite: AuthoredSuiteSpec,
    ) -> BenchmarkSuiteDetailEntry:
        summary = BenchmarkCatalogEntry.from_suite(suite)
        declared_case_ids = tuple(
            case_id
            for domain in _BENCHMARK_CAPABILITY_DOMAINS
            for case_id in domain.case_ids
        )
        if (
            len(declared_case_ids) != len(set(declared_case_ids))
            or frozenset(declared_case_ids) != frozenset(suite.case_order)
        ):
            raise ValueError("能力领域必须无重复地覆盖全部固定合同。")
        return cls(
            suite_id=summary.suite_id,
            name=summary.name,
            content_hash=summary.content_hash,
            case_count=summary.case_count,
            case_order=summary.case_order,
            track_case_counts=summary.track_case_counts,
            capability_domains=_BENCHMARK_CAPABILITY_DOMAINS,
            cases=tuple(
                BenchmarkCaseExpectationEntry(
                    ordinal=ordinal,
                    case_id=case.case_id,
                    name=case.name,
                    summary=case.summary,
                    user_request=case.user_request,
                    tracks=tuple(
                        track.kind
                        for track in suite.tracks
                        if track.kind in case.applicable_tracks
                    ),
                    objective=case.scenario.objective,
                    target_final_artifact=case.scenario.target_final_artifact,
                    behavior_expectations=tuple(
                        assertion.description
                        for assertion in case.behavior_assertions
                    ),
                    expected_terminal=case.expected_terminal,
                    budget_limits=case.budgets,
                    capability_domain_id=_CAPABILITY_DOMAIN_BY_CASE_ID[
                        case.case_id
                    ],
                )
                for ordinal, case in enumerate(suite.cases, start=1)
            ),
        )


class BenchmarkCatalogService:
    def __init__(
        self,
        entries: tuple[BenchmarkCatalogEntry, ...],
        *,
        authored_suites: tuple[AuthoredSuiteSpec, ...] = (),
    ) -> None:
        by_id = {entry.suite_id: entry for entry in entries}
        if len(by_id) != len(entries):
            raise ValueError("基准目录 suite_id 不得重复。")
        suites_by_id = {suite.suite_id: suite for suite in authored_suites}
        if len(suites_by_id) != len(authored_suites):
            raise ValueError("权威 Suite 的 suite_id 不得重复。")
        if set(suites_by_id) - set(by_id):
            raise ValueError("权威 Suite 必须存在对应的目录条目。")
        self._entries = by_id
        self._authored_suites = suites_by_id

    def list(self) -> tuple[BenchmarkCatalogEntry, ...]:
        return tuple(
            self._entries[key] for key in sorted(self._entries)
        )

    def get(self, suite_id: str) -> BenchmarkCatalogEntry:
        try:
            return self._entries[suite_id]
        except KeyError as error:
            raise KeyError(f"固定基准不存在：{suite_id}") from error

    def get_detail(self, suite_id: str) -> BenchmarkSuiteDetailEntry:
        self.get(suite_id)
        try:
            suite = self._authored_suites[suite_id]
        except KeyError as error:
            raise KeyError(f"固定基准缺少权威合同详情：{suite_id}") from error
        return BenchmarkSuiteDetailEntry.from_suite(suite)

    def validate_selection(
        self,
        *,
        suite_id: str,
        suite_content_hash: str,
        track: TrackKind,
        selected_case_ids: tuple[str, ...],
    ) -> SelectionError | None:
        try:
            entry = self.get(suite_id)
        except KeyError:
            return SelectionError(
                code="invalid_case_ids",
                message=f"固定基准不存在：{suite_id}。",
                track=track.value,
                case_ids=selected_case_ids,
            )
        if entry.content_hash != suite_content_hash:
            return SelectionError(
                code="invalid_case_ids",
                message="Suite 内容身份与当前权威合同不一致。",
                track=track.value,
                case_ids=selected_case_ids,
                expected_case_ids=entry.case_order,
            )
        suite = self._authored_suites.get(suite_id)
        if suite is None:
            return None
        selection = SuiteSelectionValidator.validate(
            suite,
            track,
            selected_case_ids,
        )
        return selection if isinstance(selection, SelectionError) else None


class SubmissionRequest(BenchmarkModel):
    idempotency_key: str = Field(min_length=1, max_length=300)
    run_id: str = Field(
        pattern=r"^benchmark_run_\d{8}T\d{6}Z_[a-f0-9]{12}$"
    )
    suite_id: StableId
    suite_content_hash: Sha256
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    track: TrackKind


class BenchmarkSubmissionConflict(RuntimeError):
    """幂等键或运行身份已绑定不同提交。"""


class BenchmarkSelectionRejected(ValueError):
    """运行创建前的 Suite/轨道/案例选择被拒绝。"""

    def __init__(self, selection_error: SelectionError) -> None:
        super().__init__(selection_error.message)
        self.selection_error = selection_error


class BenchmarkSubmissionService:
    def __init__(
        self,
        *,
        lifecycle: BenchmarkLifecycleService,
        catalog: BenchmarkCatalogService | None = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._catalog = catalog
        self._claims: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    async def submit(self, request: SubmissionRequest) -> SuiteRun:
        if self._catalog is not None:
            selection_error = self._catalog.validate_selection(
                suite_id=request.suite_id,
                suite_content_hash=request.suite_content_hash,
                track=request.track,
                selected_case_ids=request.selected_case_ids,
            )
            if selection_error is not None:
                raise BenchmarkSelectionRejected(selection_error)
        submission_hash = canonical_sha256(
            request.model_dump(mode="json", exclude={"idempotency_key"})
        )
        async with self._lock:
            claim = self._claims.get(request.idempotency_key)
            if claim is not None:
                claimed_hash, run_id = claim
                if claimed_hash != submission_hash:
                    raise BenchmarkSubmissionConflict(
                        "幂等键已经绑定不同的评测提交。"
                    )
                return await self._lifecycle.get(run_id)
            try:
                created = await self._lifecycle.create(
                    run_id=request.run_id,
                    suite_content_hash=request.suite_content_hash,
                    selected_case_ids=request.selected_case_ids,
                    track=request.track,
                )
            except SuiteRunRevisionConflict as error:
                raise BenchmarkSubmissionConflict(
                    "评测运行标识已经绑定其他提交。"
                ) from error
            self._claims[request.idempotency_key] = (
                submission_hash,
                created.run_id,
            )
            return created


class SuiteRunPage(BenchmarkModel):
    items: tuple[SuiteRun, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    index_revision: int = Field(ge=0)
    total_snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")


class BenchmarkQueryService:
    def __init__(self, store: SuiteRunStore) -> None:
        self._store = store

    async def get_run(self, run_id: str) -> SuiteRun:
        return await self._store.get(run_id)

    async def list_runs(
        self,
        *,
        page: int,
        page_size: int,
        total_snapshot: str | None = None,
    ) -> SuiteRunPage:
        if page < 1:
            raise ValueError("page 必须大于等于 1。")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size 必须在 1 到 100 之间。")
        runs, index_revision, snapshot = await self._store.list_snapshot(
            total_snapshot
        )
        total = len(runs)
        offset = (page - 1) * page_size
        return SuiteRunPage(
            items=runs[offset : offset + page_size],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
            index_revision=index_revision,
            total_snapshot=snapshot,
        )
