"""需求 15.1、15.2、15.3、15.16、15.18、15.23：首轮 live 冻结。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.correlation import (
    CorrelationSubjectKind,
    CorrelationSubjectRef,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    ProviderExecutionState,
)


class FirstLiveIterationState(StrEnum):
    AWAITING_SYNTHETIC = "awaiting_synthetic"
    READY_FOR_DEEPSEEK = "ready_for_deepseek"
    DEEPSEEK_RUNNING = "deepseek_running"
    CLASSIFYING = "classifying"
    CLOSING_SYSTEM_DEFECTS = "closing_system_defects"
    READY_FOR_COMPARISON = "ready_for_comparison"
    BLOCKED = "blocked"
    INVALID = "invalid"


class FirstLiveRevisionConflict(RuntimeError):
    """首轮迭代 revision 与调用方期望不一致。"""


class FirstLiveStateError(RuntimeError):
    """首轮迭代状态不允许当前动作。"""


class FirstLiveArtifact(BenchmarkModel):
    artifact_id: str = Field(pattern=r"^first_live_[a-f0-9]{64}$")
    iteration_id: StableId
    code_hash: Sha256
    suite_hash: Sha256
    fixture_hash: Sha256
    capability_catalog_hash: Sha256
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    completed_case_ids: tuple[StableId, ...]
    synthetic_qualification_artifact_refs: tuple[str, ...] = Field(
        min_length=1
    )
    requested_model_ref: Literal["deepseek-v4-pro"]
    actual_provider_id: StableId | None
    actual_model_id: str | None = Field(default=None, min_length=1)
    probe_succeeded: bool
    fallback_used: bool
    replay_available: bool
    usage_available: bool
    cost_available: bool
    error_code: str | None = Field(default=None, min_length=1)
    provider_state: ProviderExecutionState
    suite_artifact_ref: str | None
    failure_record_refs: tuple[str, ...]
    complete: bool
    correlation_subject: CorrelationSubjectRef
    artifact_hash: Sha256

    @model_validator(mode="after")
    def _state_matches_completeness(self) -> FirstLiveArtifact:
        if self.provider_state is ProviderExecutionState.COMPLETED:
            if not self.complete:
                raise ValueError("completed 首轮必须标记为完整。")
            if set(self.completed_case_ids) != set(self.selected_case_ids):
                raise ValueError("completed 首轮必须覆盖完整案例集合。")
            if not self.suite_artifact_ref:
                raise ValueError("completed 首轮必须包含套件工件引用。")
        elif self.provider_state in {
            ProviderExecutionState.BLOCKED,
            ProviderExecutionState.ERROR,
        }:
            if self.complete:
                raise ValueError("blocked/error 首轮不得冒充完整结果。")
        else:
            raise ValueError("首轮冻结只接受 completed、blocked 或 error。")
        return self


class FirstLiveIterationManifest(BenchmarkModel):
    iteration_id: StableId
    revision: int = Field(ge=0)
    state: FirstLiveIterationState
    code_hash: Sha256
    suite_hash: Sha256
    fixture_hash: Sha256
    capability_catalog_hash: Sha256
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    synthetic_qualification_artifact_refs: tuple[str, ...] = Field(
        min_length=1
    )
    prior_iteration_ids: tuple[StableId, ...]
    first_live_artifact_ref: str | None
    pending_intent_refs: tuple[str, ...]
    confirmed_relation_refs: tuple[str, ...]
    comparison_refs: tuple[str, ...]
    latest_comparison_ref: str | None
    problems: tuple[str, ...]

    @field_validator("selected_case_ids", "prior_iteration_ids")
    @classmethod
    def _ids_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("首轮迭代 ID 集合不得重复。")
        return value


class FirstLiveIterationService:
    """以显式身份和 CAS 管理首轮，不依赖目录或文件名顺序。"""

    def __init__(self) -> None:
        self._manifests: dict[str, FirstLiveIterationManifest] = {}
        self._artifacts: dict[str, FirstLiveArtifact] = {}

    def restore_frozen(
        self,
        manifest: FirstLiveIterationManifest,
        artifact: FirstLiveArtifact,
    ) -> None:
        """恢复一个已校验的冻结首轮视图，禁止覆盖不同内容。"""

        if manifest.first_live_artifact_ref != artifact.artifact_id:
            raise FirstLiveStateError("冻结首轮清单与工件引用不一致。")
        existing_manifest = self._manifests.get(manifest.iteration_id)
        existing_artifact = self._artifacts.get(artifact.artifact_id)
        if existing_manifest is not None and existing_manifest != manifest:
            raise FirstLiveStateError("冻结首轮清单恢复冲突。")
        if existing_artifact is not None and existing_artifact != artifact:
            raise FirstLiveStateError("冻结首轮工件恢复冲突。")
        self._manifests[manifest.iteration_id] = manifest
        self._artifacts[artifact.artifact_id] = artifact

    def create_iteration(
        self,
        *,
        iteration_id: str,
        code_hash: str,
        suite_hash: str,
        fixture_hash: str,
        capability_catalog_hash: str,
        selected_case_ids: tuple[str, ...],
        synthetic_qualification_artifact_refs: tuple[str, ...],
        synthetic_suite_passed: bool,
        core_gates_passed: bool,
        memory_gates_passed: bool,
        mechanism_gates_passed: bool,
        prior_iteration_ids: tuple[str, ...] = (),
    ) -> FirstLiveIterationManifest:
        if iteration_id in self._manifests:
            raise FirstLiveStateError("首轮迭代已经存在，不能覆盖。")
        missing_prior = [
            item
            for item in prior_iteration_ids
            if item not in self._manifests
        ]
        if missing_prior:
            raise FirstLiveStateError(
                "前序迭代不存在：" + ", ".join(missing_prior)
            )
        checks = (
            ("synthetic 全量套件未通过。", synthetic_suite_passed),
            ("核心硬门禁未通过。", core_gates_passed),
            ("工作记忆硬门禁未通过。", memory_gates_passed),
            ("局部机制硬门禁未通过。", mechanism_gates_passed),
        )
        problems = tuple(message for message, passed in checks if not passed)
        state = (
            FirstLiveIterationState.AWAITING_SYNTHETIC
            if problems
            else FirstLiveIterationState.READY_FOR_DEEPSEEK
        )
        manifest = FirstLiveIterationManifest(
            iteration_id=iteration_id,
            revision=0,
            state=state,
            code_hash=code_hash,
            suite_hash=suite_hash,
            fixture_hash=fixture_hash,
            capability_catalog_hash=capability_catalog_hash,
            selected_case_ids=selected_case_ids,
            synthetic_qualification_artifact_refs=(
                synthetic_qualification_artifact_refs
            ),
            prior_iteration_ids=prior_iteration_ids,
            first_live_artifact_ref=None,
            pending_intent_refs=(),
            confirmed_relation_refs=(),
            comparison_refs=(),
            latest_comparison_ref=None,
            problems=problems,
        )
        self._manifests[iteration_id] = manifest
        return manifest

    def start(
        self,
        iteration_id: str,
        *,
        expected_revision: int,
        requested_model_ref: str,
    ) -> FirstLiveIterationManifest:
        current = self._expected(iteration_id, expected_revision)
        if requested_model_ref != "deepseek-v4-pro":
            raise FirstLiveStateError(
                "首轮闭环前只能单独运行 DeepSeek V4 Pro。"
            )
        if current.state is not FirstLiveIterationState.READY_FOR_DEEPSEEK:
            raise FirstLiveStateError("当前迭代尚未达到 DeepSeek 首轮准入状态。")
        return self._save(
            current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "state": FirstLiveIterationState.DEEPSEEK_RUNNING,
                }
            ),
            expected_revision=expected_revision,
        )

    def freeze(
        self,
        iteration_id: str,
        *,
        expected_revision: int,
        provider_state: ProviderExecutionState,
        completed_case_ids: tuple[str, ...],
        suite_artifact_ref: str | None,
        actual_provider_id: str | None,
        actual_model_id: str | None,
        probe_succeeded: bool,
        fallback_used: bool,
        replay_available: bool,
        usage_available: bool,
        cost_available: bool,
        error_code: str | None,
        failure_record_refs: tuple[str, ...],
    ) -> tuple[FirstLiveArtifact, FirstLiveIterationManifest]:
        current = self._expected(iteration_id, expected_revision)
        if current.first_live_artifact_ref is not None:
            raise FirstLiveStateError("首轮工件已经冻结，不能覆盖。")
        if current.state is not FirstLiveIterationState.DEEPSEEK_RUNNING:
            raise FirstLiveStateError("只有运行中的 DeepSeek 首轮可以冻结。")
        state = ProviderExecutionState(provider_state)
        completed_set = set(completed_case_ids)
        if len(completed_set) != len(completed_case_ids):
            raise FirstLiveStateError("已完成案例集合不得重复。")
        if not completed_set <= set(current.selected_case_ids):
            raise FirstLiveStateError("已完成案例包含未选择案例。")
        complete = state is ProviderExecutionState.COMPLETED
        if complete and completed_set != set(current.selected_case_ids):
            raise FirstLiveStateError("completed 首轮必须覆盖完整案例集合。")
        if complete and (
            suite_artifact_ref is None
            or actual_provider_id is None
            or actual_model_id is None
            or not probe_succeeded
            or fallback_used
            or not replay_available
            or not usage_available
            or not cost_available
            or error_code is not None
        ):
            raise FirstLiveStateError("completed 首轮缺少完整 provider 审计证据。")
        if state not in {
            ProviderExecutionState.COMPLETED,
            ProviderExecutionState.BLOCKED,
            ProviderExecutionState.ERROR,
        }:
            raise FirstLiveStateError(
                "首轮冻结只接受 completed、blocked 或 error。"
            )
        artifact = self._build_artifact(
            current=current,
            provider_state=state,
            completed_case_ids=completed_case_ids,
            suite_artifact_ref=suite_artifact_ref,
            actual_provider_id=actual_provider_id,
            actual_model_id=actual_model_id,
            probe_succeeded=probe_succeeded,
            fallback_used=fallback_used,
            replay_available=replay_available,
            usage_available=usage_available,
            cost_available=cost_available,
            error_code=error_code,
            failure_record_refs=failure_record_refs,
            complete=complete,
        )
        if artifact.artifact_id in self._artifacts:
            raise FirstLiveStateError("首轮工件 identity 已存在，不能覆盖。")
        self._artifacts[artifact.artifact_id] = artifact
        manifest_state = (
            FirstLiveIterationState.CLASSIFYING
            if complete
            else FirstLiveIterationState.BLOCKED
        )
        problems = (
            ()
            if complete
            else (
                f"DeepSeek V4 Pro 首轮状态为 {state.value}，闭环未完成。",
            )
        )
        updated = current.model_copy(
            update={
                "revision": current.revision + 1,
                "state": manifest_state,
                "first_live_artifact_ref": artifact.artifact_id,
                "problems": problems,
            }
        )
        return artifact, self._save(
            updated,
            expected_revision=expected_revision,
        )

    def require_comparison_ready(
        self,
        iteration_id: str,
    ) -> FirstLiveIterationManifest:
        current = self._manifests[iteration_id]
        if current.state is not FirstLiveIterationState.READY_FOR_COMPARISON:
            raise FirstLiveStateError(
                "首轮闭环前禁止启动或发布多模型比较。"
            )
        return current

    def get_manifest(self, iteration_id: str) -> FirstLiveIterationManifest:
        return self._manifests[iteration_id]

    def get_artifact(self, artifact_id: str) -> FirstLiveArtifact:
        return self._artifacts[artifact_id]

    def list_iterations(self) -> tuple[FirstLiveIterationManifest, ...]:
        return tuple(self._manifests.values())

    def _expected(
        self,
        iteration_id: str,
        expected_revision: int,
    ) -> FirstLiveIterationManifest:
        current = self._manifests[iteration_id]
        if current.revision != expected_revision:
            raise FirstLiveRevisionConflict(
                f"首轮迭代 revision 冲突：当前 {current.revision}，"
                f"期望 {expected_revision}。"
            )
        return current

    def _save(
        self,
        manifest: FirstLiveIterationManifest,
        *,
        expected_revision: int,
    ) -> FirstLiveIterationManifest:
        current = self._manifests[manifest.iteration_id]
        if current.revision != expected_revision:
            raise FirstLiveRevisionConflict("首轮迭代 CAS 保存失败。")
        if manifest.revision != expected_revision + 1:
            raise FirstLiveRevisionConflict("首轮迭代 revision 必须递增一。")
        self._manifests[manifest.iteration_id] = manifest
        return manifest

    @staticmethod
    def _build_artifact(
        *,
        current: FirstLiveIterationManifest,
        provider_state: ProviderExecutionState,
        completed_case_ids: tuple[str, ...],
        suite_artifact_ref: str | None,
        actual_provider_id: str | None,
        actual_model_id: str | None,
        probe_succeeded: bool,
        fallback_used: bool,
        replay_available: bool,
        usage_available: bool,
        cost_available: bool,
        error_code: str | None,
        failure_record_refs: tuple[str, ...],
        complete: bool,
    ) -> FirstLiveArtifact:
        payload = {
            "iteration_id": current.iteration_id,
            "code_hash": current.code_hash,
            "suite_hash": current.suite_hash,
            "fixture_hash": current.fixture_hash,
            "capability_catalog_hash": current.capability_catalog_hash,
            "selected_case_ids": current.selected_case_ids,
            "completed_case_ids": completed_case_ids,
            "synthetic_qualification_artifact_refs": (
                current.synthetic_qualification_artifact_refs
            ),
            "requested_model_ref": "deepseek-v4-pro",
            "actual_provider_id": actual_provider_id,
            "actual_model_id": actual_model_id,
            "probe_succeeded": probe_succeeded,
            "fallback_used": fallback_used,
            "replay_available": replay_available,
            "usage_available": usage_available,
            "cost_available": cost_available,
            "error_code": error_code,
            "provider_state": provider_state,
            "suite_artifact_ref": suite_artifact_ref,
            "failure_record_refs": failure_record_refs,
            "complete": complete,
        }
        content_hash = canonical_sha256(payload)
        artifact_id = f"first_live_{content_hash}"
        correlation_subject = CorrelationSubjectRef(
            kind=CorrelationSubjectKind.FIRST_LIVE_ARTIFACT,
            stable_id=artifact_id,
        )
        artifact_hash = canonical_sha256(
            {
                **payload,
                "artifact_id": artifact_id,
                "correlation_subject": correlation_subject,
            }
        )
        return FirstLiveArtifact(
            artifact_id=artifact_id,
            correlation_subject=correlation_subject,
            artifact_hash=artifact_hash,
            **payload,
        )
