"""需求 15.6-15.32：评测失败与 Inbox issue revision 的持久关联。"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from math import ceil
from typing import Literal

from pydantic import Field, field_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
)


class IssueStatus(StrEnum):
    TODO = "todo"
    PROCESSED = "processed"


class IssueCorrelationRevisionConflict(RuntimeError):
    def __init__(self, current_revision: int) -> None:
        self.current_revision = current_revision
        super().__init__(f"问题 revision 冲突：当前 {current_revision}。")


class IssueCorrelationIntent(BenchmarkModel):
    intent_id: str = Field(pattern=r"^issue_intent_[a-f0-9]{64}$")
    stable_issue_key: str = Field(pattern=r"^benchmark_issue_[a-f0-9]{64}$")
    iteration_id: StableId
    suite_hash: Sha256
    run_id: str = Field(
        pattern=r"^benchmark_run_\d{8}T\d{6}Z_[a-f0-9]{12}$"
    )
    failure_record_id: StableId
    frozen_subject_id: str = Field(min_length=1, max_length=300)
    classification: Literal["system_defect"]
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    content_hash: Sha256

    @classmethod
    def create(
        cls,
        *,
        iteration_id: str,
        suite_hash: str,
        run_id: str,
        failure_record_id: str,
        frozen_subject_id: str,
        classification: Literal["system_defect"],
        evidence_refs: tuple[str, ...],
    ) -> IssueCorrelationIntent:
        identity = {
            "iteration_id": iteration_id,
            "suite_hash": suite_hash,
            "run_id": run_id,
            "failure_record_id": failure_record_id,
            "frozen_subject_id": frozen_subject_id,
            "classification": classification,
        }
        stable_issue_key = (
            f"benchmark_issue_{canonical_sha256(identity)}"
        )
        payload = {
            **identity,
            "stable_issue_key": stable_issue_key,
            "evidence_refs": evidence_refs,
        }
        content_hash = canonical_sha256(payload)
        return cls(
            intent_id=f"issue_intent_{content_hash}",
            content_hash=content_hash,
            **payload,
        )


class IssueCorrelationRevision(BenchmarkModel):
    revision_id: str = Field(pattern=r"^issue_revision_[a-f0-9]{64}$")
    intent_id: str = Field(pattern=r"^issue_intent_[a-f0-9]{64}$")
    stable_issue_key: str = Field(pattern=r"^benchmark_issue_[a-f0-9]{64}$")
    issue_id: str = Field(min_length=1, max_length=300)
    revision: int = Field(ge=0)
    status: IssueStatus
    content_hash: Sha256
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class IssueCorrelationObservationKind(StrEnum):
    INTENT_CREATED = "intent_created"
    LEGACY_READBACK = "legacy_readback"
    REVISION_APPENDED = "revision_appended"
    CAS_CONFLICT = "cas_conflict"
    IDENTITY_CONFLICT = "identity_conflict"


class IssueCorrelationObservation(BenchmarkModel):
    observation_id: str = Field(pattern=r"^issue_observation_[a-f0-9]{64}$")
    sequence: int = Field(ge=1)
    intent_id: str = Field(pattern=r"^issue_intent_[a-f0-9]{64}$")
    kind: IssueCorrelationObservationKind
    issue_id: str | None = Field(default=None, min_length=1, max_length=300)
    expected_revision: int | None = Field(default=None, ge=0)
    observed_revision: int | None = Field(default=None, ge=0)
    evidence_refs: tuple[str, ...]
    detail: str = Field(min_length=1, max_length=1_000)


class IssueCorrelationRepository:
    """内存参考实现；意图去重、revision 与 observation 均为 append-only。"""

    def __init__(self) -> None:
        self._intents: dict[str, IssueCorrelationIntent] = {}
        self._intent_by_issue_key: dict[str, str] = {}
        self._revisions: dict[str, list[IssueCorrelationRevision]] = {}
        self._issue_bindings: dict[str, str] = {}
        self._observations: dict[str, list[IssueCorrelationObservation]] = {}
        self._lock = asyncio.Lock()

    async def create_intent(
        self,
        intent: IssueCorrelationIntent,
    ) -> IssueCorrelationIntent:
        async with self._lock:
            existing_id = self._intent_by_issue_key.get(
                intent.stable_issue_key
            )
            if existing_id is not None:
                existing = self._intents[existing_id]
                if existing != intent:
                    raise ValueError("稳定问题标识已经绑定不同意图。")
                return existing
            self._intents[intent.intent_id] = intent
            self._intent_by_issue_key[intent.stable_issue_key] = (
                intent.intent_id
            )
            self._revisions[intent.intent_id] = []
            self._observations[intent.intent_id] = []
            self._append_observation(
                intent_id=intent.intent_id,
                kind=IssueCorrelationObservationKind.INTENT_CREATED,
                issue_id=None,
                expected_revision=None,
                observed_revision=None,
                evidence_refs=intent.evidence_refs,
                detail="已建立确定性系统问题意图。",
            )
            return intent

    async def observe_legacy_issue(
        self,
        *,
        intent_id: str,
        issue_id: str,
        status: IssueStatus,
        content_hash: str,
        evidence_refs: tuple[str, ...],
    ) -> IssueCorrelationRevision:
        async with self._lock:
            intent = self._intents[intent_id]
            revisions = self._revisions[intent_id]
            if revisions:
                current = revisions[-1]
                candidate = self._make_revision(
                    intent=intent,
                    issue_id=issue_id,
                    revision=0,
                    status=IssueStatus(status),
                    content_hash=content_hash,
                    evidence_refs=evidence_refs,
                )
                if current == candidate:
                    return current
                raise ValueError("问题意图已有 revision，不能重写 legacy 观察。")
            self._claim_issue(intent_id, issue_id)
            revision = self._make_revision(
                intent=intent,
                issue_id=issue_id,
                revision=0,
                status=IssueStatus(status),
                content_hash=content_hash,
                evidence_refs=evidence_refs,
            )
            revisions.append(revision)
            self._append_observation(
                intent_id=intent_id,
                kind=IssueCorrelationObservationKind.LEGACY_READBACK,
                issue_id=issue_id,
                expected_revision=0,
                observed_revision=0,
                evidence_refs=evidence_refs,
                detail="legacy 问题已只读投影为 revision 0。",
            )
            return revision

    async def append_revision(
        self,
        *,
        intent_id: str,
        issue_id: str,
        expected_revision: int,
        status: IssueStatus,
        content_hash: str,
        evidence_refs: tuple[str, ...],
    ) -> IssueCorrelationRevision:
        async with self._lock:
            intent = self._intents[intent_id]
            revisions = self._revisions[intent_id]
            bound_intent = self._issue_bindings.get(issue_id)
            bound_issue = revisions[-1].issue_id if revisions else None
            if (
                (bound_intent is not None and bound_intent != intent_id)
                or (bound_issue is not None and bound_issue != issue_id)
            ):
                self._append_observation(
                    intent_id=intent_id,
                    kind=IssueCorrelationObservationKind.IDENTITY_CONFLICT,
                    issue_id=issue_id,
                    expected_revision=expected_revision,
                    observed_revision=(
                        revisions[-1].revision if revisions else None
                    ),
                    evidence_refs=evidence_refs,
                    detail="问题 ID 与确定性意图绑定不一致。",
                )
                raise ValueError("问题 ID 已绑定不同确定性意图。")
            current_revision = revisions[-1].revision if revisions else 0
            if current_revision != expected_revision:
                self._append_observation(
                    intent_id=intent_id,
                    kind=IssueCorrelationObservationKind.CAS_CONFLICT,
                    issue_id=issue_id,
                    expected_revision=expected_revision,
                    observed_revision=current_revision,
                    evidence_refs=evidence_refs,
                    detail="问题 revision CAS 冲突。",
                )
                raise IssueCorrelationRevisionConflict(current_revision)
            self._claim_issue(intent_id, issue_id)
            revision = self._make_revision(
                intent=intent,
                issue_id=issue_id,
                revision=current_revision + 1,
                status=IssueStatus(status),
                content_hash=content_hash,
                evidence_refs=evidence_refs,
            )
            revisions.append(revision)
            self._append_observation(
                intent_id=intent_id,
                kind=IssueCorrelationObservationKind.REVISION_APPENDED,
                issue_id=issue_id,
                expected_revision=expected_revision,
                observed_revision=revision.revision,
                evidence_refs=evidence_refs,
                detail="问题 revision 已按 CAS 追加。",
            )
            return revision

    async def latest_revision(
        self,
        intent_id: str,
    ) -> IssueCorrelationRevision:
        async with self._lock:
            revisions = self._revisions[intent_id]
            if not revisions:
                raise KeyError("问题意图尚无 readback revision。")
            return revisions[-1]

    async def list_revisions(
        self,
        intent_id: str,
    ) -> tuple[IssueCorrelationRevision, ...]:
        async with self._lock:
            return tuple(self._revisions[intent_id])

    async def list_observations(
        self,
        intent_id: str,
    ) -> tuple[IssueCorrelationObservation, ...]:
        async with self._lock:
            return tuple(self._observations[intent_id])

    async def list_intents(self) -> tuple[IssueCorrelationIntent, ...]:
        async with self._lock:
            return tuple(
                self._intents[key] for key in sorted(self._intents)
            )

    def _claim_issue(self, intent_id: str, issue_id: str) -> None:
        bound = self._issue_bindings.get(issue_id)
        if bound is not None and bound != intent_id:
            raise ValueError("Inbox 问题已绑定其他评测意图。")
        self._issue_bindings[issue_id] = intent_id

    @staticmethod
    def _make_revision(
        *,
        intent: IssueCorrelationIntent,
        issue_id: str,
        revision: int,
        status: IssueStatus,
        content_hash: str,
        evidence_refs: tuple[str, ...],
    ) -> IssueCorrelationRevision:
        payload = {
            "intent_id": intent.intent_id,
            "stable_issue_key": intent.stable_issue_key,
            "issue_id": issue_id,
            "revision": revision,
            "status": status,
            "content_hash": content_hash,
            "evidence_refs": evidence_refs,
        }
        return IssueCorrelationRevision(
            revision_id=f"issue_revision_{canonical_sha256(payload)}",
            **payload,
        )

    def _append_observation(
        self,
        *,
        intent_id: str,
        kind: IssueCorrelationObservationKind,
        issue_id: str | None,
        expected_revision: int | None,
        observed_revision: int | None,
        evidence_refs: tuple[str, ...],
        detail: str,
    ) -> None:
        observations = self._observations[intent_id]
        sequence = len(observations) + 1
        payload = {
            "sequence": sequence,
            "intent_id": intent_id,
            "kind": kind,
            "issue_id": issue_id,
            "expected_revision": expected_revision,
            "observed_revision": observed_revision,
            "evidence_refs": evidence_refs,
            "detail": detail,
        }
        observations.append(
            IssueCorrelationObservation(
                observation_id=(
                    f"issue_observation_{canonical_sha256(payload)}"
                ),
                **payload,
            )
        )


class IssueRelationKind(StrEnum):
    DOCUMENTS = "documents"
    CAUSED_BY = "caused_by"
    OBSERVED_IN = "observed_in"
    CLOSES = "closes"


class IssueTypedLink(BenchmarkModel):
    namespace: StableId
    relation_id: Sha256
    subject_id: Sha256
    relation_kind: IssueRelationKind
    subject_content_sha256: Sha256


class FrozenSubjectSnapshot(BenchmarkModel):
    subject_id: Sha256
    content_hash: Sha256
    artifact_ref: str = Field(min_length=1, max_length=500)


class IssueCorrelationRelationRevision(BenchmarkModel):
    revision_id: str = Field(pattern=r"^relation_revision_[a-f0-9]{64}$")
    relation_id: Sha256
    intent_id: str = Field(pattern=r"^issue_intent_[a-f0-9]{64}$")
    subject_id: Sha256
    subject_content_hash: Sha256
    issue_id: str = Field(min_length=1, max_length=300)
    issue_revision: int = Field(ge=0)
    issue_status: IssueStatus
    issue_content_hash: Sha256
    relation_kind: IssueRelationKind

    @classmethod
    def create(
        cls,
        *,
        intent_id: str,
        subject_id: str,
        subject_content_hash: str,
        issue_id: str,
        issue_revision: int,
        issue_status: IssueStatus,
        issue_content_hash: str,
        relation_kind: IssueRelationKind,
    ) -> IssueCorrelationRelationRevision:
        relation_identity = {
            "intent_id": intent_id,
            "subject_id": subject_id,
            "issue_id": issue_id,
            "relation_kind": relation_kind,
        }
        relation_id = canonical_sha256(relation_identity)
        payload = {
            **relation_identity,
            "relation_id": relation_id,
            "subject_content_hash": subject_content_hash,
            "issue_revision": issue_revision,
            "issue_status": IssueStatus(issue_status),
            "issue_content_hash": issue_content_hash,
        }
        return cls(
            revision_id=f"relation_revision_{canonical_sha256(payload)}",
            **payload,
        )


class IssueRelationManifest(BenchmarkModel):
    relation_id: Sha256
    revision: int = Field(ge=1)
    latest_confirmed_revision_id: str = Field(
        pattern=r"^relation_revision_[a-f0-9]{64}$"
    )


class InboxIssueReadback(BenchmarkModel):
    issue_id: str = Field(min_length=1, max_length=300)
    revision: int = Field(ge=0)
    status: IssueStatus
    content_hash: Sha256
    links: tuple[IssueTypedLink, ...]


class IterationCorrelationSnapshot(BenchmarkModel):
    iteration_id: StableId
    pending_intent_ids: tuple[str, ...]
    confirmed_relation_revision_ids: tuple[str, ...]

    @field_validator(
        "pending_intent_ids",
        "confirmed_relation_revision_ids",
    )
    @classmethod
    def _refs_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("迭代关联引用不得重复。")
        return value


class IssueCorrelationSnapshot(BenchmarkModel):
    intent: IssueCorrelationIntent
    subject: FrozenSubjectSnapshot
    relation_revision: IssueCorrelationRelationRevision
    relation_manifest: IssueRelationManifest
    inbox_readback: InboxIssueReadback
    iteration: IterationCorrelationSnapshot


class IssueCorrelationSymmetryResult(BenchmarkModel):
    passed: bool
    relation_revision_id: str
    problems: tuple[str, ...]


class IssueCorrelationSymmetryGate:
    @staticmethod
    def evaluate(
        snapshot: IssueCorrelationSnapshot,
    ) -> IssueCorrelationSymmetryResult:
        relation = snapshot.relation_revision
        problems: list[str] = []
        if snapshot.intent.intent_id != relation.intent_id:
            problems.append("关系 revision 未绑定当前问题意图。")
        if snapshot.subject.subject_id != relation.subject_id:
            problems.append("冻结 subject 身份不一致。")
        if snapshot.subject.content_hash != relation.subject_content_hash:
            problems.append("冻结 subject 内容哈希不一致。")
        if snapshot.relation_manifest.relation_id != relation.relation_id:
            problems.append("关系 manifest 身份不一致。")
        if (
            snapshot.relation_manifest.latest_confirmed_revision_id
            != relation.revision_id
        ):
            problems.append("关系 manifest 未指向最新 confirmed revision。")
        readback = snapshot.inbox_readback
        if readback.issue_id != relation.issue_id:
            problems.append("Inbox readback 问题身份不一致。")
        if readback.revision != relation.issue_revision:
            problems.append("Inbox readback revision 不一致。")
        if readback.status is not relation.issue_status:
            problems.append("Inbox readback 状态不一致。")
        if readback.content_hash != relation.issue_content_hash:
            problems.append("Inbox readback 正文哈希不一致。")
        expected_link = IssueTypedLink(
            namespace="general_agent_benchmark",
            relation_id=relation.relation_id,
            subject_id=relation.subject_id,
            relation_kind=relation.relation_kind,
            subject_content_sha256=relation.subject_content_hash,
        )
        matching_links = [
            item for item in readback.links if item == expected_link
        ]
        if len(matching_links) != 1:
            problems.append("Inbox typed link 缺失或重复。")
        if snapshot.intent.intent_id in snapshot.iteration.pending_intent_ids:
            problems.append("迭代仍保留 pending intent。")
        if (
            relation.revision_id
            not in snapshot.iteration.confirmed_relation_revision_ids
        ):
            problems.append("迭代未引用 confirmed relation revision。")
        return IssueCorrelationSymmetryResult(
            passed=not problems,
            relation_revision_id=relation.revision_id,
            problems=tuple(problems),
        )


class ReconciliationStatus(StrEnum):
    CONSISTENT = "consistent"
    REPAIR_REQUIRED = "repair_required"
    CONFLICTING = "conflicting"


class ReconciliationAction(BenchmarkModel):
    action: Literal[
        "restore_typed_link",
        "confirm_relation_revision",
        "commit_iteration_relation",
    ]
    target_id: str = Field(min_length=1, max_length=500)


class IssueReconciliationReport(BenchmarkModel):
    status: ReconciliationStatus
    actions: tuple[ReconciliationAction, ...]
    problems: tuple[str, ...]
    report_hash: Sha256


class IssueCorrelationReconciler:
    """只做确定性检查与补偿建议，不篡改冻结工件或 Inbox。"""

    @staticmethod
    def inspect(
        snapshot: IssueCorrelationSnapshot,
    ) -> IssueReconciliationReport:
        relation = snapshot.relation_revision
        gate = IssueCorrelationSymmetryGate.evaluate(snapshot)
        if gate.passed:
            status = ReconciliationStatus.CONSISTENT
            actions: tuple[ReconciliationAction, ...] = ()
        else:
            conflicting = any(
                problem
                in {
                    "关系 revision 未绑定当前问题意图。",
                    "冻结 subject 身份不一致。",
                    "冻结 subject 内容哈希不一致。",
                    "Inbox readback 问题身份不一致。",
                    "Inbox readback revision 不一致。",
                    "Inbox readback 状态不一致。",
                    "Inbox readback 正文哈希不一致。",
                }
                for problem in gate.problems
            )
            if conflicting:
                status = ReconciliationStatus.CONFLICTING
                actions = ()
            else:
                action_items: list[ReconciliationAction] = []
                expected_link = IssueTypedLink(
                    namespace="general_agent_benchmark",
                    relation_id=relation.relation_id,
                    subject_id=relation.subject_id,
                    relation_kind=relation.relation_kind,
                    subject_content_sha256=relation.subject_content_hash,
                )
                matching_links = [
                    item
                    for item in snapshot.inbox_readback.links
                    if item == expected_link
                ]
                if not matching_links:
                    action_items.append(
                        ReconciliationAction(
                            action="restore_typed_link",
                            target_id=relation.issue_id,
                        )
                    )
                elif len(matching_links) > 1:
                    status = ReconciliationStatus.CONFLICTING
                    actions = ()
                    return _reconciliation_report(
                        status=status,
                        actions=actions,
                        problems=gate.problems,
                    )
                if (
                    snapshot.relation_manifest.relation_id
                    != relation.relation_id
                    or snapshot.relation_manifest.latest_confirmed_revision_id
                    != relation.revision_id
                ):
                    action_items.append(
                        ReconciliationAction(
                            action="confirm_relation_revision",
                            target_id=relation.relation_id,
                        )
                    )
                if (
                    snapshot.intent.intent_id
                    in snapshot.iteration.pending_intent_ids
                    or relation.revision_id
                    not in snapshot.iteration.confirmed_relation_revision_ids
                ):
                    action_items.append(
                        ReconciliationAction(
                            action="commit_iteration_relation",
                            target_id=snapshot.iteration.iteration_id,
                        )
                    )
                status = ReconciliationStatus.REPAIR_REQUIRED
                actions = tuple(action_items)
        return _reconciliation_report(
            status=status,
            actions=actions,
            problems=gate.problems,
        )


def _reconciliation_report(
    *,
    status: ReconciliationStatus,
    actions: tuple[ReconciliationAction, ...],
    problems: tuple[str, ...],
) -> IssueReconciliationReport:
    payload = {
        "status": status,
        "actions": actions,
        "problems": problems,
    }
    return IssueReconciliationReport(
        status=status,
        actions=actions,
        problems=problems,
        report_hash=canonical_sha256(payload),
    )


class IssueCorrelationStatus(BenchmarkModel):
    snapshot: IssueCorrelationSnapshot
    symmetry: IssueCorrelationSymmetryResult


class IssueObservationPage(BenchmarkModel):
    items: tuple[IssueCorrelationObservation, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    total_snapshot: Sha256


class IssueCorrelationQueryService:
    def __init__(self, repository: IssueCorrelationRepository) -> None:
        self._repository = repository
        self._by_subject: dict[str, IssueCorrelationSnapshot] = {}

    def register(self, snapshot: IssueCorrelationSnapshot) -> None:
        subject_id = snapshot.subject.subject_id
        existing = self._by_subject.get(subject_id)
        if existing is not None and existing != snapshot:
            raise ValueError("冻结 subject 已绑定不同关联快照。")
        self._by_subject[subject_id] = snapshot

    def get_by_subject(self, subject_id: str) -> IssueCorrelationStatus:
        snapshot = self._by_subject[subject_id]
        return IssueCorrelationStatus(
            snapshot=snapshot,
            symmetry=IssueCorrelationSymmetryGate.evaluate(snapshot),
        )

    async def list_observations(
        self,
        *,
        intent_id: str,
        page: int,
        page_size: int,
    ) -> IssueObservationPage:
        if page < 1:
            raise ValueError("page 必须大于等于 1。")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size 必须在 1 到 100 之间。")
        observations = await self._repository.list_observations(intent_id)
        total = len(observations)
        offset = (page - 1) * page_size
        return IssueObservationPage(
            items=observations[offset : offset + page_size],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
            total_snapshot=canonical_sha256(observations),
        )
