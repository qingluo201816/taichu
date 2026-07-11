"""Knowledge-extraction effect-evaluation application service."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
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
from taichu.application.evaluations.knowledge_extraction.judge import (
    PROMPT_CONTRACT_ID,
    JudgeBatchOutput,
    JudgeInputCase,
    JudgeItem,
    JudgeStatus,
    aggregate_judge_samples,
    build_judge_prompt,
    parse_judge_output,
    prompt_contract_hash,
    semantic_score,
    should_rejudge,
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


_RUN_ID_PATTERN = re.compile(r"^extract_run_\d{8}_\d{6}_[a-z0-9]{6}$")
_ACTIVE_STATUSES = {EvaluationStatus.PENDING, EvaluationStatus.RUNNING}
_TERMINAL_STATUSES = {
    EvaluationStatus.COMPLETED,
    EvaluationStatus.COMPLETED_WITH_WARNINGS,
    EvaluationStatus.FAILED,
}


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
    warnings: list[EvaluationNotice]


_REASON_MESSAGES = {
    "case_not_found": "任务范围没有匹配的评测样例。",
    "dataset_invalid": "评测集校验未通过。",
    "candidates_unreadable": "历史任务候选结果无法读取。",
    "snapshot_unavailable": "历史任务缺少可冻结的候选快照。",
    "source_hash_mismatch": "任务使用的正文与评测来源不一致。",
    "source_hash_unverified": "旧任务未保存完整正文哈希，仅提供降级诊断。",
    "incomplete_execution": "任务未完整执行，仅提供降级诊断。",
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
            issue.code == "EVALUATION_DATASET_NOT_FOUND"
            for issue in validation.issues
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
                (
                    record
                    for record in records
                    if run.run_id in record.run_ids
                ),
                None,
            )
            response.append(
                self._eligible_run_payload(prepared, latest=latest)
            )
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
                    "eligibility_level": item.eligibility.level.value,
                    "reason": self._reason_text(item.eligibility) or None,
                    "generation_model_identity": item.run.generation_model_identity,
                    "independence_level": independence,
                    "expected_card_count": (
                        len(item.case.expected_cards) if item.case else 0
                    ),
                    "estimated_matched_card_count": item.estimated_match_count,
                    "estimated_judge_card_count": (
                        item.estimated_match_count
                        if judge_enabled and full
                        else 0
                    ),
                }
            )
        judge_count = sum(
            item.estimated_match_count
            for item in prepared.runs
            if judge_enabled
            and item.eligibility.level is EligibilityLevel.FULL
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
            if judge_enabled
            and item.eligibility.level is EligibilityLevel.FULL
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
            metric_profile_id=prepared.profile.metric_profile_id,
            judge=JudgeSummary(
                enabled=judge_enabled,
                model_identity=(self._judge.model_identity if judge_enabled else None),
                self_judge=(
                    any(value is IndependenceLevel.SAME_MODEL for value in independence.values())
                    if judge_enabled
                    else None
                ),
                independence_by_run=independence,
            ),
            progress=EvaluationProgress(
                run_total=len(prepared.runs),
                judge_card_total=judge_count,
                judge_batch_total=(
                    prepared.judge_batch_count if judge_enabled else 0
                ),
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
        return await self._results.list_records(
            page=page,
            page_size=page_size,
            status=status,
        )

    async def get_evaluation(self, evaluation_id: str) -> KnowledgeEvaluationRecord:
        record = await self._results.get_record(evaluation_id)
        if record is None or record.lifecycle is EvaluationLifecycle.REJECTED:
            raise EvaluationServiceError(
                "EVALUATION_NOT_FOUND",
                "未找到指定评估记录。",
            )
        return record

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
        if run_id:
            comparisons = [item for item in comparisons if item.run_id == run_id]
        if knowledge_type:
            comparisons = [
                item for item in comparisons if item.knowledge_type == knowledge_type
            ]
        if issue_type and issue_type != "all":
            comparisons = [item for item in comparisons if item.issue_type == issue_type]
        total = len(comparisons)
        start = (page - 1) * page_size
        return comparisons[start : start + page_size], total

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
        if (
            parent.lifecycle is EvaluationLifecycle.REJECTED
            or parent.status
            not in {
                EvaluationStatus.FAILED,
                EvaluationStatus.COMPLETED_WITH_WARNINGS,
            }
        ):
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
            or frozen_contract.get("prompt_hash")
            != current_contract["prompt_hash"]
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
                or frozen_identity
                != self._judge.model_identity.model_dump(mode="json")
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
        if (
            record.lifecycle is not EvaluationLifecycle.DRAFT
            or record.status
            not in {
                EvaluationStatus.COMPLETED,
                EvaluationStatus.COMPLETED_WITH_WARNINGS,
            }
        ):
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
        if not 1 <= len(unique_ids) <= 10:
            raise EvaluationServiceError(
                "EVALUATION_CANDIDATE_SNAPSHOT_MISSING",
                "每次请选择 1 到 10 个历史任务。",
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
            for chapter_id, expected_hash in item.case.ref.source_chapter_hashes.items():
                markdown = chapters.get(chapter_id)
                if markdown is None or sha256(markdown.encode("utf-8")).hexdigest() != expected_hash:
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
                len(match_candidates(actual, case.expected_cards).matches)
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
                        self._judge.model_identity
                        if prepared.judge_enabled
                        else None
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
        except Exception:
            await self._fail_background(evaluation_id, token)
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
            grouped[(case.knowledge_type, generation_identity.get(run_id, run_id))].append(
                value
            )
        completed = 0
        batch_completed = 0
        for values in grouped.values():
            for offset in range(0, len(values), 5):
                batch = values[offset : offset + 5]
                first, ids, error = await self._judge_once(
                    record,
                    [item[0] for item in batch],
                    batch[0][2],
                )
                if error and len(batch) > 1:
                    first = {}
                    original_ids = ids
                    ids = defaultdict(list)
                    for key, original_call_ids in original_ids.items():
                        ids[key].extend(original_call_ids)
                    for case, _, independence in batch:
                        single, single_ids, single_error = await self._judge_once(
                            record,
                            [case],
                            independence,
                        )
                        first.update(single)
                        for key, values_ids in single_ids.items():
                            ids[key].extend(values_ids)
                        if single_error:
                            warnings.append(
                                EvaluationNotice(
                                    code="EVALUATION_JUDGE_INVALID_OUTPUT",
                                    message="语义裁判返回内容无法校验，已保留确定性结果。",
                                    run_id=case.run_id,
                                )
                            )
                elif error:
                    warnings.append(
                        EvaluationNotice(
                            code="EVALUATION_JUDGE_INVALID_OUTPUT",
                            message="语义裁判返回内容无法校验，已保留确定性结果。",
                            run_id=batch[0][1],
                        )
                    )
                for case, _, independence in batch:
                    sample = first.get(case.case_id)
                    samples = [sample] if sample else []
                    call_ids[case.case_id].extend(ids.get(case.case_id, []))
                    if sample is not None and should_rejudge(sample):
                        for _ in range(2):
                            repeated, repeated_ids, repeated_error = (
                                await self._judge_once(
                                    record,
                                    [case],
                                    independence,
                                )
                            )
                            call_ids[case.case_id].extend(
                                repeated_ids.get(case.case_id, [])
                            )
                            if not repeated_error and case.case_id in repeated:
                                samples.append(repeated[case.case_id])
                    aggregated = aggregate_judge_samples(samples)
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
                    elif samples:
                        warnings.append(
                            EvaluationNotice(
                                code="EVALUATION_JUDGE_DISAGREEMENT",
                                message="语义裁判重复判断未形成一致结论。",
                                run_id=case.run_id,
                            )
                        )
                    completed += 1
                batch_completed += 1
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
        return _JudgeExecution(dict(items), dict(call_ids), warnings)

    async def _judge_once(
        self,
        record: KnowledgeEvaluationRecord,
        cases: list[JudgeInputCase],
        independence: IndependenceLevel,
    ) -> tuple[dict[str, JudgeItem], dict[str, list[str]], bool]:
        prompt = build_judge_prompt(cases)
        call_id = f"judge_call_{token_hex(6)}"
        started_at = _now_iso()
        started = monotonic()
        raw: str | None = None
        parsed: dict[str, Any] | None = None
        error_message: str | None = None
        result: dict[str, JudgeItem] = {}
        token_usage: dict[str, int] | None = None
        try:
            response = await asyncio.wait_for(
                self._judge.complete(prompt),
                timeout=120,
            )
            raw = response.raw_response
            token_usage = response.token_usage
            output = parse_judge_output(raw, cases)
            parsed = output.model_dump(mode="json")
            result = {item.case_id: item for item in output.items}
        except Exception:
            error_message = "语义裁判调用或输出校验失败。"
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
            error=error_message,
            token_usage=token_usage,
        )
        await self._results.write_judge_call(call)
        ids = {case.case_id: [call_id] for case in cases}
        return result, ids, error_message is not None

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

    async def _fail_background(self, evaluation_id: str, token: str) -> None:
        now = _now_iso()
        try:
            await self._results.mutate_record(
                evaluation_id,
                {
                    "status": EvaluationStatus.FAILED,
                    "phase": EvaluationPhase.FINISHED,
                    "error_code": "EVALUATION_SNAPSHOT_CORRUPTED",
                    "error_message": "评估执行失败，冻结快照或中间结果无法可靠读取。",
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

    @staticmethod
    def _reason_text(eligibility: EvaluationEligibility) -> str:
        return "；".join(_REASON_MESSAGES[reason.value] for reason in eligibility.reasons)


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
    matches = match_candidates(actual, case.expected_cards)
    candidate_metrics = compute_candidate_identification_metrics(matches)
    structured = compare_structured_fields(
        matches,
        actual,
        case.expected_cards,
        case.rules,
    )
    actual_by_id = {item.actual_candidate_id: item for item in actual}
    expected_by_id = {item.expected_card_id: item for item in case.expected_cards}
    quote_by_id = {item.quote_id: item for item in case.source_evidence}
    located: list[LocatedEvidence] = []
    expected_groups: list[ExpectedEvidenceGroup] = []
    for match in matches.matches:
        candidate = actual_by_id[match.actual_candidate_id]
        for index, excerpt in enumerate(candidate.evidence_excerpts):
            location = _locate_excerpt(excerpt, case.ref.chapter_ids, chapters)
            located.append(
                LocatedEvidence(
                    evidence_id=f"{candidate.actual_candidate_id}:{index}",
                    **location,
                )
            )
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
        result.append(
            EvaluationComparison(
                run_id=run_id,
                case_id=case_id,
                knowledge_type=match.knowledge_type.value,
                issue_type="field_difference",
                expected_card_id=match.expected_card_id,
                actual_candidate_id=match.actual_candidate_id,
                expected_card=expected_card.card,
                actual_card=actual_card.card,
                match_kind=match.kind.value,
                field_diffs=[
                    item.model_dump(mode="json")
                    for item in diffs
                    if item.actual_candidate_id == match.actual_candidate_id
                    and item.comparable
                    and item.score is not None
                    and item.score < 1
                ],
            )
        )
    for item in matches.false_positives:
        candidate = actual_by_id[item.card_id]
        result.append(
            EvaluationComparison(
                run_id=run_id,
                case_id=case_id,
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
                knowledge_type=item.knowledge_type.value,
                issue_type="missing_candidate",
                expected_card_id=item.card_id,
                expected_card=card.card,
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
                located_actual_evidence.append(
                    {"text": excerpt[:350], **location}
                )
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
                },
                actual_fields={
                    field: actual_card.card.get(field)
                    for field in expected_card.semantic_fields
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
                disagreement = bool(judged.call_ids.get(key))
                comparisons.append(comparison)
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
            comparisons.append(
                comparison.model_copy(
                    update={
                        "judge_result": {
                            **item.model_dump(mode="json"),
                            "judge_call_ids": judged.call_ids.get(key, []),
                            "semantic_score": score,
                        }
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
        deterministic_state = QualityState(
            run.metrics["deterministic_quality_state"]
        )
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
                critical_claims_covered=(
                    coverage == 1 and not critical_claim_missing
                ),
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
    aggregate["semantic_score"] = (
        sum(semantic) / len(semantic) if semantic else None
    )
    aggregate["judge_coverage"] = (
        sum(coverage) / len(coverage) if coverage else None
    )
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
        result.append(
            ActualCandidate(
                actual_candidate_id=item.review_item_id,
                knowledge_type=item.knowledge_type,
                candidate_action=CandidateAction(item.candidate_action.value),
                card=item.suggested_card,
                schema_valid=item.schema_validation.passed,
                evidence_excerpts=list(dict.fromkeys(excerpts)),
            )
        )
    return result


def _run_scope(run: AgentRun) -> tuple[EvaluationScopeType, list[str]]:
    scope = run.scope
    if scope.scope_type == EvaluationScopeType.CHAPTER_BATCH.value:
        return EvaluationScopeType.CHAPTER_BATCH, list(scope.chapter_ids)
    chapter_ids = list(scope.chapter_ids) or ([scope.chapter_id] if scope.chapter_id else [])
    if len(chapter_ids) > 1:
        return EvaluationScopeType.CHAPTER_BATCH, chapter_ids
    return EvaluationScopeType.CHAPTER, chapter_ids


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
        matches = match_candidates(item.actual_candidates, item.case.expected_cards)
        for match in matches.matches:
            identity = _hash_json(
                item.run.generation_model_identity.model_dump(mode="json")
            )
            groups[(match.knowledge_type.value, identity)] += 1
    return sum((count + 4) // 5 for count in groups.values())


def derive_independence(
    generation: LLMModelIdentity,
    judge: LLMModelIdentity,
) -> IndependenceLevel:
    if not generation.known or not judge.known:
        return IndependenceLevel.UNKNOWN
    if (
        generation.provider == judge.provider
        and generation.model_id == judge.model_id
    ):
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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
