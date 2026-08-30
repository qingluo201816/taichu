"""真实模型评测轨道的观察与审计适配。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pymongo import AsyncMongoClient
from pydantic import Field, model_validator

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.llm import LLMModelProfile
from taichu.infrastructure.llm.contracts import (
    LLMGatewayContract,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
)
from taichu.application.contracts.llm_replay import LLMCallReplayRepository
from taichu.application.contracts.llm_usage import LLMUsageRepository
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ObservedInteraction,
    StrictScriptedDriver,
)
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    CapabilityCatalogSnapshot,
    CapabilityKind,
    CaseConclusion,
    Sha256,
    StableId,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    ProviderExecutionState,
)
from taichu.application.evaluations.general_agent_benchmark.selection import (
    CaseSelection,
    SelectionError,
    SuiteSelectionValidator,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    AuthoredSuiteSpec,
    RequiredInvocationSpec,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    RuntimeInteractionRecord,
    SyntheticCapabilityInvocation,
    SyntheticCaseBaselineResult,
    SyntheticCaseObservation,
    SyntheticRuntimePort,
    SyntheticSuiteRunner,
)
from taichu.application.general_agent.models import GeneralAgentHumanRequest
from taichu.application.models.llm_replay import LLMCallReplayRecord
from taichu.application.models.llm_usage import (
    LLMCallRecord,
    LLMTokenTrendPoint,
    LLMUsagePage,
    LLMUsageQuery,
    LLMUsageSummary,
)
from taichu.application.services.model_role_router import ModelRoleRouter
from taichu.config import Settings
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_environment import (
    SyntheticFixtureRuntime,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_runtime import (
    StrictSyntheticInteractionObserver,
    SyntheticInjectedProcessTermination,
)
from taichu.infrastructure.llm.catalog import LLMModelCatalog
from taichu.infrastructure.llm.rightcode import (
    LLMGatewayError,
    RightCodeLLMGateway,
)
from taichu.infrastructure.llm_replays.json_repository import (
    JsonLLMCallReplayRepository,
)
from taichu.infrastructure.llm_usage.jsonl_repository import (
    JsonlLLMUsageRepository,
)


_MODEL_ROLES = (
    "canon_evidence",
    "character",
    "consistency_reviewer",
    "drafting",
    "external_research",
    "narrative_reviewer",
    "narrative_summary",
    "revision",
    "scene_planning",
    "story_architecture",
    "style_reviewer",
    "worldbuilding",
)


@dataclass(frozen=True, slots=True)
class LiveGatewayFailure:
    """保留真实 provider 异常对象之外的稳定审计摘要。"""

    task_name: str
    requested_model_id: str
    error_type: str
    error_code: str | None
    status_code: int | None
    error_message: str


@dataclass(frozen=True, slots=True)
class LiveCaseProviderAudit:
    """单案例真实模型调用的完整可复核审计集合。"""

    case_id: str
    usage_records: tuple[LLMCallRecord, ...]
    replay_records: tuple[LLMCallReplayRecord, ...]
    gateway_failures: tuple[LiveGatewayFailure, ...]
    response_call_ids: tuple[str, ...]


class LiveProviderInterruption(BenchmarkModel):
    """provider 未形成可交给 Typed Oracle 的 Runtime observation。"""

    case_id: StableId
    state: ProviderExecutionState
    error_type: str = Field(min_length=1, max_length=256)
    error_code: str | None = Field(default=None, min_length=1, max_length=128)
    status_code: int | None = Field(default=None, ge=100, le=599)
    message: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def _state_is_provider_interruption(self) -> LiveProviderInterruption:
        if self.state not in {
            ProviderExecutionState.BLOCKED,
            ProviderExecutionState.ERROR,
        }:
            raise ValueError("provider 中断只能记录 blocked 或 error。")
        return self


class LiveSuiteBaselineResult(BenchmarkModel):
    """Live 独立轨道结果；不持有也不改写 Synthetic 准入对象。"""

    suite_id: StableId
    suite_content_hash: Sha256
    runtime_config_identity: Sha256
    track: TrackKind = TrackKind.LIVE_PROVIDER
    applicable_case_ids: tuple[StableId, ...] = Field(min_length=1)
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    cases: tuple[SyntheticCaseBaselineResult, ...]
    provider_state: ProviderExecutionState
    provider_interruptions: tuple[LiveProviderInterruption, ...] = ()
    case_count: int = Field(ge=1)
    executed_case_count: int = Field(ge=0)
    passed_case_count: int = Field(ge=0)
    failed_case_count: int = Field(ge=0)
    pending_case_ids: tuple[StableId, ...] = ()
    complete: bool
    result_hash: Sha256
    stable_result_hash: Sha256

    @model_validator(mode="after")
    def _counts_and_provider_state_are_consistent(self) -> LiveSuiteBaselineResult:
        if self.track is not TrackKind.LIVE_PROVIDER:
            raise ValueError("Live 结果轨道必须是 live_provider。")
        if self.case_count != len(self.selected_case_ids):
            raise ValueError("Live case_count 必须等于已校验选择数量。")
        if self.executed_case_count != len(self.cases):
            raise ValueError("Live executed_case_count 必须来自实际案例结果。")
        if self.passed_case_count != sum(
            item.conclusion is CaseConclusion.PASSED for item in self.cases
        ):
            raise ValueError("Live passed_case_count 必须来自实际案例结果。")
        if self.failed_case_count != self.executed_case_count - self.passed_case_count:
            raise ValueError("Live failed_case_count 必须来自实际案例结果。")
        executed_ids = tuple(item.case_id for item in self.cases)
        if executed_ids != self.selected_case_ids[: self.executed_case_count]:
            raise ValueError("Live 案例结果必须保持 selector 的权威顺序。")
        expected_pending = self.selected_case_ids[self.executed_case_count :]
        if self.pending_case_ids != expected_pending:
            raise ValueError("Live pending_case_ids 必须由未执行选择派生。")
        if self.provider_state is ProviderExecutionState.COMPLETED:
            if self.provider_interruptions or self.pending_case_ids:
                raise ValueError("provider completed 不得携带中断或待执行案例。")
        elif self.provider_state in {
            ProviderExecutionState.BLOCKED,
            ProviderExecutionState.ERROR,
        }:
            if len(self.provider_interruptions) != 1 or not self.pending_case_ids:
                raise ValueError("provider blocked/error 必须保留一次中断及待执行案例。")
        else:
            raise ValueError("Live 终态只接受 completed、blocked 或 error。")
        expected_complete = (
            self.provider_state is ProviderExecutionState.COMPLETED
            and self.selected_case_ids == self.applicable_case_ids
            and self.executed_case_count == self.case_count
            and self.passed_case_count == self.case_count
        )
        if self.complete is not expected_complete:
            raise ValueError("Live complete 必须由完整 L21、provider 与六 Gate 派生。")
        return self


class LiveObservedLLMGateway:
    """在真实网关返回后记录模型交互，不替换模型输出。"""

    def __init__(
        self,
        delegate: LLMGatewayContract,
        *,
        driver: StrictScriptedDriver | None,
        observer: StrictSyntheticInteractionObserver,
        crash_once_task_name: str | None = None,
    ) -> None:
        self._delegate = delegate
        self._driver = driver
        self._observer = observer
        self._crash_once_task_name = crash_once_task_name
        self._crashed = False
        self.requests: list[LLMRequest] = []
        self._responses: list[LLMResponse] = []
        self._failures: list[LiveGatewayFailure] = []

    @property
    def responses(self) -> tuple[LLMResponse, ...]:
        return tuple(self._responses)

    @property
    def failures(self) -> tuple[LiveGatewayFailure, ...]:
        return tuple(self._failures)

    def set_response_bindings(self, values: dict[str, object]) -> None:
        """兼容共享夹具执行器；真实模型响应不接受合成绑定。"""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if request.task_name == self._crash_once_task_name and not self._crashed:
            self.requests.append(request)
            self._crashed = True
            raise SyntheticInjectedProcessTermination(
                f"在 {request.task_name} 注入一次进程终止。"
            )
        self.requests.append(request)
        try:
            response = await self._delegate.complete(request)
        except Exception as error:
            self._failures.append(
                LiveGatewayFailure(
                    task_name=request.task_name,
                    requested_model_id=request.model_id,
                    error_type=type(error).__name__,
                    error_code=getattr(error, "code", None),
                    status_code=getattr(error, "status_code", None),
                    error_message=str(error),
                )
            )
            raise
        payload = {"phase": _model_phase(request.task_name)}
        step = (
            self._driver.select_step(
                kind=InteractionKind.MODEL,
                payload=payload,
            )
            if self._driver is not None
            else None
        )
        interaction = ObservedInteraction(
            kind=InteractionKind.MODEL,
            name=(
                step.name
                if step is not None
                else f"orchestrator_{_model_phase(request.task_name)}"
            ),
            payload=payload,
            outcome="completed",
        )
        if self._driver is not None:
            self._driver.observe(interaction)
        self._observer.record_observed(interaction)
        self._responses.append(response)
        return response

    async def stream(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[LLMStreamEvent]:
        response = await self.complete(request)
        yield LLMStreamEvent(
            event_type="completed",
            response=response,
            usage=response.usage,
            call_id=response.call_id,
        )

    def list_models(self) -> list[LLMModelProfile]:
        return self._delegate.list_models()


class RecordingUsageRepository:
    """转发正式 usage 写入，同时保留本案例精确记录。"""

    def __init__(self, delegate: LLMUsageRepository) -> None:
        self._delegate = delegate
        self._records: list[LLMCallRecord] = []

    @property
    def records(self) -> tuple[LLMCallRecord, ...]:
        return tuple(self._records)

    async def append(self, record: LLMCallRecord) -> None:
        await self._delegate.append(record)
        self._records.append(record)

    async def get(self, call_id: str) -> LLMCallRecord | None:
        return await self._delegate.get(call_id)

    async def list_calls(self, query: LLMUsageQuery) -> LLMUsagePage:
        return await self._delegate.list_calls(query)

    async def summarize(self, query: LLMUsageQuery) -> LLMUsageSummary:
        return await self._delegate.summarize(query)

    async def token_trend(
        self,
        query: LLMUsageQuery,
        bucket: str,
    ) -> list[LLMTokenTrendPoint]:
        return await self._delegate.token_trend(query, bucket)  # type: ignore[arg-type]


class RecordingReplayRepository:
    """转发正式 replay 写入，同时保留本案例精确记录。"""

    def __init__(self, delegate: LLMCallReplayRepository) -> None:
        self._delegate = delegate
        self._records: list[LLMCallReplayRecord] = []

    @property
    def records(self) -> tuple[LLMCallReplayRecord, ...]:
        return tuple(self._records)

    async def save(self, record: LLMCallReplayRecord) -> None:
        await self._delegate.save(record)
        self._records.append(record)

    async def get(self, call_id: str) -> LLMCallReplayRecord | None:
        return await self._delegate.get(call_id)

    async def list_for_run(self, run_id: str) -> list[LLMCallReplayRecord]:
        return await self._delegate.list_for_run(run_id)

    async def delete_run(self, run_id: str) -> None:
        await self._delegate.delete_run(run_id)


@dataclass(slots=True)
class _LiveCaseCollector:
    usage: RecordingUsageRepository
    replay: RecordingReplayRepository
    gateway: LiveObservedLLMGateway


class LiveInteractionObserver(StrictSyntheticInteractionObserver):
    """只记录真实交互，不消费 deterministic synthetic 步骤。"""

    def __init__(self) -> None:
        self.interaction_records: list[RuntimeInteractionRecord] = []
        self.capability_records: list[RuntimeInteractionRecord] = []

    def record_observed(self, interaction: ObservedInteraction) -> None:
        self.interaction_records.append(
            RuntimeInteractionRecord(interaction=interaction)
        )

    def record_capability(
        self,
        *,
        kind: InteractionKind,
        name: str,
        call_id: str,
        handler_identity: str,
        outcome: str,
        invocation: object | None = None,
        request_payload: dict[str, object] | None = None,
        response_payload: dict[str, object] | None = None,
        source_refs: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        phase = getattr(invocation, "phase", None)
        node_id = (
            phase.removeprefix("dag:")
            if isinstance(phase, str) and phase.startswith("dag:")
            else None
        )
        record = RuntimeInteractionRecord(
            interaction=ObservedInteraction(
                kind=kind,
                name=name,
                payload={"capability_name": name},
                outcome=outcome,
            ),
            call_id=call_id,
            handler_identity=handler_identity,
            parent_call_id=(
                str(parent_call_id)
                if (
                    parent_call_id := getattr(
                        invocation,
                        "parent_call_id",
                        None,
                    )
                )
                is not None
                else None
            ),
            run_id=(
                str(run_id)
                if (run_id := getattr(invocation, "run_id", None)) is not None
                else None
            ),
            node_id=node_id,
            request_payload=request_payload,
            response_payload=response_payload,
            source_refs=source_refs,
            artifact_refs=artifact_refs,
            started_at=started_at,
            finished_at=finished_at,
        )
        self.interaction_records.append(record)
        self.capability_records.append(record)

    def record_human_decision(
        self,
        *,
        request: GeneralAgentHumanRequest,
        source_run_id: str,
        approved: bool,
        second_confirmation: bool,
    ) -> None:
        interaction = ObservedInteraction(
            kind=InteractionKind.HUMAN,
            name=request.kind,
            payload={"approved": approved},
            outcome="completed",
        )
        self.interaction_records.append(
            RuntimeInteractionRecord(
                interaction=interaction,
                run_id=source_run_id,
                node_id=request.node_id,
                human_request_id=request.request_id,
                human_request_kind=request.kind,
                human_tool_name=request.tool_name,
                human_input_sha256=request.input_sha256,
                human_resource_scopes=tuple(request.resource_scopes),
                human_second_confirmation_required=(
                    request.second_confirmation_required
                ),
                human_approved=approved,
                human_second_confirmation=second_confirmation,
                human_request_created_at=request.created_at,
            )
        )


class LiveFixtureRuntime(SyntheticFixtureRuntime):
    """复用同一密封夹具，仅把 synthetic 模型替换为真实 RightCode。"""

    def __init__(
        self,
        *,
        sealed_fixture_root: Path,
        workspaces_root: Path,
        settings: Settings,
        model_id: str = "deepseek-v4-pro",
        mongodb_uri: str = "mongodb://127.0.0.1:27017",
    ) -> None:
        if settings.deepseek_fallback_enabled:
            raise ValueError("live 首轮必须禁用 fallback。")
        if settings.rightcode_default_model_id != model_id:
            raise ValueError("live 轨道配置模型与请求模型不一致。")
        super().__init__(
            sealed_fixture_root=sealed_fixture_root,
            workspaces_root=workspaces_root,
            mongodb_uri=mongodb_uri,
        )
        self._live_settings = settings
        self._model_id = model_id
        self._collectors: dict[str, _LiveCaseCollector] = {}
        self._audits: dict[str, LiveCaseProviderAudit] = {}

    async def execute(self, case: AuthoredCaseSpec) -> SyntheticCaseObservation:
        try:
            observation = await super().execute(case)
            collector = self._collectors.get(case.case_id)
            if collector is None or observation.runtime_facts is None:
                return observation
            usage = observation.runtime_facts.usage.model_copy(
                update={
                    "model_calls": len(collector.gateway.requests),
                    "total_tokens": sum(
                        record.total_tokens or 0 for record in collector.usage.records
                    ),
                }
            )
            return observation.model_copy(
                update={
                    "runtime_facts": observation.runtime_facts.model_copy(
                        update={"usage": usage}
                    )
                }
            )
        finally:
            collector = self._collectors.get(case.case_id)
            self._audits[case.case_id] = LiveCaseProviderAudit(
                case_id=case.case_id,
                usage_records=(
                    collector.usage.records if collector is not None else ()
                ),
                replay_records=(
                    collector.replay.records if collector is not None else ()
                ),
                gateway_failures=(
                    collector.gateway.failures if collector is not None else ()
                ),
                response_call_ids=(
                    tuple(
                        response.call_id
                        for response in collector.gateway.responses
                        if response.call_id is not None
                    )
                    if collector is not None
                    else ()
                ),
            )

    def case_audit(self, case_id: str) -> LiveCaseProviderAudit:
        return self._audits[case_id]

    async def _build_case_environment(
        self,
        case: AuthoredCaseSpec,
        *,
        workspace: Path,
        database_name: str,
        client: AsyncMongoClient[Any],
    ) -> dict[str, Any]:
        environment = await super()._build_case_environment(
            case,
            workspace=workspace,
            database_name=database_name,
            client=client,
        )
        driver: StrictScriptedDriver = environment["driver"]
        observer: StrictSyntheticInteractionObserver = environment["observer"]
        usage = RecordingUsageRepository(JsonlLLMUsageRepository(workspace))
        replay = RecordingReplayRepository(JsonLLMCallReplayRepository(workspace))
        settings = self._live_settings.model_copy(
            update={
                "project_assets_dir": workspace,
                "deepseek_fallback_enabled": False,
                "rightcode_default_model_id": self._model_id,
            }
        )
        raw_gateway = RightCodeLLMGateway(
            settings,
            LLMModelCatalog(settings),
            usage,
            replay_repository=replay,
        )
        gateway = LiveObservedLLMGateway(
            raw_gateway,
            driver=driver,
            observer=observer,
            crash_once_task_name=(
                "general_writing_orchestrator.verify"
                if case.case_id == "recovery_verification_interruption"
                else None
            ),
        )
        model_router = ModelRoleRouter(
            self._model_id,
            {name: self._model_id for name in _MODEL_ROLES},
        )
        current_context = environment["dependencies"].capability_context
        context = CapabilityContext(
            capabilities={
                **current_context.capabilities,
                "llm": gateway,
                "model_role_router": model_router,
            }
        )
        dependencies = replace(
            environment["dependencies"],
            capability_context=context,
            llm=gateway,
            model_router=model_router,
            llm_replay_repository=replay,
            interaction_observer=observer,
        )
        isolated = self._factory.create(
            dependencies,
            allowed_capabilities=environment["allowed_capabilities"],
        )
        environment.update(
            {
                "runtime": isolated.runtime,
                "gateway": gateway,
                "observer": observer,
                "dependencies": dependencies,
            }
        )
        self._collectors[case.case_id] = _LiveCaseCollector(
            usage=usage,
            replay=replay,
            gateway=gateway,
        )
        return environment


class LiveSuiteRunner:
    """Live 只替换 gateway，并复用 selector 与统一 Typed 判定。"""

    def __init__(
        self,
        *,
        runtime: SyntheticRuntimePort,
        runtime_config_identity: str,
        capability_catalog: CapabilityCatalogSnapshot,
        oracle: TypedOracle,
    ) -> None:
        self._runtime = runtime
        self._runtime_config_identity = runtime_config_identity
        self._typed_evaluator = SyntheticSuiteRunner(
            runtime=runtime,
            runtime_config_identity=runtime_config_identity,
            capability_catalog=capability_catalog,
            oracle=oracle,
            track=TrackKind.LIVE_PROVIDER,
        )
        self._capability_handlers = {
            (item.kind, item.capability_id): item.handler_identity
            for item in capability_catalog.tools + capability_catalog.subagents
        }
        self._registration_dependencies = capability_catalog.registration_dependencies

    async def run(
        self,
        suite: AuthoredSuiteSpec,
        *,
        requested_case_ids: Iterable[str] | None = None,
        progress: Any | None = None,
    ) -> LiveSuiteBaselineResult | SelectionError:
        authoritative_suite = _revalidate_live_suite(suite)
        if isinstance(authoritative_suite, SelectionError):
            return authoritative_suite
        selection = SuiteSelectionValidator.validate(
            authoritative_suite,
            TrackKind.LIVE_PROVIDER,
            requested_case_ids,
        )
        if isinstance(selection, SelectionError):
            return selection

        results: list[SyntheticCaseBaselineResult] = []
        interruptions: list[LiveProviderInterruption] = []
        provider_state = ProviderExecutionState.COMPLETED
        total = selection.case_count
        for position, case in enumerate(selection.cases, start=1):
            if progress is not None:
                progress(position, total, case.case_id, "started")
            try:
                result = await self._run_case(authoritative_suite, case)
            except LLMGatewayError as error:
                interruption = _provider_interruption(case.case_id, error)
                interruptions.append(interruption)
                provider_state = interruption.state
                if progress is not None:
                    progress(position, total, case.case_id, provider_state.value)
                break
            results.append(result)
            if progress is not None:
                progress(
                    position,
                    total,
                    case.case_id,
                    result.conclusion.value,
                )
        return _live_suite_result(
            selection=selection,
            runtime_config_identity=self._runtime_config_identity,
            results=tuple(results),
            provider_state=provider_state,
            interruptions=tuple(interruptions),
        )

    async def _run_case(
        self,
        suite: AuthoredSuiteSpec,
        case: AuthoredCaseSpec,
    ) -> SyntheticCaseBaselineResult:
        try:
            observation = await self._runtime.execute(case)
        except LLMGatewayError:
            raise
        except Exception as error:
            return SyntheticCaseBaselineResult(
                case_id=case.case_id,
                conclusion=CaseConclusion.INVALID,
                invocations=(),
                gates=(),
                normalization_artifact=None,
                problems=(f"runtime_error:{type(error).__name__}:{error}",),
            )
        invocations: list[SyntheticCapabilityInvocation] = []
        for record in observation.interactions:
            if record.interaction.kind not in {
                InteractionKind.TOOL,
                InteractionKind.SUBAGENT,
            }:
                continue
            if record.call_id is None or record.handler_identity is None:
                return SyntheticCaseBaselineResult(
                    case_id=case.case_id,
                    conclusion=CaseConclusion.INVALID,
                    invocations=tuple(invocations),
                    gates=(),
                    normalization_artifact=None,
                    problems=("capability_identity_missing",),
                )
            invocation = SyntheticCapabilityInvocation(
                kind=CapabilityKind(record.interaction.kind.value),
                capability_name=record.interaction.name,
                call_id=record.call_id,
                handler_identity=record.handler_identity,
                outcome=record.interaction.outcome,
            )
            expected_handler = self._capability_handlers.get(
                (invocation.kind, invocation.capability_name)
            )
            if expected_handler != invocation.handler_identity:
                return SyntheticCaseBaselineResult(
                    case_id=case.case_id,
                    conclusion=CaseConclusion.INVALID,
                    invocations=tuple(invocations),
                    gates=(),
                    normalization_artifact=None,
                    problems=("capability_handler_identity_mismatch",),
                )
            invocations.append(invocation)
        scripted_capabilities = frozenset(
            (
                CapabilityKind(step.kind.value),
                step.name,
            )
            for step in case.scripted_steps
            if step.kind in {InteractionKind.TOOL, InteractionKind.SUBAGENT}
        )
        selected_subagents = {
            item.name
            for item in case.required_invocations
            if item.type is CapabilityKind.SUBAGENT
        } | {
            step.name
            for step in case.scripted_steps
            if step.kind is InteractionKind.SUBAGENT
        }
        dependency_capabilities = frozenset(
            (CapabilityKind.TOOL, dependency.tool_id)
            for dependency in self._registration_dependencies
            if dependency.subagent_id in selected_subagents
        )
        invocation_problems = (
            *_live_invocation_problems(
                case.required_invocations,
                tuple(invocations),
                scripted_capabilities=(scripted_capabilities | dependency_capabilities),
            ),
            *_live_human_problems(case, observation.interactions),
        )
        typed = self._typed_evaluator.evaluate_runtime_observation(
            suite=suite,
            case=case,
            runtime_observation=observation,
            invocation_problems=invocation_problems,
        )
        if isinstance(typed, SyntheticCaseBaselineResult):
            return typed
        decision, assertions, case_observation = typed
        return SyntheticCaseBaselineResult(
            case_id=case.case_id,
            conclusion=decision.conclusion,
            invocations=tuple(invocations),
            gates=decision.gates,
            assertions=assertions,
            case_observation=case_observation,
            observation_sha256=case_observation.observation_sha256,
            evidence_ids=tuple(
                record.ref.evidence_id
                for record in case_observation.evidence_records
            ),
            normalization_artifact=None,
            problems=invocation_problems,
        )


def _revalidate_live_suite(
    suite: AuthoredSuiteSpec,
) -> AuthoredSuiteSpec | SelectionError:
    try:
        return AuthoredSuiteSpec.model_validate(
            suite.model_dump(mode="python", by_alias=True)
        )
    except ValueError:
        return SelectionError(
            code="invalid_case_ids",
            message="Live 执行只接受通过 Suite@2 完整合同校验的活动套件。",
            track=TrackKind.LIVE_PROVIDER.value,
            case_ids=tuple(case.case_id for case in suite.cases),
        )


def _provider_interruption(
    case_id: str,
    error: LLMGatewayError,
) -> LiveProviderInterruption:
    blocked_codes = {
        "LLM_MODEL_DISABLED",
        "LLM_MODEL_FORBIDDEN",
        "LLM_MODEL_UNAVAILABLE",
        "LLM_MODEL_UNKNOWN",
        "LLM_RATE_LIMITED",
        "LLM_TOKEN_MISSING",
    }
    state = (
        ProviderExecutionState.BLOCKED
        if error.code in blocked_codes
        else ProviderExecutionState.ERROR
    )
    return LiveProviderInterruption(
        case_id=case_id,
        state=state,
        error_type=type(error).__name__,
        error_code=error.code,
        status_code=error.status_code,
        message=str(error),
    )


def _live_suite_result(
    *,
    selection: CaseSelection,
    runtime_config_identity: str,
    results: tuple[SyntheticCaseBaselineResult, ...],
    provider_state: ProviderExecutionState,
    interruptions: tuple[LiveProviderInterruption, ...],
) -> LiveSuiteBaselineResult:
    passed = sum(item.conclusion is CaseConclusion.PASSED for item in results)
    pending_case_ids = selection.selected_case_ids[len(results) :]
    complete = (
        provider_state is ProviderExecutionState.COMPLETED
        and selection.is_full_selection
        and not pending_case_ids
        and passed == selection.case_count
    )
    payload = {
        "suite_id": selection.suite_id,
        "suite_content_hash": selection.suite_content_hash,
        "runtime_config_identity": runtime_config_identity,
        "track": TrackKind.LIVE_PROVIDER,
        "applicable_case_ids": selection.applicable_case_ids,
        "selected_case_ids": selection.selected_case_ids,
        "cases": tuple(item.model_dump(mode="json") for item in results),
        "provider_state": provider_state,
        "provider_interruptions": tuple(
            item.model_dump(mode="json") for item in interruptions
        ),
        "case_count": selection.case_count,
        "executed_case_count": len(results),
        "passed_case_count": passed,
        "failed_case_count": len(results) - passed,
        "pending_case_ids": pending_case_ids,
        "complete": complete,
    }
    stable_payload = {
        **payload,
        "cases": [
            {
                "case_id": result.case_id,
                "conclusion": result.conclusion.value,
                "invocations": sorted(
                    (
                        invocation.kind.value,
                        invocation.capability_name,
                        invocation.handler_identity,
                        invocation.outcome,
                    )
                    for invocation in result.invocations
                ),
                "assertions": [
                    (assertion.assertion_id, assertion.status.value)
                    for assertion in result.assertions
                ],
                "gates": [
                    {
                        "kind": gate.gate_kind.value,
                        "status": gate.status.value,
                        "conditions": [
                            condition.condition_id for condition in gate.conditions
                        ],
                    }
                    for gate in result.gates
                ],
                "problems": list(result.problems),
            }
            for result in results
        ],
        "provider_interruptions": [
            {
                "case_id": item.case_id,
                "state": item.state.value,
                "error_type": item.error_type,
                "error_code": item.error_code,
                "status_code": item.status_code,
            }
            for item in interruptions
        ],
    }
    return LiveSuiteBaselineResult(
        suite_id=selection.suite_id,
        suite_content_hash=selection.suite_content_hash,
        runtime_config_identity=runtime_config_identity,
        track=TrackKind.LIVE_PROVIDER,
        applicable_case_ids=selection.applicable_case_ids,
        selected_case_ids=selection.selected_case_ids,
        cases=results,
        provider_state=provider_state,
        provider_interruptions=interruptions,
        case_count=selection.case_count,
        executed_case_count=len(results),
        passed_case_count=passed,
        failed_case_count=len(results) - passed,
        pending_case_ids=pending_case_ids,
        complete=complete,
        result_hash=canonical_sha256(payload),
        stable_result_hash=canonical_sha256(stable_payload),
    )


def _model_phase(task_name: str) -> str:
    if task_name.endswith(".plan"):
        return "plan"
    if task_name.endswith(".replan"):
        return "replan"
    if task_name.endswith(".verify"):
        return "verify"
    return task_name


def _live_invocation_problems(
    expected: tuple[RequiredInvocationSpec, ...],
    observed: tuple[SyntheticCapabilityInvocation, ...],
    *,
    scripted_capabilities: frozenset[tuple[CapabilityKind, str]],
) -> tuple[str, ...]:
    """恢复成功的失败尝试计入 attempts，但不冒充最终能力失败。"""
    problems: list[str] = []
    expected_keys = {(item.type, item.name) for item in expected}
    observed_keys = {(item.kind, item.capability_name) for item in observed}
    for item in expected:
        completed = tuple(
            invocation
            for invocation in observed
            if invocation.kind is item.type
            and invocation.capability_name == item.name
            and invocation.outcome == item.expected_outcome
        )
        if not item.min_calls <= len(completed) <= item.max_calls:
            problems.append(
                f"{item.type.value}:{item.name} completed 调用次数 "
                f"{len(completed)} 不在 {item.min_calls}..{item.max_calls}"
            )
    unexpected = sorted(
        f"{kind.value}:{name}"
        for kind, name in (observed_keys - expected_keys - scripted_capabilities)
    )
    if unexpected:
        problems.append("出现未声明能力调用：" + "、".join(unexpected))
    return tuple(problems)


def _live_human_problems(
    case: AuthoredCaseSpec,
    interactions: tuple[RuntimeInteractionRecord, ...],
) -> tuple[str, ...]:
    expected: dict[str, int] = {}
    for step in case.scripted_steps:
        if step.kind is not InteractionKind.HUMAN:
            continue
        runtime_kind = (
            "write_authorization" if step.name == "second_confirmation" else step.name
        )
        expected[runtime_kind] = expected.get(runtime_kind, 0) + 1
    observed: dict[str, int] = {}
    for record in interactions:
        interaction = record.interaction
        if interaction.kind is not InteractionKind.HUMAN:
            continue
        observed[interaction.name] = observed.get(interaction.name, 0) + 1
    problems = [
        f"human:{name} 决定次数 {count} 不等于合同声明 {expected.get(name, 0)}"
        for name, count in sorted(observed.items())
        if count != expected.get(name, 0)
    ]
    problems.extend(
        f"human:{name} 决定次数 0 不等于合同声明 {count}"
        for name, count in sorted(expected.items())
        if name not in observed
    )
    return tuple(problems)
