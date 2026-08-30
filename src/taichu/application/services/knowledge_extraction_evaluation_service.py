"""Knowledge-extraction effect-evaluation application service."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import logging
import re
from secrets import token_hex
from time import monotonic
from typing import Any

from taichu.application.agents.models.agent_run import AgentRun
from taichu.application.contracts.evaluation_dataset_repository import (
    EvaluationDatasetRepository,
)
from taichu.application.contracts.evaluation_judge import EvaluationJudge
from taichu.application.contracts.evaluation_result_repository import (
    EvaluationResultRepository,
)
from taichu.application.contracts.agent_run_repository import AgentRunRepository
from taichu.application.contracts.llm import LLMModelIdentity
from taichu.application.evaluations.knowledge_extraction.dataset import (
    DatasetValidationResult,
    EvaluationDatasetSummary,
    LoadedEvaluationCase,
    LoadedEvaluationDataset,
)
from taichu.application.evaluations.knowledge_extraction.difference_explainer import (
    PROMPT_CONTRACT_ID as DIFFERENCE_EXPLANATION_PROMPT_CONTRACT_ID,
    DifferenceExplanationBatchOutput,
    DifferenceExplanationInput,
    build_difference_explanation_prompt,
    difference_explanation_prompt_contract_hash,
    fallback_difference_explanation,
    validate_difference_explanation_output,
)
from taichu.application.evaluations.knowledge_extraction.judge import (
    PROMPT_CONTRACT_ID,
    JudgeBatchOutput,
    JudgeInputCase,
    JudgeItem,
    JudgeStatus,
    aggregate_judge_samples,
    build_judge_prompt,
    prompt_contract_hash,
    semantic_score,
    should_rejudge,
    validate_judge_output,
)
from taichu.application.evaluations.knowledge_extraction.matcher import (
    match_candidates,
)
from taichu.application.evaluations.knowledge_extraction.metrics import (
    assemble_deterministic_metrics,
    case_scope_matches,
    classify_eligibility,
    compare_source_hashes,
    compare_structured_fields,
    compute_candidate_identification_metrics,
    compute_evidence_metrics_from_spans,
    compute_execution_coverage,
    compute_negative_suppression,
    compute_overall_quality_score,
    compute_schema_compliance_rate,
    final_quality_state,
    semantic_quality_state,
)
from taichu.application.evaluations.knowledge_extraction.models import (
    ActualCandidate,
    CandidateAction,
    EligibilityFacts,
    EligibilityLevel,
    EvaluationEligibility,
    EvaluationLifecycle,
    EvaluationScopeType,
    ExpectedCard,
    ExpectedEvidenceGroup,
    LocatedEvidence,
    OverallScoreInputs,
    QualityState,
    SemanticQualityInputs,
)
from taichu.application.evaluations.knowledge_extraction.profiles import (
    MetricProfile,
    get_metric_profile,
)
from taichu.application.evaluations.knowledge_extraction.records import (
    DifferenceExplanation,
    DifferenceExplanationSource,
    EvaluationComparison,
    EvaluationMode,
    EvaluationNotice,
    EvaluationPhase,
    EvaluationProgress,
    EvaluationRunResult,
    EvaluationStatus,
    IndependenceLevel,
    JudgeCallRecord,
    JudgeSummary,
    KnowledgeEvaluationRecord,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.knowledge_service import (
    merge_knowledge_card_preview,
)


logger = logging.getLogger(__name__)

_RUN_ID_PATTERN = re.compile(r"^extract_run_\d{8}_\d{6}_[a-z0-9]{6}$")
_ACTIVE_STATUSES = {EvaluationStatus.PENDING, EvaluationStatus.RUNNING}
_TERMINAL_STATUSES = {
    EvaluationStatus.COMPLETED,
    EvaluationStatus.COMPLETED_WITH_WARNINGS,
    EvaluationStatus.FAILED,
}
_JUDGE_BATCH_SIZE = 3


class EvaluationServiceError(RuntimeError):
    """Stable application error mapped by the HTTP boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class _PreparedRun:
    run: AgentRun
    case: LoadedEvaluationCase | None
    eligibility: EvaluationEligibility
    actual_candidates: list[ActualCandidate]
    estimated_match_count: int


@dataclass(frozen=True, slots=True)
class _PreparedRequest:
    dataset: LoadedEvaluationDataset
    profile: MetricProfile
    runs: list[_PreparedRun]
    chapters: dict[str, str]
    judge_enabled: bool
    judge_batch_count: int


@dataclass(frozen=True, slots=True)
class _JudgeExecution:
    items: dict[str, JudgeItem]
    call_ids: dict[str, list[str]]
    diagnostics: dict[str, "_JudgeCaseDiagnostic"]
    warnings: list[EvaluationNotice]


@dataclass(frozen=True, slots=True)
class _JudgeCaseDiagnostic:
    """Valid judge samples and total attempts for one matched card."""

    samples: tuple[JudgeItem, ...]
    attempt_count: int


_REASON_MESSAGES = {
    "case_not_found": "任务范围没有匹配的评测样例。",
    "dataset_invalid": "评测集校验未通过。",
    "candidates_unreadable": "历史任务候选结果无法读取。",
    "snapshot_unavailable": "历史任务缺少可冻结的候选快照。",
    "source_hash_mismatch": "任务使用的正文与评测来源不一致。",
    "source_hash_unverified": "旧任务未保存完整正文哈希，仅提供降级诊断。",
    "incomplete_execution": "任务未完整执行，仅提供降级诊断。",
    "unresolved_action": "任务含冲突或建议忽略的候选，仅提供降级诊断。",
    # 兼容已冻结的历史评估快照；新任务中的更新候选可参与完整评估。
    "non_create_action": "任务含非新建候选，仅提供降级诊断。",
}


class KnowledgeExtractionEvaluationService:
    """Freeze, execute, and audit knowledge-extraction evaluations."""

    def __init__(
        self,
        *,
        dataset_repository: EvaluationDatasetRepository,
        result_repository: EvaluationResultRepository,
        run_store: AgentRunRepository,
        chapter_service: ChapterService,
        judge: EvaluationJudge,
        task_factory: Callable[[Awaitable[None]], asyncio.Task[None]] | None = None,
    ) -> None:
        self._datasets = dataset_repository
        self._results = result_repository
        self._runs = run_store
        self._chapters = chapter_service
        self._judge = judge
        self._task_factory = task_factory or asyncio.create_task
        self._tasks: set[asyncio.Task[None]] = set()
        self._watchdog: asyncio.Task[None] | None = None

    async def list_datasets(self) -> list[EvaluationDatasetSummary]:
        return await self._datasets.list_datasets()

    async def get_dataset(self, dataset_id: str) -> EvaluationDatasetSummary:
        summaries = await self._datasets.list_datasets(include_non_confirmed=True)
        for summary in summaries:
            if summary.dataset_id == dataset_id:
                return summary
        validation = await self._datasets.validate_dataset(dataset_id)
        if not validation.valid and any(
            issue.code == "EVALUATION_DATASET_NOT_FOUND" for issue in validation.issues
        ):
            raise EvaluationServiceError(
                "EVALUATION_DATASET_NOT_FOUND",
                "未找到指定评测集。",
            )
        return EvaluationDatasetSummary(
            dataset_id=dataset_id,
            label=dataset_id,
            lifecycle=validation.lifecycle or EvaluationLifecycle.DRAFT,
            case_count=0,
            valid=validation.valid,
            checksum=validation.checksum,
            issues=validation.issues,
        )

    async def validate_dataset(self, dataset_id: str) -> DatasetValidationResult:
        return await self._datasets.validate_dataset(dataset_id)

    async def list_eligible_runs(
        self,
        *,
        dataset_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        dataset = await self._datasets.get_dataset(dataset_id)
        runs, total = await self._runs.list_runs(
            page=page,
            page_size=page_size,
            status="all",
        )
        records, _ = await self._results.list_records(
            page=1,
            page_size=10_000,
            status="all",
        )
        response = []
        for run in runs:
            prepared = self._prepare_run(run, dataset)
            latest = next(
                (record for record in records if run.run_id in record.run_ids),
                None,
            )
            response.append(self._eligible_run_payload(prepared, latest=latest))
        return response, total

    async def preview(
        self,
        *,
        dataset_id: str,
        run_ids: Sequence[str],
        judge_enabled: bool,
        metric_profile_id: str,
    ) -> dict[str, Any]:
        prepared = await self._prepare_request(
            dataset_id=dataset_id,
            run_ids=run_ids,
            judge_enabled=judge_enabled,
            metric_profile_id=metric_profile_id,
        )
        blocking = [
            self._reason_text(item.eligibility)
            for item in prepared.runs
            if item.eligibility.level is EligibilityLevel.INELIGIBLE
        ]
        if judge_enabled and not self._judge.available:
            blocking.append("语义裁判当前不可用，请检查模型配置。")
        warnings = [
            self._reason_text(item.eligibility)
            for item in prepared.runs
            if item.eligibility.level is EligibilityLevel.DIAGNOSTIC
        ]
        preview_runs: list[dict[str, Any]] = []
        for item in prepared.runs:
            full = item.eligibility.level is EligibilityLevel.FULL
            independence = (
                derive_independence(
                    item.run.generation_model_identity,
                    self._judge.model_identity,
                )
                if judge_enabled
                else None
            )
            preview_runs.append(
                {
                    "run_id": item.run.run_id,
                    "case_id": item.case.ref.case_id if item.case else None,
                    "display_title": _display_run_title(item.run),
                    "model_display_name": _display_model_title(item.run),
                    "eligibility_level": item.eligibility.level.value,
                    "reason": self._reason_text(item.eligibility) or None,
                    "generation_model_identity": item.run.generation_model_identity,
                    "independence_level": independence,
                    "expected_card_count": (
                        len(item.case.expected_cards) if item.case else 0
                    ),
                    "estimated_matched_card_count": item.estimated_match_count,
                    "estimated_judge_card_count": (
                        item.estimated_match_count if judge_enabled and full else 0
                    ),
                }
            )
        judge_count = sum(
            item.estimated_match_count
            for item in prepared.runs
            if judge_enabled and item.eligibility.level is EligibilityLevel.FULL
        )
        return {
            "can_create": not blocking,
            "evaluation_mode": (
                EvaluationMode.DETERMINISTIC_AND_JUDGE.value
                if judge_enabled
                else EvaluationMode.DETERMINISTIC_ONLY.value
            ),
            "has_diagnostic_runs": any(
                item.eligibility.level is EligibilityLevel.DIAGNOSTIC
                for item in prepared.runs
            ),
            "dataset": {
                "dataset_id": prepared.dataset.manifest.dataset_id,
                "checksum": prepared.dataset.checksum,
            },
            "runs": preview_runs,
            "judge": {
                "requested": judge_enabled,
                "available": self._judge.available if judge_enabled else None,
                "model_identity": (
                    self._judge.model_identity if judge_enabled else None
                ),
                "unavailable_reason": (
                    "语义裁判当前不可用，请检查模型配置。"
                    if judge_enabled and not self._judge.available
                    else None
                ),
            },
            "estimate": {
                "run_count": len(prepared.runs),
                "expected_card_count": sum(
                    len(item.case.expected_cards) if item.case else 0
                    for item in prepared.runs
                ),
                "matched_card_count": sum(
                    item.estimated_match_count for item in prepared.runs
                ),
                "judge_card_count": judge_count,
                "judge_batch_count": (
                    prepared.judge_batch_count if judge_enabled else 0
                ),
            },
            "warnings": [value for value in warnings if value],
            "blocking_errors": [value for value in blocking if value],
        }

    async def create_evaluation(
        self,
        *,
        dataset_id: str,
        run_ids: Sequence[str],
        judge_enabled: bool,
        metric_profile_id: str,
    ) -> KnowledgeEvaluationRecord:
        prepared = await self._prepare_request(
            dataset_id=dataset_id,
            run_ids=run_ids,
            judge_enabled=judge_enabled,
            metric_profile_id=metric_profile_id,
        )
        self._assert_creatable(prepared)
        snapshot = self._build_snapshot(prepared)
        fingerprint = _request_fingerprint(
            prepared,
            self._judge.model_identity if judge_enabled else None,
        )
        now = _now_iso()
        independence = {
            item.run.run_id: derive_independence(
                item.run.generation_model_identity,
                self._judge.model_identity,
            )
            for item in prepared.runs
            if judge_enabled
        }
        judge_count = sum(
            item.estimated_match_count
            for item in prepared.runs
            if judge_enabled and item.eligibility.level is EligibilityLevel.FULL
        )
        record = KnowledgeEvaluationRecord(
            evaluation_id=_evaluation_id(),
            request_fingerprint=fingerprint,
            evaluation_mode=(
                EvaluationMode.DETERMINISTIC_AND_JUDGE
                if judge_enabled
                else EvaluationMode.DETERMINISTIC_ONLY
            ),
            dataset_id=prepared.dataset.manifest.dataset_id,
            dataset_label=prepared.dataset.manifest.label,
            dataset_checksum=prepared.dataset.checksum,
            subject_title=_display_run_title(prepared.runs[0].run),
            metric_profile_id=prepared.profile.metric_profile_id,
            judge=JudgeSummary(
                enabled=judge_enabled,
                model_identity=(self._judge.model_identity if judge_enabled else None),
                self_judge=(
                    any(
                        value is IndependenceLevel.SAME_MODEL
                        for value in independence.values()
                    )
                    if judge_enabled
                    else None
                ),
                independence_by_run=independence,
            ),
            progress=EvaluationProgress(
                run_total=len(prepared.runs),
                judge_card_total=judge_count,
                judge_batch_total=(prepared.judge_batch_count if judge_enabled else 0),
            ),
            run_ids=[item.run.run_id for item in prepared.runs],
            created_at=now,
            updated_at=now,
            heartbeat_at=now,
        )
        published = await self._results.publish_pending(record, snapshot)
        try:
            self._register(published.evaluation_id)
        except Exception:
            await self._results.discard_unstarted(published.evaluation_id)
            raise
        return published

    async def list_evaluations(
        self,
        *,
        page: int,
        page_size: int,
        status: str,
    ) -> tuple[list[KnowledgeEvaluationRecord], int]:
        allowed = {"all", *(item.value for item in EvaluationStatus)}
        if status not in allowed:
            raise EvaluationServiceError(
                "EVALUATION_INVALID_TRANSITION",
                "评估状态筛选条件不正确。",
            )
        records, total = await self._results.list_records(
            page=page,
            page_size=page_size,
            status=status,
        )
        return [await self._with_display_titles(record) for record in records], total

    async def get_evaluation(self, evaluation_id: str) -> KnowledgeEvaluationRecord:
        record = await self._results.get_record(evaluation_id)
        if record is None or record.lifecycle is EvaluationLifecycle.REJECTED:
            raise EvaluationServiceError(
                "EVALUATION_NOT_FOUND",
                "未找到指定评估记录。",
            )
        return await self._with_display_titles(record)

    async def list_comparisons(
        self,
        evaluation_id: str,
        *,
        page: int,
        page_size: int,
        run_id: str | None,
        knowledge_type: str | None,
        issue_type: str | None,
    ) -> tuple[list[EvaluationComparison], int]:
        record = await self.get_evaluation(evaluation_id)
        comparisons: list[EvaluationComparison] = []
        for summary in record.run_results:
            result = await self._results.get_run_result(evaluation_id, summary.run_id)
            source = result or summary
            comparisons.extend(source.comparisons)
        judge_call_cache: dict[str, JudgeCallRecord | None] = {}
        visible_comparisons: list[EvaluationComparison] = []
        for comparison in comparisons:
            comparison = await self._hydrate_legacy_judge_result(
                evaluation_id,
                comparison,
                judge_call_cache,
            )
            normalized_issue_type = _comparison_issue_type(comparison)
            if normalized_issue_type is None:
                continue
            normalized = comparison.model_copy(
                update={"issue_type": normalized_issue_type}
            )
            visible_comparisons.append(
                normalized.model_copy(
                    update={
                        "explanation": normalized.explanation
                        or fallback_difference_explanation(normalized)
                    }
                )
            )
        comparisons = visible_comparisons
        if run_id:
            comparisons = [item for item in comparisons if item.run_id == run_id]
        if knowledge_type:
            comparisons = [
                item for item in comparisons if item.knowledge_type == knowledge_type
            ]
        if issue_type and issue_type != "all":
            comparisons = [
                item for item in comparisons if item.issue_type == issue_type
            ]
        total = len(comparisons)
        start = (page - 1) * page_size
        titles = await self._run_title_map(record.run_ids)
        return [
            item.model_copy(
                update={
                    "task_title": item.task_title
                    or titles.get(item.run_id, "未命名章节")
                }
            )
            for item in comparisons[start : start + page_size]
        ], total

    async def _hydrate_legacy_judge_result(
        self,
        evaluation_id: str,
        comparison: EvaluationComparison,
        call_cache: dict[str, JudgeCallRecord | None],
    ) -> EvaluationComparison:
        """Recover accurate judge diagnostics for historical disagreement rows."""
        judge_result = comparison.judge_result or {}
        if (
            judge_result.get("status") != "disagreement"
            or "valid_result_count" in judge_result
        ):
            return comparison

        call_ids = [
            value
            for value in judge_result.get("judge_call_ids", [])
            if isinstance(value, str) and value
        ]
        calls: list[JudgeCallRecord] = []
        for call_id in call_ids:
            if call_id not in call_cache:
                call_cache[call_id] = await self._results.get_judge_call(
                    evaluation_id,
                    call_id,
                )
            call = call_cache[call_id]
            if call is not None:
                calls.append(call)

        recovered = _legacy_judge_diagnostics(comparison, calls, len(call_ids))
        return comparison.model_copy(update={"judge_result": recovered})

    async def get_judge_call(
        self,
        evaluation_id: str,
        call_id: str,
    ) -> JudgeCallRecord:
        await self.get_evaluation(evaluation_id)
        call = await self._results.get_judge_call(evaluation_id, call_id)
        if call is None:
            raise EvaluationServiceError(
                "EVALUATION_NOT_FOUND",
                "未找到指定裁判调用记录。",
            )
        return call

    async def retry_evaluation(
        self,
        evaluation_id: str,
    ) -> KnowledgeEvaluationRecord:
        parent = await self.get_evaluation(evaluation_id)
        if parent.lifecycle is EvaluationLifecycle.REJECTED or parent.status not in {
            EvaluationStatus.FAILED,
            EvaluationStatus.COMPLETED_WITH_WARNINGS,
        }:
            raise EvaluationServiceError(
                "EVALUATION_INVALID_TRANSITION",
                "当前评估状态不允许重试。",
            )
        snapshot = await self._results.read_snapshot_files(evaluation_id)
        try:
            frozen_contract = json.loads(
                snapshot["judge_contract.json"].decode("utf-8")
            )
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvaluationServiceError(
                "EVALUATION_SNAPSHOT_CORRUPTED",
                "评估快照损坏，无法继续执行。",
            ) from error
        current_contract = _judge_contract_payload(
            enabled=parent.judge.enabled,
            model_identity=(
                self._judge.model_identity if parent.judge.enabled else None
            ),
        )
        if (
            frozen_contract.get("prompt_contract_id") != PROMPT_CONTRACT_ID
            or frozen_contract.get("prompt_hash") != current_contract["prompt_hash"]
        ):
            raise EvaluationServiceError(
                "EVALUATION_JUDGE_UNAVAILABLE",
                "当前裁判 Prompt 契约与原快照不一致，无法按原快照重试。",
            )
        if parent.judge.enabled:
            if not self._judge.available:
                raise EvaluationServiceError(
                    "EVALUATION_JUDGE_UNAVAILABLE",
                    "语义裁判当前不可用。",
                )
            frozen_identity = frozen_contract.get("judge_model_identity")
            if (
                self._judge.model_identity != parent.judge.model_identity
                or frozen_identity != self._judge.model_identity.model_dump(mode="json")
            ):
                raise EvaluationServiceError(
                    "EVALUATION_JUDGE_UNAVAILABLE",
                    "当前裁判模型与原快照不一致，无法按原快照重试。",
                )
        fingerprint = _hash_json(
            {
                "kind": "retry",
                "parent_evaluation_id": evaluation_id,
                "snapshot_root_hash": parent.snapshot_root_hash,
                "judge_model_identity": (
                    parent.judge.model_identity.model_dump(mode="json")
                    if parent.judge.model_identity
                    else None
                ),
                "prompt_contract_id": PROMPT_CONTRACT_ID,
                "prompt_hash": frozen_contract["prompt_hash"],
            }
        )
        now = _now_iso()
        record = KnowledgeEvaluationRecord(
            evaluation_id=_evaluation_id(),
            parent_evaluation_id=evaluation_id,
            request_fingerprint=fingerprint,
            evaluation_mode=parent.evaluation_mode,
            dataset_id=parent.dataset_id,
            dataset_label=parent.dataset_label,
            dataset_checksum=parent.dataset_checksum,
            metric_profile_id=parent.metric_profile_id,
            judge=parent.judge,
            progress=EvaluationProgress(
                run_total=parent.progress.run_total,
                judge_card_total=parent.progress.judge_card_total,
                judge_batch_total=parent.progress.judge_batch_total,
            ),
            run_ids=parent.run_ids,
            created_at=now,
            updated_at=now,
            heartbeat_at=now,
        )
        published = await self._results.publish_pending(record, snapshot)
        try:
            self._register(published.evaluation_id)
        except Exception:
            await self._results.discard_unstarted(published.evaluation_id)
            raise
        return published

    async def confirm_evaluation(
        self,
        evaluation_id: str,
    ) -> KnowledgeEvaluationRecord:
        record = await self.get_evaluation(evaluation_id)
        if record.lifecycle is not EvaluationLifecycle.DRAFT or record.status not in {
            EvaluationStatus.COMPLETED,
            EvaluationStatus.COMPLETED_WITH_WARNINGS,
        }:
            raise EvaluationServiceError(
                "EVALUATION_INVALID_TRANSITION",
                "当前评估状态不允许确认。",
            )
        return await self._results.mutate_record(
            evaluation_id,
            {"lifecycle": EvaluationLifecycle.CONFIRMED, "updated_at": _now_iso()},
            expected_status=record.status.value,
        )

    async def reject_evaluation(self, evaluation_id: str) -> None:
        record = await self.get_evaluation(evaluation_id)
        if record.status not in _TERMINAL_STATUSES or record.lifecycle not in {
            EvaluationLifecycle.DRAFT,
            EvaluationLifecycle.CONFIRMED,
        }:
            raise EvaluationServiceError(
                "EVALUATION_INVALID_TRANSITION",
                "当前评估状态不允许废弃。",
            )
        await self._results.mutate_record(
            evaluation_id,
            {"lifecycle": EvaluationLifecycle.REJECTED, "updated_at": _now_iso()},
            expected_status=record.status.value,
        )

    async def recover_interrupted(self) -> None:
        """Fail active records left by a previous single-process server."""
        for status in (EvaluationStatus.PENDING, EvaluationStatus.RUNNING):
            records, _ = await self._results.list_records(
                page=1,
                page_size=10_000,
                status=status.value,
            )
            for record in records:
                await self._mark_interrupted(record)

    def start_watchdog(self) -> None:
        if self._watchdog is None or self._watchdog.done():
            self._watchdog = self._task_factory(self._watchdog_loop())

    async def shutdown(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            await asyncio.gather(self._watchdog, return_exceptions=True)
            self._watchdog = None
        active = list(self._tasks)
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)

    async def _prepare_request(
        self,
        *,
        dataset_id: str,
        run_ids: Sequence[str],
        judge_enabled: bool,
        metric_profile_id: str,
    ) -> _PreparedRequest:
        unique_ids = list(dict.fromkeys(run_ids))
        if len(unique_ids) != 1:
            raise EvaluationServiceError(
                "EVALUATION_CANDIDATE_SNAPSHOT_MISSING",
                "每次请选择一个历史任务。",
            )
        if len(unique_ids) != len(run_ids):
            raise EvaluationServiceError(
                "EVALUATION_CANDIDATE_SNAPSHOT_MISSING",
                "所选历史任务不能重复。",
            )
        try:
            profile = get_metric_profile(metric_profile_id)
        except ValueError as error:
            raise EvaluationServiceError(
                "EVALUATION_DATASET_INVALID",
                "评分参数方案不受支持。",
            ) from error
        dataset = await self._datasets.get_dataset(dataset_id)
        selected: list[_PreparedRun] = []
        for run_id in unique_ids:
            _validate_run_id(run_id)
            run = await self._runs.get_run(run_id)
            if run is None:
                raise EvaluationServiceError(
                    "EVALUATION_RUN_NOT_FOUND",
                    "未找到指定历史任务。",
                )
            selected.append(self._prepare_run(run, dataset))
        chapter_ids = sorted(
            {
                chapter_id
                for item in selected
                if item.case
                for chapter_id in item.case.ref.chapter_ids
            }
        )
        chapters: dict[str, str] = {}
        for chapter_id in chapter_ids:
            try:
                content = await self._chapters.read_chapter(chapter_id)
            except LookupError as error:
                raise EvaluationServiceError(
                    "EVALUATION_SOURCE_CHANGED",
                    "评测所需正文无法读取。",
                ) from error
            chapters[chapter_id] = content.markdown
        for item in selected:
            if item.case is None:
                continue
            for (
                chapter_id,
                expected_hash,
            ) in item.case.ref.source_chapter_hashes.items():
                markdown = chapters.get(chapter_id)
                if (
                    markdown is None
                    or sha256(markdown.encode("utf-8")).hexdigest() != expected_hash
                ):
                    raise EvaluationServiceError(
                        "EVALUATION_SOURCE_CHANGED",
                        "任务使用的正文与评测来源不一致。",
                    )
        batch_count = _judge_batch_count(selected) if judge_enabled else 0
        return _PreparedRequest(
            dataset=dataset,
            profile=profile,
            runs=selected,
            chapters=chapters,
            judge_enabled=judge_enabled,
            judge_batch_count=batch_count,
        )

    def _prepare_run(
        self,
        run: AgentRun,
        dataset: LoadedEvaluationDataset,
    ) -> _PreparedRun:
        scope_type, chapter_ids = _run_scope(run)
        case = next(
            (
                value
                for value in dataset.cases.values()
                if case_scope_matches(
                    value.ref,
                    scope_type=scope_type,
                    chapter_ids=chapter_ids,
                )
            ),
            None,
        )
        actual = _actual_candidates(run)
        expected_ids = case.ref.chapter_ids if case else chapter_ids
        coverage = (
            compute_execution_coverage(
                scope_type=scope_type,
                run_status=run.status.value,
                expected_chapter_ids=expected_ids,
                batch_chapter_statuses={
                    item.chapter_id: item.status.value
                    for item in run.batch_chapter_progress
                },
                failed_chapter_count=run.failed_chapter_count,
            )
            if expected_ids
            else 0.0
        )
        actual_hashes = _run_source_hashes(run)
        source_match = (
            compare_source_hashes(case.ref.source_chapter_hashes, actual_hashes)
            if case
            else None
        )
        candidates_readable = all(
            bool(item.suggested_card) and isinstance(item.suggested_card, dict)
            for item in run.review_items
        )
        eligibility = classify_eligibility(
            EligibilityFacts(
                has_matching_case=case is not None,
                dataset_valid=True,
                candidates_readable=candidates_readable,
                snapshot_available=candidates_readable,
                source_hash_matches=source_match,
                execution_coverage=coverage,
                candidate_actions=[item.candidate_action for item in actual],
            )
        )
        try:
            match_count = (
                len(
                    match_candidates(
                        actual,
                        case.expected_cards,
                        case.source_evidence,
                    ).matches
                )
                if case and candidates_readable
                else 0
            )
        except ValueError:
            candidates_readable = False
            eligibility = classify_eligibility(
                EligibilityFacts(
                    has_matching_case=case is not None,
                    dataset_valid=True,
                    candidates_readable=False,
                    snapshot_available=False,
                    source_hash_matches=source_match,
                    execution_coverage=coverage,
                    candidate_actions=[item.candidate_action for item in actual],
                )
            )
            match_count = 0
        return _PreparedRun(
            run=run,
            case=case,
            eligibility=eligibility,
            actual_candidates=actual,
            estimated_match_count=match_count,
        )

    def _assert_creatable(self, prepared: _PreparedRequest) -> None:
        if prepared.judge_enabled and not self._judge.available:
            raise EvaluationServiceError(
                "EVALUATION_JUDGE_UNAVAILABLE",
                "语义裁判当前不可用。",
            )
        for item in prepared.runs:
            if item.eligibility.level is not EligibilityLevel.INELIGIBLE:
                continue
            reasons = {reason.value for reason in item.eligibility.reasons}
            if "source_hash_mismatch" in reasons:
                code = "EVALUATION_SOURCE_CHANGED"
                message = "任务使用的正文与评测来源不一致。"
            elif "case_not_found" in reasons:
                code = "EVALUATION_SCOPE_MISMATCH"
                message = "所选任务与评测范围不匹配。"
            else:
                code = "EVALUATION_CANDIDATE_SNAPSHOT_MISSING"
                message = "历史任务缺少可冻结的候选结果。"
            raise EvaluationServiceError(code, message)

    def _build_snapshot(self, prepared: _PreparedRequest) -> dict[str, bytes]:
        files = {
            "dataset_manifest.json": _json_bytes(prepared.dataset.manifest),
            "metric_profile.json": _json_bytes(prepared.profile),
            "judge_contract.json": _json_bytes(
                _judge_contract_payload(
                    enabled=prepared.judge_enabled,
                    model_identity=(
                        self._judge.model_identity if prepared.judge_enabled else None
                    ),
                )
            ),
            "evaluation_schema.json": _json_bytes(
                {
                    "expected_card": ExpectedCard.model_json_schema(),
                    "actual_candidate": ActualCandidate.model_json_schema(),
                }
            ),
            "request.json": _json_bytes(
                {
                    "dataset_id": prepared.dataset.manifest.dataset_id,
                    "dataset_checksum": prepared.dataset.checksum,
                    "metric_profile_id": prepared.profile.metric_profile_id,
                    "judge_enabled": prepared.judge_enabled,
                    "run_case_ids": {
                        item.run.run_id: item.case.ref.case_id
                        for item in prepared.runs
                        if item.case
                    },
                    "eligibility": {
                        item.run.run_id: item.eligibility.model_dump(mode="json")
                        for item in prepared.runs
                    },
                }
            ),
        }
        for item in prepared.runs:
            files[f"runs/{item.run.run_id}.json"] = _json_bytes(item.run)
            if item.case:
                files[f"cases/{item.case.ref.case_id}.json"] = _json_bytes(item.case)
        for chapter_id, markdown in prepared.chapters.items():
            files[f"chapters/{chapter_id}.md"] = markdown.encode("utf-8")
        return files

    def _register(self, evaluation_id: str) -> None:
        task = self._task_factory(self._run_background(evaluation_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_background(self, evaluation_id: str) -> None:
        token = token_hex(12)
        heartbeat: asyncio.Task[None] | None = None
        try:
            record = await self._results.get_record(evaluation_id)
            if record is None:
                return
            now = _now_iso()
            record = await self._results.mutate_record(
                evaluation_id,
                {
                    "status": EvaluationStatus.RUNNING,
                    "phase": EvaluationPhase.DETERMINISTIC,
                    "started_at": now,
                    "updated_at": now,
                    "heartbeat_at": now,
                    "execution_token": token,
                },
                expected_status=EvaluationStatus.PENDING.value,
            )
            heartbeat = self._task_factory(self._heartbeat(evaluation_id, token))
            snapshot = await self._results.read_snapshot_files(evaluation_id)
            frozen = _decode_snapshot(snapshot)
            run_results: list[EvaluationRunResult] = []
            judged: _JudgeExecution | None = None
            judge_inputs: list[tuple[JudgeInputCase, str, IndependenceLevel]] = []
            warnings: list[EvaluationNotice] = []
            for run in frozen.runs:
                result, inputs = _evaluate_deterministic_run(
                    run=run,
                    case=frozen.case_by_run[run.run_id],
                    eligibility=frozen.eligibility[run.run_id],
                    chapters=frozen.chapters,
                    profile=frozen.profile,
                )
                await self._results.write_run_result(evaluation_id, result)
                run_results.append(result)
                judge_inputs.extend(
                    (
                        item,
                        run.run_id,
                        derive_independence(
                            run.generation_model_identity,
                            self._judge.model_identity,
                        ),
                    )
                    for item in inputs
                    if record.judge.enabled
                    and result.eligibility_level == EligibilityLevel.FULL.value
                )
                if result.eligibility_level == EligibilityLevel.DIAGNOSTIC.value:
                    warnings.extend(result.warnings)
                progress = record.progress.model_copy(
                    update={"run_completed": len(run_results)}
                )
                record = await self._results.mutate_record(
                    evaluation_id,
                    {
                        "run_results": _summary_run_results(run_results),
                        "progress": progress,
                        "warnings": warnings,
                        "updated_at": _now_iso(),
                    },
                    expected_status=EvaluationStatus.RUNNING.value,
                    expected_execution_token=token,
                )
            if record.judge.enabled:
                record = await self._results.mutate_record(
                    evaluation_id,
                    {
                        "phase": EvaluationPhase.JUDGING,
                        "updated_at": _now_iso(),
                    },
                    expected_status=EvaluationStatus.RUNNING.value,
                    expected_execution_token=token,
                )
                judged = await self._execute_judge(
                    record,
                    token,
                    judge_inputs,
                )
                warnings.extend(judged.warnings)
                run_results = _apply_judge_results(
                    run_results,
                    judged,
                    frozen.profile,
                    record.judge,
                )
                for result in run_results:
                    await self._results.write_run_result(evaluation_id, result)
                record = await self._results.mutate_record(
                    evaluation_id,
                    {
                        "phase": EvaluationPhase.EXPLAINING,
                        "updated_at": _now_iso(),
                    },
                    expected_status=EvaluationStatus.RUNNING.value,
                    expected_execution_token=token,
                )
            run_results, explanation_warnings = await self._attach_explanations(
                record,
                run_results,
                judged,
                use_model=record.judge.enabled,
            )
            warnings.extend(explanation_warnings)
            for result in run_results:
                await self._results.write_run_result(evaluation_id, result)
            record = await self._results.mutate_record(
                evaluation_id,
                {
                    "phase": EvaluationPhase.AGGREGATING,
                    "run_results": _summary_run_results(run_results),
                    "warnings": warnings,
                    "updated_at": _now_iso(),
                },
                expected_status=EvaluationStatus.RUNNING.value,
                expected_execution_token=token,
            )
            aggregate = _aggregate_metrics(run_results)
            terminal = (
                EvaluationStatus.COMPLETED_WITH_WARNINGS
                if warnings
                else EvaluationStatus.COMPLETED
            )
            now = _now_iso()
            await self._results.mutate_record(
                evaluation_id,
                {
                    "status": terminal,
                    "phase": EvaluationPhase.FINISHED,
                    "run_results": _summary_run_results(run_results),
                    "aggregate_metrics": aggregate,
                    "warnings": warnings,
                    "updated_at": now,
                    "heartbeat_at": now,
                    "finished_at": now,
                    "execution_token": None,
                },
                expected_status=EvaluationStatus.RUNNING.value,
                expected_execution_token=token,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception(
                "Knowledge-extraction evaluation background execution failed",
                extra={"evaluation_id": evaluation_id},
            )
            await self._fail_background(evaluation_id, token, error)
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

    async def _execute_judge(
        self,
        record: KnowledgeEvaluationRecord,
        token: str,
        inputs: list[tuple[JudgeInputCase, str, IndependenceLevel]],
    ) -> _JudgeExecution:
        items: dict[str, JudgeItem] = {}
        call_ids: dict[str, list[str]] = defaultdict(list)
        diagnostics: dict[str, _JudgeCaseDiagnostic] = {}
        warnings: list[EvaluationNotice] = []
        grouped: dict[
            tuple[str, str],
            list[tuple[JudgeInputCase, str, IndependenceLevel]],
        ] = defaultdict(list)
        generation_identity = {
            item.run_id: _hash_json(
                item.generation_model_identity.model_dump(mode="json")
            )
            for item in record.run_results
        }
        for value in inputs:
            case, run_id, _ = value
            grouped[
                (case.knowledge_type, generation_identity.get(run_id, run_id))
            ].append(value)
        completed = 0
        batch_completed = 0

        async def persist_progress() -> None:
            nonlocal record
            progress = record.progress.model_copy(
                update={
                    "judge_card_completed": completed,
                    "judge_batch_completed": batch_completed,
                }
            )
            record = await self._results.mutate_record(
                record.evaluation_id,
                {"progress": progress, "updated_at": _now_iso()},
                expected_status=EvaluationStatus.RUNNING.value,
                expected_execution_token=token,
            )

        async def process_case(
            case: JudgeInputCase,
            independence: IndependenceLevel,
            sample: JudgeItem | None,
            initial_call_ids: list[str],
            initial_error: str | None,
        ) -> None:
            nonlocal completed
            samples = [sample] if sample else []
            call_ids[case.case_id].extend(initial_call_ids)
            if initial_error:
                warnings.append(
                    EvaluationNotice(
                        code="EVALUATION_JUDGE_INVALID_OUTPUT",
                        message=(
                            f"语义裁判未纳入本次评分：{initial_error}已保留确定性结果。"
                        ),
                        run_id=case.run_id,
                    )
                )
            rejudge_required = sample is not None and should_rejudge(sample)
            if rejudge_required:
                for _ in range(2):
                    repeated, repeated_ids, repeated_error = await self._judge_once(
                        record,
                        [case],
                        independence,
                    )
                    call_ids[case.case_id].extend(repeated_ids.get(case.case_id, []))
                    if not repeated_error and case.case_id in repeated:
                        samples.append(repeated[case.case_id])
            aggregated = (
                None
                if rejudge_required and len(samples) < 2
                else aggregate_judge_samples(samples)
            )
            diagnostics[case.case_id] = _JudgeCaseDiagnostic(
                samples=tuple(samples),
                attempt_count=len(call_ids[case.case_id]),
            )
            if aggregated is not None:
                items[case.case_id] = aggregated
                if aggregated.status is not JudgeStatus.SCORED:
                    warnings.append(
                        EvaluationNotice(
                            code="EVALUATION_JUDGE_INCOMPLETE",
                            message="语义裁判缺少足够证据，已保留确定性结果。",
                            run_id=case.run_id,
                        )
                    )
            elif len(samples) >= 2:
                warnings.append(
                    EvaluationNotice(
                        code="EVALUATION_JUDGE_DISAGREEMENT",
                        message="多次有效语义裁判的评分未满足一致性要求。",
                        run_id=case.run_id,
                    )
                )
            elif len(samples) == 1:
                warnings.append(
                    EvaluationNotice(
                        code="EVALUATION_JUDGE_INCONCLUSIVE",
                        message="有效语义裁判结果不足，已保留确定性结果。",
                        run_id=case.run_id,
                    )
                )
            completed += 1
            await persist_progress()

        for values in grouped.values():
            for offset in range(0, len(values), _JUDGE_BATCH_SIZE):
                batch = values[offset : offset + _JUDGE_BATCH_SIZE]
                first, ids, error = await self._judge_once(
                    record,
                    [item[0] for item in batch],
                    batch[0][2],
                )
                if error and len(batch) > 1:
                    for case, _, independence in batch:
                        prior_ids = ids.get(case.case_id, [])
                        single, single_ids, single_error = await self._judge_once(
                            record,
                            [case],
                            independence,
                            retry_of=prior_ids[-1] if prior_ids else None,
                        )
                        await process_case(
                            case,
                            independence,
                            single.get(case.case_id),
                            [
                                *ids.get(case.case_id, []),
                                *single_ids.get(case.case_id, []),
                            ],
                            single_error,
                        )
                else:
                    for case, _, independence in batch:
                        await process_case(
                            case,
                            independence,
                            first.get(case.case_id),
                            ids.get(case.case_id, []),
                            error,
                        )
                batch_completed += 1
                await persist_progress()
        return _JudgeExecution(
            dict(items),
            dict(call_ids),
            diagnostics,
            warnings,
        )

    async def _judge_once(
        self,
        record: KnowledgeEvaluationRecord,
        cases: list[JudgeInputCase],
        independence: IndependenceLevel,
        *,
        retry_of: str | None = None,
    ) -> tuple[dict[str, JudgeItem], dict[str, list[str]], str | None]:
        prompt = build_judge_prompt(cases)
        call_id = f"judge_call_{token_hex(6)}"
        started_at = _now_iso()
        started = monotonic()
        raw: str | None = None
        parsed: dict[str, Any] | None = None
        error_code: str | None = None
        error_message: str | None = None
        result: dict[str, JudgeItem] = {}
        token_usage: dict[str, int] | None = None
        try:
            response = await asyncio.wait_for(
                self._judge.complete(
                    prompt,
                    output_schema=JudgeBatchOutput,
                ),
                timeout=120,
            )
            raw = response.raw_response
            token_usage = response.token_usage
            if not isinstance(response.output, JudgeBatchOutput):
                raise TypeError("语义裁判返回了错误的结构化输出类型。")
            output = validate_judge_output(response.output, cases)
            parsed = output.model_dump(mode="json")
            result = {item.case_id: item for item in output.items}
        except Exception as error:  # noqa: BLE001
            error_code = _judge_failure_code(error)
            error_message = _judge_failure_message(error, error_code=error_code)
        finished_at = _now_iso()
        call = JudgeCallRecord(
            call_id=call_id,
            evaluation_id=record.evaluation_id,
            run_ids=sorted({item.run_id for item in cases}),
            judge_model_identity=self._judge.model_identity,
            independence_level=independence,
            self_judge=independence is IndependenceLevel.SAME_MODEL,
            prompt_contract_id=PROMPT_CONTRACT_ID,
            prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
            input_snapshot_hash=_hash_json(
                [item.model_dump(mode="json") for item in cases]
            ),
            input_prompt=prompt,
            raw_response=raw,
            parsed_output=parsed,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=int((monotonic() - started) * 1000),
            retry_of=retry_of,
            error_code=error_code,
            error=error_message,
            token_usage=token_usage,
        )
        await self._results.write_judge_call(call)
        ids = {case.case_id: [call_id] for case in cases}
        return result, ids, error_message

    async def _attach_explanations(
        self,
        record: KnowledgeEvaluationRecord,
        run_results: list[EvaluationRunResult],
        judged: _JudgeExecution | None,
        *,
        use_model: bool,
    ) -> tuple[list[EvaluationRunResult], list[EvaluationNotice]]:
        """Attach model summaries, with rule summaries as an auditable fallback."""
        cases_by_run: dict[str, list[DifferenceExplanationInput]] = defaultdict(list)
        locations: dict[str, tuple[int, int]] = {}
        updated_runs: list[EvaluationRunResult] = []
        diagnostics = judged.diagnostics if judged is not None else {}

        for run_index, run in enumerate(run_results):
            comparisons: list[EvaluationComparison] = []
            for comparison_index, comparison in enumerate(run.comparisons):
                issue_type = _comparison_issue_type(comparison)
                if issue_type is None:
                    comparisons.append(comparison)
                    continue
                normalized = comparison.model_copy(update={"issue_type": issue_type})
                explanation_id = _difference_explanation_id(
                    normalized,
                    comparison_index,
                )
                judge_key = _comparison_judge_key(normalized)
                diagnostic = diagnostics.get(judge_key) if judge_key else None
                case = DifferenceExplanationInput(
                    explanation_id=explanation_id,
                    run_id=run.run_id,
                    task_title=normalized.task_title or run.display_title,
                    knowledge_type=normalized.knowledge_type,
                    issue_type=normalized.issue_type,
                    display_title=_comparison_display_title(normalized),
                    match_kind=normalized.match_kind,
                    expected_card=normalized.expected_card,
                    actual_card=normalized.actual_card,
                    field_diffs=normalized.field_diffs,
                    judge_result=normalized.judge_result,
                    valid_judge_samples=(
                        [
                            sample.model_dump(mode="json")
                            for sample in diagnostic.samples
                        ]
                        if diagnostic is not None
                        else []
                    ),
                )
                normalized = normalized.model_copy(
                    update={"explanation": fallback_difference_explanation(normalized)}
                )
                locations[explanation_id] = (run_index, len(comparisons))
                cases_by_run[run.run_id].append(case)
                comparisons.append(normalized)
            updated_runs.append(run.model_copy(update={"comparisons": comparisons}))

        if not use_model or not locations:
            return updated_runs, []

        explanations: dict[str, DifferenceExplanation] = {}
        fallback_counts: dict[str, int] = defaultdict(int)
        for run_id, cases in cases_by_run.items():
            independence = record.judge.independence_by_run.get(
                run_id,
                IndependenceLevel.UNKNOWN,
            )
            for offset in range(0, len(cases), 5):
                batch = cases[offset : offset + 5]
                result, call_id, error = await self._explain_once(
                    record,
                    batch,
                    independence,
                )
                if error and len(batch) > 1:
                    result = {}
                    for case in batch:
                        single, single_call_id, single_error = await self._explain_once(
                            record,
                            [case],
                            independence,
                        )
                        if single_error:
                            fallback_counts[run_id] += 1
                            continue
                        explanations.update(
                            {
                                key: DifferenceExplanation(
                                    summary=value,
                                    source=DifferenceExplanationSource.MODEL,
                                    call_id=single_call_id,
                                )
                                for key, value in single.items()
                            }
                        )
                    continue
                if error:
                    fallback_counts[run_id] += len(batch)
                    continue
                explanations.update(
                    {
                        key: DifferenceExplanation(
                            summary=value,
                            source=DifferenceExplanationSource.MODEL,
                            call_id=call_id,
                        )
                        for key, value in result.items()
                    }
                )

        mutable_comparisons = [list(run.comparisons) for run in updated_runs]
        for explanation_id, explanation in explanations.items():
            location = locations.get(explanation_id)
            if location is None:
                continue
            run_index, comparison_index = location
            comparison = mutable_comparisons[run_index][comparison_index]
            mutable_comparisons[run_index][comparison_index] = comparison.model_copy(
                update={"explanation": explanation}
            )
        final_runs = [
            run.model_copy(update={"comparisons": mutable_comparisons[index]})
            for index, run in enumerate(updated_runs)
        ]
        warnings = [
            EvaluationNotice(
                code="EVALUATION_EXPLANATION_FALLBACK",
                message=(
                    f"{count} 项差异未获得模型总结，已改用规则说明，不影响评估分数。"
                ),
                run_id=run_id,
            )
            for run_id, count in fallback_counts.items()
            if count
        ]
        return final_runs, warnings

    async def _explain_once(
        self,
        record: KnowledgeEvaluationRecord,
        cases: list[DifferenceExplanationInput],
        independence: IndependenceLevel,
    ) -> tuple[dict[str, str], str, str | None]:
        """Execute and persist one strict difference-explanation request."""
        prompt = build_difference_explanation_prompt(cases)
        call_id = f"judge_call_{token_hex(6)}"
        started_at = _now_iso()
        started = monotonic()
        raw: str | None = None
        parsed: dict[str, Any] | None = None
        error_message: str | None = None
        result: dict[str, str] = {}
        token_usage: dict[str, int] | None = None
        try:
            response = await asyncio.wait_for(
                self._judge.complete(
                    prompt,
                    output_schema=DifferenceExplanationBatchOutput,
                ),
                timeout=120,
            )
            raw = response.raw_response
            token_usage = response.token_usage
            if not isinstance(response.output, DifferenceExplanationBatchOutput):
                raise TypeError("差异说明返回了错误的结构化输出类型。")
            output = validate_difference_explanation_output(response.output, cases)
            parsed = output.model_dump(mode="json")
            result = {item.explanation_id: item.summary for item in output.items}
        except Exception as error:  # noqa: BLE001
            error_message = _difference_explanation_failure_message(error)
        finished_at = _now_iso()
        await self._results.write_judge_call(
            JudgeCallRecord(
                call_id=call_id,
                evaluation_id=record.evaluation_id,
                run_ids=sorted({item.run_id for item in cases}),
                judge_model_identity=self._judge.model_identity,
                independence_level=independence,
                self_judge=independence is IndependenceLevel.SAME_MODEL,
                prompt_contract_id=DIFFERENCE_EXPLANATION_PROMPT_CONTRACT_ID,
                prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                input_snapshot_hash=_hash_json(
                    [item.model_dump(mode="json") for item in cases]
                ),
                input_prompt=prompt,
                raw_response=raw,
                parsed_output=parsed,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=int((monotonic() - started) * 1000),
                error=error_message,
                token_usage=token_usage,
            )
        )
        return result, call_id, error_message

    async def _heartbeat(self, evaluation_id: str, token: str) -> None:
        while True:
            await asyncio.sleep(15)
            try:
                await self._results.mutate_record(
                    evaluation_id,
                    {"heartbeat_at": _now_iso()},
                    expected_status=EvaluationStatus.RUNNING.value,
                    expected_execution_token=token,
                )
            except Exception:
                return

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            now = datetime.now(UTC)
            for status, timeout_seconds in (
                (EvaluationStatus.PENDING, 60),
                (EvaluationStatus.RUNNING, 90),
            ):
                records, _ = await self._results.list_records(
                    page=1,
                    page_size=10_000,
                    status=status.value,
                )
                for record in records:
                    heartbeat = _parse_iso(record.heartbeat_at)
                    if (now - heartbeat).total_seconds() > timeout_seconds:
                        await self._mark_interrupted(record)

    async def _mark_interrupted(self, record: KnowledgeEvaluationRecord) -> None:
        now = _now_iso()
        try:
            await self._results.mutate_record(
                record.evaluation_id,
                {
                    "status": EvaluationStatus.FAILED,
                    "phase": EvaluationPhase.FINISHED,
                    "error_code": "EVALUATION_PROCESS_INTERRUPTED",
                    "error_message": "评估进程已中断，可基于原快照重试。",
                    "updated_at": now,
                    "heartbeat_at": now,
                    "finished_at": now,
                    "execution_token": None,
                },
                expected_status=record.status.value,
                expected_execution_token=(
                    record.execution_token
                    if record.status is EvaluationStatus.RUNNING
                    else None
                ),
            )
        except Exception:
            return

    async def _fail_background(
        self,
        evaluation_id: str,
        token: str,
        error: Exception,
    ) -> None:
        now = _now_iso()
        error_code, error_message = _background_failure(error)
        try:
            await self._results.mutate_record(
                evaluation_id,
                {
                    "status": EvaluationStatus.FAILED,
                    "phase": EvaluationPhase.FINISHED,
                    "error_code": error_code,
                    "error_message": error_message,
                    "updated_at": now,
                    "heartbeat_at": now,
                    "finished_at": now,
                    "execution_token": None,
                },
                expected_status=EvaluationStatus.RUNNING.value,
                expected_execution_token=token,
            )
        except Exception:
            return

    def _eligible_run_payload(
        self,
        item: _PreparedRun,
        *,
        latest: KnowledgeEvaluationRecord | None,
    ) -> dict[str, Any]:
        run = item.run
        latest_payload = None
        if latest:
            run_result = next(
                (value for value in latest.run_results if value.run_id == run.run_id),
                None,
            )
            latest_payload = {
                "evaluation_id": latest.evaluation_id,
                "status": latest.status.value,
                "lifecycle": latest.lifecycle.value,
                "overall_quality_score": (
                    run_result.overall_quality_score if run_result else None
                ),
                "final_quality_state": (
                    run_result.final_quality_state.value if run_result else None
                ),
            }
        return {
            "run_id": run.run_id,
            "case_id": item.case.ref.case_id if item.case else None,
            "display_title": _display_run_title(run),
            "model_display_name": _display_model_title(run),
            "status": run.status.value,
            "scope_type": run.scope.scope_type,
            "chapter_id": run.scope.chapter_id or None,
            "chapter_title": run.scope.chapter_title or None,
            "chapter_ids": run.scope.chapter_ids,
            "chapter_titles": run.scope.chapter_titles,
            "total_chapter_count": run.total_chapter_count,
            "started_at": run.started_at,
            "requested_model_name": run.requested_model_name,
            "model_name": run.model_name,
            "generation_model_identity": run.generation_model_identity,
            "prompt_version": run.prompt_version,
            "schema_version": run.schema_version,
            "eligibility_level": item.eligibility.level.value,
            "reason": self._reason_text(item.eligibility) or None,
            "suggested_card_available": all(
                bool(value.suggested_card) for value in run.review_items
            ),
            "latest_evaluation": latest_payload,
        }

    async def _run_title_map(self, run_ids: Sequence[str]) -> dict[str, str]:
        titles: dict[str, str] = {}
        for run_id in run_ids:
            run = await self._runs.get_run(run_id)
            if run is not None:
                titles[run_id] = _display_run_title(run)
        return titles

    async def _with_display_titles(
        self,
        record: KnowledgeEvaluationRecord,
    ) -> KnowledgeEvaluationRecord:
        titles = await self._run_title_map(record.run_ids)
        run_results = [
            result.model_copy(
                update={
                    "display_title": result.display_title
                    or titles.get(result.run_id, "未命名章节"),
                    "comparisons": [
                        comparison.model_copy(
                            update={
                                "task_title": comparison.task_title
                                or titles.get(comparison.run_id, "未命名章节")
                            }
                        )
                        for comparison in result.comparisons
                    ],
                }
            )
            for result in record.run_results
        ]
        subject_title = record.subject_title or titles.get(
            record.run_ids[0], "未命名章节"
        )
        return record.model_copy(
            update={"subject_title": subject_title, "run_results": run_results}
        )

    @staticmethod
    def _reason_text(eligibility: EvaluationEligibility) -> str:
        return "；".join(
            _REASON_MESSAGES[reason.value] for reason in eligibility.reasons
        )


@dataclass(frozen=True, slots=True)
class _FrozenEvaluation:
    profile: MetricProfile
    runs: list[AgentRun]
    case_by_run: dict[str, LoadedEvaluationCase]
    eligibility: dict[str, EvaluationEligibility]
    chapters: dict[str, str]


def _decode_snapshot(files: dict[str, bytes]) -> _FrozenEvaluation:
    request = json.loads(files["request.json"].decode("utf-8"))
    profile = MetricProfile.model_validate_json(files["metric_profile.json"])
    run_case_ids = request["run_case_ids"]
    runs: list[AgentRun] = []
    cases: dict[str, LoadedEvaluationCase] = {}
    eligibility: dict[str, EvaluationEligibility] = {}
    for run_id, case_id in run_case_ids.items():
        runs.append(AgentRun.model_validate_json(files[f"runs/{run_id}.json"]))
        cases[run_id] = LoadedEvaluationCase.model_validate_json(
            files[f"cases/{case_id}.json"]
        )
        eligibility[run_id] = EvaluationEligibility.model_validate(
            request["eligibility"][run_id]
        )
    chapters = {
        path.removeprefix("chapters/").removesuffix(".md"): value.decode("utf-8")
        for path, value in files.items()
        if path.startswith("chapters/") and path.endswith(".md")
    }
    return _FrozenEvaluation(profile, runs, cases, eligibility, chapters)


def _evaluate_deterministic_run(
    *,
    run: AgentRun,
    case: LoadedEvaluationCase,
    eligibility: EvaluationEligibility,
    chapters: dict[str, str],
    profile: MetricProfile,
) -> tuple[EvaluationRunResult, list[JudgeInputCase]]:
    actual = _actual_candidates(run)
    matches = match_candidates(actual, case.expected_cards, case.source_evidence)
    candidate_metrics = compute_candidate_identification_metrics(matches)
    structured = compare_structured_fields(
        matches,
        actual,
        case.expected_cards,
        case.rules,
    )
    expected_by_id = {item.expected_card_id: item for item in case.expected_cards}
    quote_by_id = {item.quote_id: item for item in case.source_evidence}
    located: list[LocatedEvidence] = []
    expected_groups: list[ExpectedEvidenceGroup] = []
    for candidate in actual:
        for index, excerpt in enumerate(candidate.evidence_excerpts):
            location = _locate_excerpt(excerpt, case.ref.chapter_ids, chapters)
            located.append(
                LocatedEvidence(
                    evidence_id=f"{candidate.actual_candidate_id}:{index}",
                    **location,
                )
            )
    for match in matches.matches:
        expected = expected_by_id[match.expected_card_id]
        quotes = [
            quote_by_id[quote_id]
            for quote_id in expected.source_quote_ids
            if quote_id in quote_by_id
        ]
        if quotes:
            expected_groups.append(
                ExpectedEvidenceGroup(group_id=expected.expected_card_id, quotes=quotes)
            )
    evidence = compute_evidence_metrics_from_spans(
        matched_card_count=len(matches.matches),
        actual_evidence=located,
        expected_groups=expected_groups,
    )
    negative = compute_negative_suppression(actual, case.negative_cases)
    schema = compute_schema_compliance_rate(
        passed_count=sum(1 for item in actual if item.schema_valid),
        total_count=len(actual),
    )
    deterministic = assemble_deterministic_metrics(
        candidate_metrics=candidate_metrics,
        structured_metrics=structured,
        evidence_metrics=evidence,
        negative_metrics=negative,
        schema_compliance_rate=schema,
        execution_coverage=eligibility.execution_coverage or 0,
        profile=profile,
    )
    comparisons = _build_comparisons(
        run.run_id,
        case.ref.case_id,
        _display_run_title(run),
        matches,
        actual,
        case.expected_cards,
        structured.diffs,
    )
    warnings = [
        EvaluationNotice(
            code=f"EVALUATION_{reason.value.upper()}",
            message=_REASON_MESSAGES[reason.value],
            run_id=run.run_id,
        )
        for reason in eligibility.reasons
    ]
    metrics = deterministic.model_dump(mode="json")
    metrics.update(
        {
            "candidate_precision_micro": candidate_metrics.micro.precision,
            "candidate_recall_micro": candidate_metrics.micro.recall,
            "candidate_f1_micro": candidate_metrics.micro.f1,
            "candidate_f1_macro": candidate_metrics.macro_f1,
            "structured_field_score": structured.score,
            "evidence_score": evidence.score,
            "evidence_grounded_precision": evidence.grounded_precision,
            "expected_evidence_recall": evidence.expected_recall,
            "negative_suppression_score": negative.score,
            "execution_coverage": eligibility.execution_coverage,
            "schema_compliance_rate": schema,
            "ambiguous_count": candidate_metrics.ambiguous_count,
            "candidate_true_positive_count": (
                candidate_metrics.micro.true_positive_count
            ),
            "candidate_false_positive_count": (
                candidate_metrics.micro.false_positive_count
            ),
            "candidate_false_negative_count": (
                candidate_metrics.micro.false_negative_count
            ),
        }
    )
    result = EvaluationRunResult(
        run_id=run.run_id,
        case_id=case.ref.case_id,
        display_title=_display_run_title(run),
        eligibility_level=eligibility.level.value,
        eligibility_reasons=[reason.value for reason in eligibility.reasons],
        generation_model_identity=run.generation_model_identity,
        expected_card_count=len(case.expected_cards),
        actual_card_count=len(actual),
        metrics=metrics,
        final_quality_state=QualityState.NOT_COMPARABLE,
        comparisons=comparisons,
        warnings=warnings,
    )
    judge_inputs = _build_judge_inputs(
        run,
        case,
        matches,
        actual,
        structured.diffs,
        chapters,
    )
    return result, judge_inputs


def _build_comparisons(
    run_id: str,
    case_id: str,
    task_title: str,
    matches: Any,
    actual: list[ActualCandidate],
    expected: list[Any],
    diffs: list[Any],
) -> list[EvaluationComparison]:
    actual_by_id = {item.actual_candidate_id: item for item in actual}
    expected_by_id = {item.expected_card_id: item for item in expected}
    result: list[EvaluationComparison] = []
    for match in matches.matches:
        actual_card = actual_by_id[match.actual_candidate_id]
        expected_card = expected_by_id[match.expected_card_id]
        field_diffs = [
            item.model_dump(mode="json")
            for item in diffs
            if item.actual_candidate_id == match.actual_candidate_id
            and item.comparable
            and item.score is not None
            and item.score < 1
        ]
        result.append(
            EvaluationComparison(
                run_id=run_id,
                case_id=case_id,
                task_title=task_title,
                knowledge_type=match.knowledge_type.value,
                issue_type="field_difference" if field_diffs else "matched",
                expected_card_id=match.expected_card_id,
                actual_candidate_id=match.actual_candidate_id,
                expected_card=expected_card.card,
                actual_card=actual_card.card,
                match_kind=match.kind.value,
                field_diffs=field_diffs,
            )
        )
    for item in matches.false_positives:
        candidate = actual_by_id[item.card_id]
        result.append(
            EvaluationComparison(
                run_id=run_id,
                case_id=case_id,
                task_title=task_title,
                knowledge_type=item.knowledge_type.value,
                issue_type="extra_candidate",
                actual_candidate_id=item.card_id,
                actual_card=candidate.card,
            )
        )
    for item in matches.false_negatives:
        card = expected_by_id[item.card_id]
        result.append(
            EvaluationComparison(
                run_id=run_id,
                case_id=case_id,
                task_title=task_title,
                knowledge_type=item.knowledge_type.value,
                issue_type="missing_candidate",
                expected_card_id=item.card_id,
                expected_card=card.card,
            )
        )
    for ambiguity in matches.ambiguities:
        expected_candidates = [
            {
                "card_id": item.card_id,
                "name": item.name,
            }
            for item in ambiguity.expected_cards
        ]
        actual_candidates = [
            {
                "card_id": item.card_id,
                "name": item.name,
            }
            for item in ambiguity.actual_candidates
        ]
        result.append(
            EvaluationComparison(
                run_id=run_id,
                case_id=case_id,
                task_title=task_title,
                knowledge_type=ambiguity.knowledge_type.value,
                issue_type="ambiguous_match",
                expected_card={
                    "name": "、".join(item["name"] for item in expected_candidates),
                    "candidates": expected_candidates,
                },
                actual_card={
                    "name": "、".join(item["name"] for item in actual_candidates),
                    "candidates": actual_candidates,
                },
                match_kind="ambiguous_match",
                judge_result={
                    "status": "ambiguous_match",
                    "reason": (
                        "存在多个可能的一对一对应，已从漏提取和多提取计数中"
                        "排除，需要人工复核。"
                    ),
                },
            )
        )
    return result


def _build_judge_inputs(
    run: AgentRun,
    case: LoadedEvaluationCase,
    matches: Any,
    actual: list[ActualCandidate],
    diffs: list[Any],
    chapters: dict[str, str],
) -> list[JudgeInputCase]:
    actual_by_id = {item.actual_candidate_id: item for item in actual}
    expected_by_id = {item.expected_card_id: item for item in case.expected_cards}
    quote_by_id = {item.quote_id: item for item in case.source_evidence}
    result: list[JudgeInputCase] = []
    for match in matches.matches:
        actual_card = actual_by_id[match.actual_candidate_id]
        expected_card = expected_by_id[match.expected_card_id]
        quote_ids = list(
            dict.fromkeys(
                [
                    *expected_card.source_quote_ids,
                    *[
                        quote_id
                        for claim in expected_card.expected_claims
                        for quote_id in claim.source_quote_ids
                    ],
                ]
            )
        )[:10]
        located_actual_evidence = []
        for excerpt in actual_card.evidence_excerpts:
            location = _locate_excerpt(excerpt, case.ref.chapter_ids, chapters)
            if location:
                located_actual_evidence.append({"text": excerpt[:350], **location})
        result.append(
            JudgeInputCase(
                case_id=(
                    f"{run.run_id}::{actual_card.actual_candidate_id}::"
                    f"{expected_card.expected_card_id}"
                ),
                run_id=run.run_id,
                expected_card_id=expected_card.expected_card_id,
                actual_review_item_id=actual_card.actual_candidate_id,
                knowledge_type=expected_card.knowledge_type.value,
                expected_fields={
                    field: expected_card.card.get(field)
                    for field in expected_card.semantic_fields
                    if field != "appearance_chapter_count"
                },
                actual_fields={
                    field: actual_card.card.get(field)
                    for field in expected_card.semantic_fields
                    if field != "appearance_chapter_count"
                },
                expected_claims=[
                    item.model_dump(mode="json")
                    for item in expected_card.expected_claims
                ],
                source_quotes=[
                    {
                        **quote_by_id[quote_id].model_dump(mode="json"),
                        "text": quote_by_id[quote_id].text[:350],
                    }
                    for quote_id in quote_ids
                    if quote_id in quote_by_id
                ],
                deterministic_diff={
                    "field_diffs": [
                        item.model_dump(mode="json")
                        for item in diffs
                        if item.actual_candidate_id == match.actual_candidate_id
                    ],
                    "located_actual_evidence": located_actual_evidence,
                },
            )
        )
    return result


def _apply_judge_results(
    run_results: list[EvaluationRunResult],
    judged: _JudgeExecution,
    profile: MetricProfile,
    judge_summary: JudgeSummary,
) -> list[EvaluationRunResult]:
    output: list[EvaluationRunResult] = []
    for run in run_results:
        if run.eligibility_level != EligibilityLevel.FULL.value:
            output.append(run)
            continue
        scores: list[float] = []
        scored_count = 0
        critical = False
        critical_claim_missing = False
        reference_conflict = False
        disagreement = False
        comparisons: list[EvaluationComparison] = []
        for comparison in run.comparisons:
            if not comparison.expected_card_id or not comparison.actual_candidate_id:
                comparisons.append(comparison)
                continue
            key = (
                f"{run.run_id}::{comparison.actual_candidate_id}::"
                f"{comparison.expected_card_id}"
            )
            item = judged.items.get(key)
            if item is None:
                call_ids = judged.call_ids.get(key, [])
                diagnostic = judged.diagnostics.get(key)
                valid_count = len(diagnostic.samples) if diagnostic else 0
                attempt_count = (
                    diagnostic.attempt_count if diagnostic else len(call_ids)
                )
                if valid_count >= 2:
                    judge_status = "disagreement"
                    issue_type = "judge_disagreement"
                    reason = "多次有效裁判的评分未满足一致性要求，语义结果未计入评分。"
                    disagreement = True
                elif valid_count == 1:
                    judge_status = "inconclusive"
                    issue_type = "judge_inconclusive"
                    reason = (
                        "只获得一份有效裁判结果，不足以形成稳健结论，已保留确定性结果。"
                    )
                else:
                    judge_status = "failed"
                    issue_type = "judge_failed"
                    reason = (
                        "语义裁判调用均未成功，无法形成语义结论；这不代表抽取错误。"
                    )
                comparisons.append(
                    comparison.model_copy(
                        update={
                            "issue_type": issue_type,
                            "judge_result": {
                                "status": judge_status,
                                "reason": reason,
                                "judge_call_ids": call_ids,
                                "attempt_count": attempt_count,
                                "valid_result_count": valid_count,
                            },
                        }
                    )
                )
                continue
            score = semantic_score(item)
            if score is not None:
                scores.append(score)
                scored_count += 1
            critical = critical or bool(item.critical_flags)
            critical_claim_missing = critical_claim_missing or any(
                finding.severity == "critical"
                and finding.kind
                in {"omission", "missing_claim", "missing_critical_claim"}
                for finding in item.findings
            )
            reference_conflict = (
                reference_conflict or item.status is JudgeStatus.REFERENCE_CONFLICT
            )
            updated_comparison = comparison.model_copy(
                update={
                    "judge_result": {
                        **item.model_dump(mode="json"),
                        "judge_call_ids": judged.call_ids.get(key, []),
                        "attempt_count": (
                            judged.diagnostics[key].attempt_count
                            if key in judged.diagnostics
                            else len(judged.call_ids.get(key, []))
                        ),
                        "valid_result_count": (
                            len(judged.diagnostics[key].samples)
                            if key in judged.diagnostics
                            else 1
                        ),
                        "semantic_score": score,
                    }
                }
            )
            comparisons.append(
                updated_comparison.model_copy(
                    update={
                        "issue_type": (
                            _comparison_issue_type(updated_comparison) or "matched"
                        )
                    }
                )
            )
        total = sum(
            1
            for item in run.comparisons
            if item.expected_card_id and item.actual_candidate_id
        )
        semantic = sum(scores) / len(scores) if scores else None
        coverage = scored_count / total if total else None
        independence = judge_summary.independence_by_run.get(
            run.run_id,
            IndependenceLevel.UNKNOWN,
        )
        semantic_state = semantic_quality_state(
            SemanticQualityInputs(
                semantic_score=semantic,
                judge_coverage=coverage,
                critical_claims_covered=(
                    coverage == 1 and not critical_claim_missing
                    if coverage is not None
                    else None
                ),
                confirmed_hard_risk=critical,
                self_judge=independence is IndependenceLevel.SAME_MODEL,
                unknown_model_independence=independence is IndependenceLevel.UNKNOWN,
                reference_conflict=reference_conflict,
                judge_disagreement=disagreement,
                has_formal_critical_flag=critical,
            ),
            profile,
        )
        deterministic_state = QualityState(run.metrics["deterministic_quality_state"])
        overall = compute_overall_quality_score(
            OverallScoreInputs(
                candidate_f1_micro=run.metrics.get("candidate_f1_micro"),
                structured_field_score=run.metrics.get("structured_field_score"),
                semantic_score=semantic,
                evidence_score=run.metrics.get("evidence_score"),
                negative_suppression_score=run.metrics.get(
                    "negative_suppression_score"
                ),
                judge_coverage=coverage,
                critical_claims_covered=(coverage == 1 and not critical_claim_missing),
                unresolved_critical_disagreement=disagreement,
            ),
            profile,
        )
        final_state = final_quality_state(
            eligibility_level=EligibilityLevel.FULL,
            deterministic_state=deterministic_state,
            semantic_state=semantic_state,
            confirmed_hard_risk=critical,
            reference_conflict=reference_conflict,
        )
        metrics = dict(run.metrics)
        metrics.update(
            {
                "semantic_score": semantic,
                "judge_coverage": coverage,
                "overall_quality_score": overall,
                "critical_flag_count": sum(
                    len(item.critical_flags)
                    for case_id, item in judged.items.items()
                    if case_id.startswith(f"{run.run_id}::")
                ),
                "final_quality_state": final_state.value,
            }
        )
        output.append(
            run.model_copy(
                update={
                    "metrics": metrics,
                    "semantic_score": semantic,
                    "judge_coverage": coverage,
                    "overall_quality_score": overall,
                    "final_quality_state": final_state,
                    "comparisons": comparisons,
                }
            )
        )
    return output


def _comparison_issue_type(comparison: EvaluationComparison) -> str | None:
    """Classify one comparison for the author-facing difference list."""
    if comparison.issue_type in {
        "missing_candidate",
        "extra_candidate",
        "ambiguous_match",
    }:
        return comparison.issue_type

    judge_result = comparison.judge_result or {}
    judge_status = str(judge_result.get("status") or "")
    if judge_status in {"reference_conflict", "disagreement"}:
        return "judge_disagreement"
    if judge_status == "inconclusive":
        return "judge_inconclusive"
    if judge_status == "failed":
        return "judge_failed"
    if judge_status == "insufficient_evidence":
        return "evidence_issue"

    dimensions = judge_result.get("dimensions")
    if isinstance(dimensions, dict):
        evidence_dimension = dimensions.get("evidence_grounding")
        if _judge_dimension_has_issue(evidence_dimension):
            return "evidence_issue"

    missing_quote_ids = judge_result.get("missing_quote_ids")
    if isinstance(missing_quote_ids, list) and missing_quote_ids:
        return "evidence_issue"

    findings = judge_result.get("findings")
    if isinstance(findings, list):
        if any(_is_evidence_finding(finding) for finding in findings):
            return "evidence_issue"
        if findings:
            return "semantic_issue"

    critical_flags = judge_result.get("critical_flags")
    if isinstance(critical_flags, list) and critical_flags:
        return "semantic_issue"
    if isinstance(dimensions, dict) and any(
        _judge_dimension_has_issue(dimension) for dimension in dimensions.values()
    ):
        return "semantic_issue"

    if comparison.field_diffs:
        return "field_difference"
    if comparison.issue_type in {
        "semantic_issue",
        "evidence_issue",
        "judge_disagreement",
        "judge_inconclusive",
        "judge_failed",
    }:
        return comparison.issue_type
    return None


def _legacy_judge_diagnostics(
    comparison: EvaluationComparison,
    calls: list[JudgeCallRecord],
    attempt_count: int,
) -> dict[str, Any]:
    """Classify a historical generic disagreement from its persisted calls."""
    judge_result = comparison.judge_result or {}
    valid_result_count = sum(
        1 for call in calls if _judge_call_contains_comparison(call, comparison)
    )
    if valid_result_count >= 2:
        status = "disagreement"
        reason = "多次有效裁判的评分未满足一致性要求，语义结果未计入评分。"
    elif valid_result_count == 1:
        status = "inconclusive"
        reason = "只获得一份有效裁判结果，不足以形成稳健结论，已保留确定性结果。"
    else:
        status = "failed"
        reason = "语义裁判调用均未成功，无法形成语义结论；这不代表抽取错误。"
    return {
        **judge_result,
        "status": status,
        "reason": reason,
        "attempt_count": attempt_count,
        "valid_result_count": valid_result_count,
    }


def _judge_call_contains_comparison(
    call: JudgeCallRecord,
    comparison: EvaluationComparison,
) -> bool:
    if call.prompt_contract_id != PROMPT_CONTRACT_ID:
        return False
    items = (call.parsed_output or {}).get("items")
    if not isinstance(items, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("expected_card_id") == comparison.expected_card_id
        and item.get("actual_review_item_id") == comparison.actual_candidate_id
        for item in items
    )


def _judge_dimension_has_issue(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    score = value.get("score")
    return isinstance(score, (int, float)) and not isinstance(score, bool) and score < 4


def _is_evidence_finding(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    marker = " ".join(str(value.get(key) or "").casefold() for key in ("kind", "field"))
    return any(
        keyword in marker
        for keyword in ("evidence", "grounding", "quote", "citation", "source")
    )


def _aggregate_metrics(run_results: list[EvaluationRunResult]) -> dict[str, Any]:
    full = [
        item
        for item in run_results
        if item.eligibility_level == EligibilityLevel.FULL.value
    ]
    if not full:
        return {
            "overall_quality_score": None,
            "final_quality_state": QualityState.NOT_COMPARABLE.value,
        }
    keys = (
        "candidate_precision_micro",
        "candidate_recall_micro",
        "candidate_f1_micro",
        "candidate_f1_macro",
        "structured_field_score",
        "evidence_score",
        "evidence_grounded_precision",
        "expected_evidence_recall",
        "negative_suppression_score",
        "schema_compliance_rate",
        "execution_coverage",
    )
    aggregate: dict[str, Any] = {}
    for key in keys:
        values = [item.metrics.get(key) for item in full]
        numeric = [value for value in values if isinstance(value, (int, float))]
        aggregate[key] = sum(numeric) / len(numeric) if numeric else None
    overall = [
        item.overall_quality_score
        for item in full
        if item.overall_quality_score is not None
    ]
    semantic = [item.semantic_score for item in full if item.semantic_score is not None]
    coverage = [item.judge_coverage for item in full if item.judge_coverage is not None]
    aggregate["overall_quality_score"] = (
        sum(overall) / len(overall) if len(overall) == len(full) else None
    )
    aggregate["semantic_score"] = sum(semantic) / len(semantic) if semantic else None
    aggregate["judge_coverage"] = sum(coverage) / len(coverage) if coverage else None
    ranks = {
        QualityState.HIGH_RISK: 0,
        QualityState.NEEDS_REVIEW: 1,
        QualityState.USABLE: 2,
        QualityState.STABLE: 3,
        QualityState.NOT_COMPARABLE: -1,
    }
    aggregate["final_quality_state"] = min(
        (item.final_quality_state for item in full),
        key=lambda value: ranks[value],
    ).value
    return aggregate


def _actual_candidates(run: AgentRun) -> list[ActualCandidate]:
    result: list[ActualCandidate] = []
    existing_by_target = {
        str(candidate.get("target_card_id") or ""): existing
        for candidate in run.typed_candidates
        if isinstance(candidate, dict)
        and str(candidate.get("target_card_id") or "").strip()
        and isinstance((existing := candidate.get("_existing_card")), dict)
    }
    for item in run.review_items:
        excerpts: list[str] = []
        if item.source_excerpt.strip():
            excerpts.append(item.source_excerpt.strip())
        value = item.suggested_card.get("evidence_excerpt")
        if isinstance(value, str) and value.strip():
            excerpts.append(value.strip())
        values = item.suggested_card.get("evidence_excerpts")
        if isinstance(values, list):
            excerpts.extend(
                value.strip()
                for value in values
                if isinstance(value, str) and value.strip()
            )
        card = dict(item.suggested_card)
        merge_preview_applied = False
        if (
            item.candidate_action.value == CandidateAction.UPDATE_CARD.value
            and item.target_card_id
            and item.target_card_id in existing_by_target
        ):
            card = merge_knowledge_card_preview(
                item.knowledge_type,
                existing_by_target[item.target_card_id],
                card,
                merge_mode="merge",
            )
            merge_preview_applied = True
        result.append(
            ActualCandidate(
                actual_candidate_id=item.review_item_id,
                knowledge_type=item.knowledge_type,
                candidate_action=CandidateAction(item.candidate_action.value),
                card=card,
                schema_valid=item.schema_validation.passed,
                evidence_excerpts=list(dict.fromkeys(excerpts)),
                merge_preview_applied=merge_preview_applied,
            )
        )
    return result


def _run_scope(run: AgentRun) -> tuple[EvaluationScopeType, list[str]]:
    scope = run.scope
    if scope.scope_type == EvaluationScopeType.CHAPTER_BATCH.value:
        return EvaluationScopeType.CHAPTER_BATCH, list(scope.chapter_ids)
    chapter_ids = list(scope.chapter_ids) or (
        [scope.chapter_id] if scope.chapter_id else []
    )
    if len(chapter_ids) > 1:
        return EvaluationScopeType.CHAPTER_BATCH, chapter_ids
    return EvaluationScopeType.CHAPTER, chapter_ids


def _display_run_title(run: AgentRun) -> str:
    """Return the stable author-facing name for a frozen task run."""

    scope_type, _ = _run_scope(run)
    titles = [
        title.strip()
        for title in (run.scope.chapter_titles or [run.scope.chapter_title])
        if title and title.strip()
    ]
    if scope_type is EvaluationScopeType.CHAPTER:
        return titles[0] if titles else "未命名章节"
    if not titles:
        return "历史批量任务"
    count = run.total_chapter_count or len(titles)
    if len(titles) == 1:
        return f"批量知识沉淀：{titles[0]}"
    return f"批量知识沉淀：{titles[0]} 至 {titles[-1]}（共 {count} 章）"


def _display_model_title(run: AgentRun) -> str:
    if not run.generation_model_identity.known:
        return "模型信息未记录"
    model_id = run.generation_model_identity.model_id
    labels = {
        "deepseek-v4-pro": "DeepSeek V4 Pro",
        "deepseek-chat": "DeepSeek Chat",
        "deepseek-reasoner": "DeepSeek Reasoner",
    }
    known_label = labels.get(model_id or "")
    if known_label:
        return known_label

    internal_names = {
        value.strip().casefold()
        for value in (
            model_id,
            run.model_id,
            run.requested_model_name,
            run.upstream_model,
        )
        if value and value.strip()
    }
    for value in (run.model_display_name, run.model_name):
        display_name = value.strip()
        if display_name and display_name.casefold() not in internal_names:
            return display_name
    return "模型信息未记录"


def _run_source_hashes(run: AgentRun) -> dict[str, str] | None:
    if run.scope.chapter_content_hashes:
        return run.scope.chapter_content_hashes
    if run.scope.chapter_id and run.scope.content_hash:
        return {run.scope.chapter_id: run.scope.content_hash}
    return None


def _locate_excerpt(
    excerpt: str,
    chapter_ids: Sequence[str],
    chapters: dict[str, str],
) -> dict[str, Any]:
    for chapter_id in chapter_ids:
        markdown = chapters.get(chapter_id, "")
        start = markdown.find(excerpt)
        if start >= 0:
            return {
                "chapter_id": chapter_id,
                "start_offset": start,
                "end_offset": start + len(excerpt),
            }
    return {}


def _judge_batch_count(runs: Sequence[_PreparedRun]) -> int:
    groups: dict[tuple[str, str], int] = defaultdict(int)
    for item in runs:
        if item.eligibility.level is not EligibilityLevel.FULL or not item.case:
            continue
        matches = match_candidates(
            item.actual_candidates,
            item.case.expected_cards,
            item.case.source_evidence,
        )
        for match in matches.matches:
            identity = _hash_json(
                item.run.generation_model_identity.model_dump(mode="json")
            )
            groups[(match.knowledge_type.value, identity)] += 1
    return sum(
        (count + _JUDGE_BATCH_SIZE - 1) // _JUDGE_BATCH_SIZE
        for count in groups.values()
    )


def derive_independence(
    generation: LLMModelIdentity,
    judge: LLMModelIdentity,
) -> IndependenceLevel:
    if not generation.known or not judge.known:
        return IndependenceLevel.UNKNOWN
    if generation.provider == judge.provider and generation.model_id == judge.model_id:
        return IndependenceLevel.SAME_MODEL
    if (
        generation.provider == judge.provider
        and generation.family
        and generation.family == judge.family
    ):
        return IndependenceLevel.SAME_PROVIDER_FAMILY
    return IndependenceLevel.DIFFERENT_MODEL


def _summary_run_results(
    results: Sequence[EvaluationRunResult],
) -> list[EvaluationRunResult]:
    """Keep summary.json compact; full comparisons live in runs/*.json."""
    metric_keys = {
        "candidate_precision_micro",
        "candidate_recall_micro",
        "candidate_f1_micro",
        "candidate_f1_macro",
        "candidate_true_positive_count",
        "candidate_false_positive_count",
        "candidate_false_negative_count",
        "structured_field_score",
        "semantic_score",
        "evidence_score",
        "evidence_grounded_precision",
        "expected_evidence_recall",
        "negative_suppression_score",
        "judge_coverage",
        "execution_coverage",
        "schema_compliance_rate",
        "critical_flag_count",
        "ambiguous_count",
        "overall_quality_score",
        "final_quality_state",
    }
    return [
        item.model_copy(
            update={
                "metrics": {
                    key: value
                    for key, value in item.metrics.items()
                    if key in metric_keys
                },
                "comparisons": [],
            }
        )
        for item in results
    ]


def _judge_contract_payload(
    *,
    enabled: bool,
    model_identity: LLMModelIdentity | None,
) -> dict[str, Any]:
    """Freeze the actual prompt builder and strict output contract."""
    return {
        "enabled": enabled,
        "prompt_contract_id": PROMPT_CONTRACT_ID,
        "prompt_builder": (
            "taichu.application.evaluations.knowledge_extraction.judge."
            "build_judge_prompt"
        ),
        "prompt_hash": prompt_contract_hash(),
        "output_schema": JudgeBatchOutput.model_json_schema(),
        "difference_explanation": {
            "prompt_contract_id": DIFFERENCE_EXPLANATION_PROMPT_CONTRACT_ID,
            "prompt_builder": (
                "taichu.application.evaluations.knowledge_extraction."
                "difference_explainer.build_difference_explanation_prompt"
            ),
            "prompt_hash": difference_explanation_prompt_contract_hash(),
            "output_schema": DifferenceExplanationBatchOutput.model_json_schema(),
        },
        "judge_model_identity": (
            model_identity.model_dump(mode="json") if model_identity else None
        ),
    }


def _request_fingerprint(
    prepared: _PreparedRequest,
    judge_identity: LLMModelIdentity | None,
) -> str:
    return _hash_json(
        {
            "dataset_checksum": prepared.dataset.checksum,
            "run_ids": sorted(item.run.run_id for item in prepared.runs),
            "judge_enabled": prepared.judge_enabled,
            "metric_profile": prepared.profile.model_dump(mode="json"),
            "judge_identity": (
                judge_identity.model_dump(mode="json") if judge_identity else None
            ),
        }
    )


def _evaluation_id() -> str:
    now = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"knowledge_eval_{now}_{token_hex(3)}"


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise EvaluationServiceError(
            "EVALUATION_ID_INVALID",
            "历史任务标识格式不正确。",
        )


def _json_bytes(value: Any) -> bytes:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _hash_json(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _comparison_judge_key(comparison: EvaluationComparison) -> str | None:
    if not comparison.expected_card_id or not comparison.actual_candidate_id:
        return None
    return (
        f"{comparison.run_id}::{comparison.actual_candidate_id}::"
        f"{comparison.expected_card_id}"
    )


def _comparison_display_title(comparison: EvaluationComparison) -> str:
    for card in (comparison.expected_card, comparison.actual_card):
        name = (card or {}).get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "未命名知识卡"


def _difference_explanation_id(
    comparison: EvaluationComparison,
    comparison_index: int,
) -> str:
    return (
        "difference_"
        + _hash_json(
            {
                "run_id": comparison.run_id,
                "expected_card_id": comparison.expected_card_id,
                "actual_candidate_id": comparison.actual_candidate_id,
                "knowledge_type": comparison.knowledge_type,
                "issue_type": comparison.issue_type,
                "comparison_index": comparison_index,
            }
        )[:16]
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _background_failure(error: Exception) -> tuple[str, str]:
    """Classify background failures without misreporting every defect as corruption."""
    if getattr(error, "code", None) == "EVALUATION_SNAPSHOT_CORRUPTED":
        return (
            "EVALUATION_SNAPSHOT_CORRUPTED",
            "评估冻结快照或中间结果已损坏，无法可靠读取。",
        )
    return (
        "EVALUATION_EXECUTION_FAILED",
        "评估后台执行失败，已保留当前进度与审计结果，可在排查后重试。",
    )


def _judge_failure_code(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "judge_timeout"
    if isinstance(error, json.JSONDecodeError):
        return "judge_protocol_invalid_json"
    detail = str(error).casefold()
    if "json" in detail and any(
        marker in detail for marker in ("decode", "解析", "parse", "expecting")
    ):
        return "judge_protocol_invalid_json"
    if any(
        marker in detail
        for marker in (
            "validation error",
            "expected_card_id",
            "actual_review_item_id",
            "dimensions",
            "confidence",
        )
    ):
        return "judge_protocol_invalid_schema"
    return "judge_provider_error"


def _judge_failure_message(
    error: Exception,
    *,
    error_code: str | None = None,
) -> str:
    """Convert strict judge-contract failures into an author-readable diagnosis."""
    code = error_code or _judge_failure_code(error)
    if code == "judge_timeout":
        return "语义裁判调用超时。"
    if code == "judge_protocol_invalid_json":
        return "语义裁判没有返回可解析的 JSON 结果。"
    if code == "judge_protocol_invalid_schema":
        return "语义裁判回复不符合当前评分协议。"
    detail = str(error)
    if "expected_card_id" in detail or "actual_review_item_id" in detail:
        return "语义裁判回复缺少固定卡片标识，未遵守当前评估格式。"
    if "dimensions" in detail or "confidence" in detail:
        return "语义裁判回复未按要求提供嵌套评分维度或置信度。"
    return "语义裁判提供方调用失败。"


def _difference_explanation_failure_message(error: Exception) -> str:
    """Convert explanation-call failures into a stable Chinese diagnosis."""
    detail = str(error)
    if "explanation_id" in detail or "条目" in detail:
        return "差异说明模型回复的条目标识不完整，未采用本次说明。"
    if "JSON" in detail or "json" in detail:
        return "差异说明模型没有返回可解析的 JSON 结果。"
    return "差异说明模型调用失败或返回格式不符合要求。"


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
