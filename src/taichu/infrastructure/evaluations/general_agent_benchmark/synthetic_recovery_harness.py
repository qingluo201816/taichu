"""把密封 FaultPlan 接到真实 Runtime 恢复生命周期与 Typed Oracle 投影。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from taichu.application.capabilities import CapabilityContext
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.faults import (
    FaultPoint,
    FaultPressureAdapter,
    FaultRunIdentity,
    FaultStep,
    JsonFaultTriggerStore,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    ObservedRecoveryDecision,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionEvaluationContext,
    CheckpointIntegrityObservation,
    RecoveryReuseObservation,
)
from taichu.application.evaluations.general_agent_benchmark.run_lineage import (
    CapturedRunLineage,
    capture_run_lineage,
)
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ScriptedMatcher,
    ScriptedStep,
    StrictScriptedDriver,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    FaultPlanAssetSpec,
)
from taichu.application.general_agent.events import GeneralAgentEventCenter
from taichu.application.general_agent.faults import InjectedProcessTermination
from taichu.application.general_agent.models import (
    GeneralAgentRun,
    GeneralAgentRunStatus,
    RecoveryAction,
)
from taichu.application.general_agent.recovery import EffectStatus
from taichu.application.services.chapter_service import ChapterService
from taichu.application.tools import apply_manuscript_patch
from taichu.application.tools._manuscript import (
    normalize_and_apply_patch,
    patch_id,
)
from taichu.application.tools._shared import sha256_text
from taichu.application.tools.contract import ToolAuthorizationPolicy
from taichu.application.tools.models import ManuscriptPatchOperation
from taichu.infrastructure.evaluations.general_agent_benchmark.recovery_harness import (
    GeneralAgentRecoveryHarness,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    BenchmarkRuntimeDependencies,
    GeneralAgentBenchmarkRuntimeFactory,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_runtime import (
    StrictSyntheticLLMGateway,
)
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentContextSnapshotRepository,
    JsonGeneralAgentEffectRepository,
    JsonGeneralAgentRunRepository,
    JsonLangGraphCheckpointSaver,
)
from taichu.infrastructure.llm_replays import JsonLLMCallReplayRepository


@dataclass(frozen=True, slots=True)
class SyntheticRecoveryHarnessResult:
    """统一案例观察所需的真实恢复终态与窄投影。"""

    run: GeneralAgentRun
    lineage: CapturedRunLineage
    assertion_context: AssertionEvaluationContext
    recovery_decisions: tuple[ObservedRecoveryDecision, ...]
    model_call_count: int
    triggered_ordinals: tuple[int, ...]


class SyntheticRecoveryHarness:
    """只按 FaultPlan 注入点选择真实恢复场景，不读取 Benchmark case ID。"""

    def __init__(
        self,
        *,
        workspace: Path,
        factory: GeneralAgentBenchmarkRuntimeFactory,
        dependencies: BenchmarkRuntimeDependencies,
    ) -> None:
        self._workspace = workspace
        self._factory = factory
        self._dependencies = dependencies

    async def execute(
        self,
        *,
        case: AuthoredCaseSpec,
        asset: FaultPlanAssetSpec,
    ) -> SyntheticRecoveryHarnessResult:
        points = tuple(FaultPoint(item) for item in asset.injection_points)
        steps = tuple(
            FaultStep(ordinal=index, point=point, once=True)
            for index, point in enumerate(points, start=1)
        )
        gateway, allowed = await self._gateway(points)
        preexisting = await self._run_ids()
        if points == (FaultPoint.CHECKPOINT_REVISION_VALIDATION,):
            run, triggered = await self._checkpoint_failure(
                case=case,
                asset=asset,
                gateway=gateway,
                allowed=allowed,
                step=steps[0],
            )
            plan_before_sha256 = _run_plan_sha256(run)
            plan_after_sha256 = plan_before_sha256
            interrupted_runs: tuple[GeneralAgentRun, ...] = ()
        else:
            adapter = FaultPressureAdapter(
                JsonFaultTriggerStore(
                    self._workspace / "runtime" / "fault_pressure" / asset.asset_id
                )
            )
            harness_result = await GeneralAgentRecoveryHarness(
                runtime_builder=self._runtime_builder(
                    gateway=gateway,
                    allowed=allowed,
                    bypass_write_authorization=(
                        FaultPoint.RESOURCE_WRITE_APPLIED in points
                        and FaultPoint.AUTHORIZATION_REQUEST_DURABLE not in points
                    ),
                ),
                fault_adapter=adapter,
            ).execute(
                user_goal=case.user_request_raw,
                plan_id=asset.asset_id,
                steps=steps,
                runtime_arguments={
                    "conversation_id": "benchmark_fixture_conversation",
                },
            )
            run = harness_result.recovered_run
            triggered = harness_result.triggered_ordinals
            plan_before_sha256 = harness_result.plan_before_sha256
            plan_after_sha256 = harness_result.plan_after_sha256
            interrupted_runs = harness_result.interrupted_runs

        observed_runs, _ = await JsonGeneralAgentRunRepository(
            self._workspace
        ).list_runs(page=1, page_size=10_000, status="all")
        lineage = capture_run_lineage(
            preexisting_run_ids=preexisting,
            observed_runs=tuple(observed_runs),
            returned_run_id=run.run_id,
            case_user_request_raw=case.user_request_raw,
        )
        effects = await JsonGeneralAgentEffectRepository(
            self._workspace
        ).list_effects(run.run_id)
        decisions = _project_decisions(
            run,
            fault_plan_ref=asset.asset_id,
            triggered_ordinals=triggered,
        )
        if points == (FaultPoint.CHECKPOINT_REVISION_VALIDATION,):
            assertion_context = AssertionEvaluationContext(
                checkpoint_integrity=(
                    _checkpoint_projection(
                        workspace=self._workspace,
                        run=run,
                        fault_plan_ref=asset.asset_id,
                        effects=effects,
                    ),
                )
            )
        else:
            retry_ids = tuple(
                sorted(
                    {
                        str(result_id)
                        for decision in run.recovery_decisions
                        for result_id in decision.evidence.get(
                            "retried_capability_result_ids",
                            (),
                        )
                    }
                )
            )
            reused_ids = tuple(
                sorted(
                    {
                        str(result_id)
                        for decision in run.recovery_decisions
                        for result_id in decision.evidence.get(
                            "reused_capability_result_ids",
                            (),
                        )
                    }
                )
            )
            assertion_context = AssertionEvaluationContext(
                recovery_reuse=(
                    RecoveryReuseObservation(
                        fault_plan_ref=asset.asset_id,
                        plan_before_sha256=plan_before_sha256,
                        plan_after_sha256=plan_after_sha256,
                        successful_node_reexecutions=len(retry_ids),
                        duplicate_side_effects=_duplicate_side_effects(effects),
                        reused_result_ids=reused_ids,
                        retried_successful_result_ids=retry_ids,
                    ),
                )
            )
            _assert_interrupted_snapshots_are_same_run(
                interrupted_runs,
                recovered=run,
            )
        return SyntheticRecoveryHarnessResult(
            run=run,
            lineage=lineage,
            assertion_context=assertion_context,
            recovery_decisions=decisions,
            model_call_count=len(gateway.requests),
            triggered_ordinals=triggered,
        )

    async def _gateway(
        self,
        points: tuple[FaultPoint, ...],
    ) -> tuple[StrictSyntheticLLMGateway, frozenset[str]]:
        plan, allowed = await self._execution_plan(points)
        steps: list[ScriptedStep] = [
            _model_step(
                sequence=0,
                step_id="recovery_model_plan",
                name="recovery_orchestrator_plan",
                phase="plan",
                response=plan,
            )
        ]
        if FaultPoint.SUBAGENT_STARTED in points:
            subagent_response = {
                "lifecycle": "draft",
                "artifact_type": "narrative_summary",
                "summary": "完整恢复结果已形成，未消费中断半成品。",
                "key_events": ["恢复后只提交一次完整子智能体结果"],
                "character_changes": [],
                "unresolved_items": [],
                "source_refs": [],
                "warnings": [],
            }
            for attempt in ("interrupted", "recovered"):
                steps.append(
                    _model_step(
                        sequence=len(steps),
                        step_id=f"recovery_model_subagent_{attempt}",
                        name=f"recovery_narrative_summary_{attempt}",
                        phase="narrative_summary",
                        response=subagent_response,
                    )
                )
        steps.append(
            _model_step(
                sequence=len(steps),
                step_id="recovery_model_verify",
                name="recovery_orchestrator_verify",
                phase="verify",
                response={
                    "outcome": "satisfied",
                    "final_answer": "故障恢复后已依据持久证据完成原计划。",
                    "issues": [],
                    "should_replan": False,
                },
            )
        )
        return (
            StrictSyntheticLLMGateway(StrictScriptedDriver(tuple(steps))),
            allowed,
        )

    async def _execution_plan(
        self,
        points: tuple[FaultPoint, ...],
    ) -> tuple[dict[str, Any], frozenset[str]]:
        if FaultPoint.SUBAGENT_STARTED in points:
            return (
                {
                    "rationale": "形成一次完整子智能体结果后再校验。",
                    "nodes": [
                        {
                            "node_id": "recovery_subagent",
                            "kind": "subagent",
                            "capability_name": "narrative_summary",
                            "objective": "形成完整且可提交的恢复摘要。",
                            "input_data": {
                                "summary_goal": "验证中断后只消费完整结果。",
                                "target_chars": 100,
                                "source_request": {"auto_collect": False},
                            },
                        }
                    ],
                },
                frozenset({"narrative_summary"}),
            )
        if FaultPoint.AUTHORIZATION_REQUEST_DURABLE in points:
            chapter_service = self._dependencies.capability_context.require(
                "chapter_service",
                ChapterService,
            )
            chapter = await chapter_service.read_chapter("chapter_001")
            preview_node = {
                "node_id": "recovery_preview",
                "kind": "tool",
                "capability_name": "preview_manuscript_patch",
                "objective": "冻结本次恢复写入的正文预览。",
                "input_data": {
                    "chapter_id": "chapter_001",
                    "base_content_sha256": sha256_text(chapter.markdown),
                    "operations": [
                        {
                            "operation": "append",
                            "text": "\n恢复基准写入哨兵。",
                        }
                    ],
                },
            }
            apply_node = {
                "node_id": "recovery_apply",
                "kind": "tool",
                "capability_name": "apply_manuscript_patch",
                "objective": "仅在作者授权后应用同一预览。",
                "dependencies": ["recovery_preview"],
                "input_data": {},
                "input_bindings": [
                    {
                        "source_node_id": "recovery_preview",
                        "source_path": "patch_id",
                        "target_path": "patch_id",
                    },
                    {
                        "source_node_id": "recovery_preview",
                        "source_path": "chapter_id",
                        "target_path": "chapter_id",
                    },
                    {
                        "source_node_id": "recovery_preview",
                        "source_path": "base_content_sha256",
                        "target_path": "base_content_sha256",
                    },
                    {
                        "source_node_id": "recovery_preview",
                        "source_path": "expected_content_sha256",
                        "target_path": "expected_content_sha256",
                    },
                    {
                        "source_node_id": "recovery_preview",
                        "source_path": "normalized_operations",
                        "target_path": "operations",
                    },
                ],
            }
            nodes: list[dict[str, Any]] = [preview_node, apply_node]
            if FaultPoint.PLAN_CREATED in points:
                nodes.insert(
                    0,
                    {
                        "node_id": "recovery_read",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取同一恢复计划所需结构。",
                        "input_data": {},
                    },
                )
                preview_node["dependencies"] = ["recovery_read"]
            return (
                {
                    "rationale": "冻结预览、取得授权并以幂等副作用完成恢复。",
                    "nodes": nodes,
                },
                frozenset(
                    {
                        "get_novel_structure",
                        "preview_manuscript_patch",
                        "apply_manuscript_patch",
                    }
                ),
            )
        if FaultPoint.RESOURCE_WRITE_APPLIED in points:
            chapter_service = self._dependencies.capability_context.require(
                "chapter_service",
                ChapterService,
            )
            chapter = await chapter_service.read_chapter("chapter_001")
            operation = ManuscriptPatchOperation(
                operation="append",
                text="\n恢复基准写入哨兵。",
            )
            operations, expected_content = normalize_and_apply_patch(
                chapter.markdown,
                [operation],
            )
            base_sha256 = sha256_text(chapter.markdown)
            apply_node: dict[str, Any] = {
                "node_id": "recovery_apply",
                "kind": "tool",
                "capability_name": "apply_manuscript_patch",
                "objective": "应用已由场景夹具预授权的确定正文补丁。",
                "input_data": {
                    "patch_id": patch_id(
                        "chapter_001",
                        base_sha256,
                        operations,
                    ),
                    "chapter_id": "chapter_001",
                    "base_content_sha256": base_sha256,
                    "expected_content_sha256": sha256_text(expected_content),
                    "operations": [
                        item.model_dump(mode="json") for item in operations
                    ],
                    "author_grant_id": "benchmark_recovery_presealed",
                    "idempotency_key": "benchmark-recovery-write-once",
                },
            }
            nodes: list[dict[str, Any]] = [apply_node]
            allowed = {"apply_manuscript_patch"}
            if FaultPoint.PLAN_CREATED in points:
                nodes.insert(
                    0,
                    {
                        "node_id": "recovery_read",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取同一恢复计划所需结构。",
                        "input_data": {},
                    },
                )
                apply_node["dependencies"] = ["recovery_read"]
                allowed.add("get_novel_structure")
            return (
                {
                    "rationale": "在隔离授权误差后验证写入副作用的精确一次恢复。",
                    "nodes": nodes,
                },
                frozenset(allowed),
            )
        return (
            {
                "rationale": "读取一次结构并复用持久结果完成校验。",
                "nodes": [
                    {
                        "node_id": "recovery_read",
                        "kind": "tool",
                        "capability_name": "get_novel_structure",
                        "objective": "读取一次当前小说结构。",
                        "input_data": {},
                    }
                ],
            },
            frozenset({"get_novel_structure"}),
        )

    def _runtime_builder(
        self,
        *,
        gateway: StrictSyntheticLLMGateway,
        allowed: frozenset[str],
        bypass_write_authorization: bool = False,
    ):
        def build(hook: object):
            dependencies = self._fresh_dependencies(
                gateway=gateway,
                fault_hook=hook,
            )
            return self._factory.create(
                dependencies,
                allowed_capabilities=allowed,
                tool_manifest_overrides=(
                    {
                        "apply_manuscript_patch": (
                            apply_manuscript_patch.manifest.model_copy(
                                update={
                                    "authorization_policy": (
                                        ToolAuthorizationPolicy.NONE
                                    )
                                }
                            )
                        )
                    }
                    if bypass_write_authorization
                    else None
                ),
            ).runtime

        return build

    def _fresh_dependencies(
        self,
        *,
        gateway: StrictSyntheticLLMGateway,
        fault_hook: object | None,
    ) -> BenchmarkRuntimeDependencies:
        return replace(
            self._dependencies,
            capability_context=CapabilityContext(
                capabilities={
                    **self._dependencies.capability_context.capabilities,
                    "llm": gateway,
                }
            ),
            llm=gateway,
            run_repository=JsonGeneralAgentRunRepository(self._workspace),
            event_center=GeneralAgentEventCenter(),
            graph_checkpointer=JsonLangGraphCheckpointSaver(self._workspace),
            effect_repository=JsonGeneralAgentEffectRepository(self._workspace),
            context_snapshot_repository=(
                JsonGeneralAgentContextSnapshotRepository(self._workspace)
            ),
            llm_replay_repository=JsonLLMCallReplayRepository(self._workspace),
            interaction_observer=None,
            fault_hook=fault_hook,  # type: ignore[arg-type]
        )

    async def _checkpoint_failure(
        self,
        *,
        case: AuthoredCaseSpec,
        asset: FaultPlanAssetSpec,
        gateway: StrictSyntheticLLMGateway,
        allowed: frozenset[str],
        step: FaultStep,
    ) -> tuple[GeneralAgentRun, tuple[int, ...]]:
        preparation_adapter = FaultPressureAdapter(
            JsonFaultTriggerStore(
                self._workspace
                / "runtime"
                / "fault_pressure"
                / f"{asset.asset_id}_prepare"
            )
        )
        preparation_hook = preparation_adapter.bind_runtime(
            plan_id=f"{asset.asset_id}_prepare",
            steps=(
                FaultStep(
                    ordinal=1,
                    point=FaultPoint.PLAN_CREATED,
                    once=True,
                ),
            ),
        )
        first = self._runtime_builder(gateway=gateway, allowed=allowed)(
            preparation_hook
        )
        try:
            try:
                await first.run(
                    user_goal=case.user_request_raw,
                    conversation_id="benchmark_fixture_conversation",
                )
            except InjectedProcessTermination:
                pass
            else:
                raise RuntimeError("Checkpoint 损坏准备阶段没有在计划持久化后中断。")
            preparation_plan = preparation_hook.resolved_plan
            if preparation_plan is None:
                raise RuntimeError("Checkpoint 损坏准备阶段缺少真实运行身份。")
            interrupted = await first.get(preparation_plan.run_identity.run_id)
        finally:
            await first.shutdown()

        revision_root = (
            self._workspace
            / "derived"
            / "general_agent_graph_checkpoints"
            / interrupted.run_id
            / "revisions"
        )
        revisions = tuple(sorted(revision_root.glob("*.json")))
        if not revisions:
            raise RuntimeError("Checkpoint 损坏场景没有可注入的真实修订。")
        for revision in revisions:
            revision.write_text("{密封故障：修订损坏", encoding="utf-8")

        adapter = FaultPressureAdapter(
            JsonFaultTriggerStore(
                self._workspace / "runtime" / "fault_pressure" / asset.asset_id
            )
        )
        plan = adapter.store.load_or_create_plan(
            plan_id=asset.asset_id,
            run_identity=FaultRunIdentity(
                conversation_id=interrupted.conversation_id,
                run_id=interrupted.run_id,
            ),
            steps=(step,),
        )
        validation = self._runtime_builder(gateway=gateway, allowed=allowed)(
            adapter.bind(plan)
        )
        try:
            try:
                await validation.recover_interrupted()
            except InjectedProcessTermination:
                pass
            else:
                raise RuntimeError("Checkpoint 修订校验故障点没有真实触发。")
        finally:
            await validation.shutdown()

        restarted = self._runtime_builder(gateway=gateway, allowed=allowed)(
            adapter.bind(plan)
        )
        try:
            recovered_count = await restarted.recover_interrupted()
            if recovered_count != 0:
                raise RuntimeError("全部 Checkpoint 损坏后不得自动重启执行图。")
            stopped = await restarted.get(interrupted.run_id)
        finally:
            await restarted.shutdown()
        if (
            stopped.status is not GeneralAgentRunStatus.FAILED
            or stopped.resumable
        ):
            raise RuntimeError("全部 Checkpoint 损坏后 Runtime 未安全停止。")
        return stopped, adapter.store.load(plan).triggered_ordinals

    async def _run_ids(self) -> tuple[str, ...]:
        runs, _ = await JsonGeneralAgentRunRepository(self._workspace).list_runs(
            page=1,
            page_size=10_000,
            status="all",
        )
        return tuple(sorted(item.run_id for item in runs))


def _model_step(
    *,
    sequence: int,
    step_id: str,
    name: str,
    phase: str,
    response: dict[str, Any],
) -> ScriptedStep:
    return ScriptedStep(
        step_id=step_id,
        sequence=sequence,
        kind=InteractionKind.MODEL,
        name=name,
        matchers=(ScriptedMatcher(path="/phase", expected=phase),),
        evidence_projection=("/phase",),
        response=response,
    )


def _run_plan_sha256(run: GeneralAgentRun) -> str | None:
    return (
        canonical_sha256(run.plan)
        if run.plan is not None
        else None
    )


def _project_decisions(
    run: GeneralAgentRun,
    *,
    fault_plan_ref: str,
    triggered_ordinals: tuple[int, ...],
) -> tuple[ObservedRecoveryDecision, ...]:
    projected = [
        ObservedRecoveryDecision(
            decision_id=item.decision_id,
            action={
                RecoveryAction.REUSE: "reuse_result",
                RecoveryAction.RETRY: "retry",
                RecoveryAction.RECONCILE: "reconcile_effect",
                RecoveryAction.RESUME: "resume",
                RecoveryAction.REQUIRES_HUMAN: "stop",
                RecoveryAction.STOP: "stop",
            }[item.action],
            reason_code=item.reason_code,
            result_id=(
                str(item.evidence["reused_capability_result_ids"][0])
                if item.evidence.get("reused_capability_result_ids")
                else item.effect_id
            ),
            checkpoint_revision=item.checkpoint_revision,
            evidence_sha256=item.evidence_sha256,
        )
        for item in run.recovery_decisions
    ]
    if (
        not projected
        and run.status is GeneralAgentRunStatus.WAITING_HUMAN
        and run.pending_human_request is not None
    ):
        payload = {
            "fault_plan_ref": fault_plan_ref,
            "triggered_ordinals": triggered_ordinals,
            "run_id": run.run_id,
            "request_id": run.pending_human_request.request_id,
            "request_kind": run.pending_human_request.kind,
            "input_sha256": run.pending_human_request.input_sha256,
        }
        evidence_sha256 = canonical_sha256(payload)
        projected.append(
            ObservedRecoveryDecision(
                decision_id=f"recovery_waiting_{evidence_sha256[:32]}",
                action="resume",
                reason_code="waiting_authorization",
                result_id=None,
                checkpoint_revision=None,
                evidence_sha256=evidence_sha256,
            )
        )
    return tuple(projected)


def _duplicate_side_effects(effects: tuple[Any, ...] | list[Any]) -> int:
    attempts: dict[str, set[str]] = {}
    for effect in effects:
        attempts.setdefault(effect.effect_id, set()).add(effect.attempt_id)
    return sum(max(0, len(items) - 1) for items in attempts.values())


def _checkpoint_projection(
    *,
    workspace: Path,
    run: GeneralAgentRun,
    fault_plan_ref: str,
    effects: tuple[Any, ...] | list[Any],
) -> CheckpointIntegrityObservation:
    summary = JsonLangGraphCheckpointSaver(workspace).inspect_thread(run.run_id)
    valid = tuple(
        revision
        for revision in summary.available_revisions
        if revision not in set(summary.invalid_revisions)
    )
    last = run.recovery_decisions[-1] if run.recovery_decisions else None
    automatic_restart_count = (
        int(last.evidence.get("automatic_restart_count", 0))
        if last is not None
        else 0
    )
    latest_effects: dict[str, Any] = {}
    for effect in effects:
        latest_effects[effect.effect_id] = effect
    statuses = {item.status for item in latest_effects.values()}
    effect_state = (
        "unknown"
        if EffectStatus.UNKNOWN in statuses
        else "requires_human"
        if EffectStatus.REQUIRES_HUMAN in statuses
        else "settled"
        if statuses
        else "not_applicable"
    )
    selected = (
        summary.recovered_from_revision
        if summary.recovered_from_revision in valid
        else summary.current_revision
        if summary.current_revision in valid
        else None
    )
    return CheckpointIntegrityObservation(
        fault_plan_ref=fault_plan_ref,
        valid_revisions=valid,
        invalid_revisions=tuple(summary.invalid_revisions),
        selected_revision=selected,
        recovery_action=(
            "stop"
            if last is not None and last.action is RecoveryAction.STOP
            else "resume"
        ),
        automatic_restart_count=automatic_restart_count,
        effect_state=effect_state,
    )


def _assert_interrupted_snapshots_are_same_run(
    interrupted: tuple[GeneralAgentRun, ...],
    *,
    recovered: GeneralAgentRun,
) -> None:
    if any(
        item.run_id != recovered.run_id
        or item.conversation_id != recovered.conversation_id
        for item in interrupted
    ):
        raise RuntimeError("恢复案例的中断快照没有保持同一逻辑运行 owner。")


__all__ = [
    "SyntheticRecoveryHarness",
    "SyntheticRecoveryHarnessResult",
]
