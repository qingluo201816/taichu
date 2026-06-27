"""Chapter summary draft and candidate setting pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import uuid4

from pydantic import ValidationError

from taichu.application.contracts.llm import LLMContract
from taichu.application.contracts.retrieval import RetrievalContract, RetrievalQuery
from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.application.services.ai_card_service import (
    PENDING_FACTS_FILE,
    AICardService,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.knowledge_service import KnowledgeService
from taichu.application.workflows.summary import (
    SummaryWorkflowOutput,
    build_summary_prompt,
)
from taichu.domain.models.ai_card import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
    AIWorkflow,
)
from taichu.domain.models.pending_fact import (
    PendingFact,
    PendingFactStatus,
    PendingFactType,
    ProposedBy,
)
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)
from taichu.domain.models.summary import ChapterSummary, ChapterSummaryStatus
from taichu.domain.rules.fact_scope import is_allowed_in_fact_scope

CHAPTER_SUMMARIES_FILE = "chapter_summaries.jsonl"
_SEGMENT_CHAR_LIMIT = 1600


@dataclass(frozen=True)
class ChapterSummaryRunResult:
    """Result of running the chapter summary workflow."""

    summary: ChapterSummary
    card: AIResultCard


@dataclass(frozen=True)
class ChapterSummaryEdit:
    """Author edits applied while confirming a summary draft."""

    summary: str | None = None
    key_events: list[str] | None = None
    character_changes: list[dict[str, Any]] | None = None
    foreshadow_candidates: list[dict[str, Any]] | None = None
    next_chapter_hooks: list[str] | None = None


class ChapterSummaryService:
    """Application use cases for chapter summaries and candidates."""

    def __init__(
        self,
        *,
        storage: ProjectAssetStorageContract,
        chapter_service: ChapterService,
        knowledge_service: KnowledgeService,
        retrieval: RetrievalContract,
        llm: LLMContract,
        ai_card_service: AICardService,
    ) -> None:
        self._storage = storage
        self._chapter_service = chapter_service
        self._knowledge_service = knowledge_service
        self._retrieval = retrieval
        self._llm = llm
        self._ai_card_service = ai_card_service

    async def summarize_chapter(self, chapter_id: str) -> ChapterSummaryRunResult:
        """Generate and persist a ChapterSummary draft and card."""
        chapter_content = await self._chapter_service.read_chapter(chapter_id)
        source_ref = _chapter_source_ref(
            chapter_id=chapter_id,
            path=chapter_content.chapter.markdown_path,
            markdown=chapter_content.markdown,
        )
        body_segments = _chapter_segments(chapter_content.markdown)
        now = _now_iso()

        if _is_empty_chapter(chapter_content.markdown):
            workflow_output = SummaryWorkflowOutput(
                summary=f"{chapter_content.chapter.title} 暂无可整理正文。",
            )
        else:
            knowledge_cards = await self._knowledge_service.list_cards()
            retrieval_hits = await self._retrieval.search(
                RetrievalQuery(
                    text=_retrieval_query_text(chapter_content.markdown),
                    limit=8,
                )
            )
            prompt = build_summary_prompt(
                chapter_id=chapter_id,
                chapter_title=chapter_content.chapter.title,
                segments=body_segments,
                confirmed_knowledge=knowledge_cards,
                retrieval_hits=retrieval_hits,
            )
            workflow_output = _parse_summary_output(
                await self._llm.complete(prompt),
                chapter_content.markdown,
            )

        summary = ChapterSummary(
            id=f"summary_{uuid4().hex}",
            chapter_id=chapter_id,
            status=ChapterSummaryStatus.DRAFT,
            summary=workflow_output.summary,
            key_events=_clean_strings(workflow_output.key_events),
            character_changes=workflow_output.character_changes,
            new_setting_candidates=_candidate_pending_facts(
                workflow_output.new_setting_candidates,
                source_ref,
                now,
            ),
            foreshadow_candidates=workflow_output.foreshadow_candidates,
            next_chapter_hooks=_clean_strings(workflow_output.next_chapter_hooks),
            source_refs=[source_ref],
            created_at=now,
            updated_at=now,
        )
        await self._storage.append_workspace_record(
            CHAPTER_SUMMARIES_FILE,
            summary.model_dump(mode="json"),
        )
        card = await self._ai_card_service.create_card(
            AIResultCard(
                id=f"card_{uuid4().hex}",
                type=AIResultCardType.CHAPTER_SUMMARY,
                workflow=AIWorkflow.SUMMARIZE,
                status=AIResultCardStatus.GENERATED,
                chapter_id=chapter_id,
                input_context={
                    "chapter_id": chapter_id,
                    "summary_id": summary.id,
                },
                content=summary.model_dump(mode="json"),
                source_refs=summary.source_refs,
                created_at=now,
                updated_at=now,
            )
        )
        return ChapterSummaryRunResult(summary=summary, card=card)

    async def list_summaries(
        self,
        chapter_id: str | None = None,
    ) -> list[ChapterSummary]:
        """List persisted chapter summaries, optionally filtered by chapter."""
        records = await self._storage.list_workspace_records(CHAPTER_SUMMARIES_FILE)
        summaries = [ChapterSummary.model_validate(record) for record in records]
        if chapter_id is None:
            return summaries
        return [summary for summary in summaries if summary.chapter_id == chapter_id]

    async def confirm_summary(
        self,
        summary_id: str,
        edits: ChapterSummaryEdit | None = None,
    ) -> ChapterSummary:
        """Confirm a summary without writing Knowledge."""
        summary = await self._get_summary(summary_id)
        updates: dict[str, object] = {
            "status": ChapterSummaryStatus.CONFIRMED,
            "updated_at": _now_iso(),
        }
        if edits is not None:
            if edits.summary is not None:
                updates["summary"] = edits.summary
            if edits.key_events is not None:
                updates["key_events"] = _clean_strings(edits.key_events)
            if edits.character_changes is not None:
                updates["character_changes"] = edits.character_changes
            if edits.foreshadow_candidates is not None:
                updates["foreshadow_candidates"] = edits.foreshadow_candidates
            if edits.next_chapter_hooks is not None:
                updates["next_chapter_hooks"] = _clean_strings(edits.next_chapter_hooks)
        confirmed = summary.model_copy(update=updates)
        await self._replace_summary(confirmed)
        return confirmed

    async def ignore_summary(self, summary_id: str) -> ChapterSummary:
        """Ignore a summary draft without changing fact assets."""
        summary = await self._get_summary(summary_id)
        ignored = summary.model_copy(
            update={
                "status": ChapterSummaryStatus.IGNORED,
                "updated_at": _now_iso(),
            }
        )
        await self._replace_summary(ignored)
        return ignored

    async def convert_candidate_to_pending_fact(
        self,
        summary_id: str,
        pending_fact_id: str,
    ) -> PendingFact:
        """Persist one summary candidate as a non-fact PendingFact."""
        summary = await self._get_summary(summary_id)
        for candidate in summary.new_setting_candidates:
            if candidate.id == pending_fact_id:
                return await self._append_pending_fact_once(candidate)
        raise SummaryCandidateNotFoundError(pending_fact_id)

    async def _append_pending_fact_once(self, candidate: PendingFact) -> PendingFact:
        if is_allowed_in_fact_scope(candidate):
            raise ChapterSummaryError("Summary candidates must not be facts")
        records = await self._storage.list_workspace_records(PENDING_FACTS_FILE)
        existing = [PendingFact.model_validate(record) for record in records]
        for pending_fact in existing:
            if pending_fact.id == candidate.id:
                return pending_fact
        await self._storage.append_workspace_record(
            PENDING_FACTS_FILE,
            candidate.model_dump(mode="json"),
        )
        return candidate

    async def _get_summary(self, summary_id: str) -> ChapterSummary:
        for summary in await self.list_summaries():
            if summary.id == summary_id:
                return summary
        raise ChapterSummaryNotFoundError(summary_id)

    async def _replace_summary(self, updated: ChapterSummary) -> None:
        records = await self._storage.list_workspace_records(CHAPTER_SUMMARIES_FILE)
        rewritten: list[dict[str, object]] = []
        replaced = False
        for record in records:
            summary = ChapterSummary.model_validate(record)
            if summary.id == updated.id:
                rewritten.append(updated.model_dump(mode="json"))
                replaced = True
            else:
                rewritten.append(summary.model_dump(mode="json"))
        if not replaced:
            raise ChapterSummaryNotFoundError(updated.id)
        await self._storage.rewrite_workspace_records(
            CHAPTER_SUMMARIES_FILE,
            rewritten,
        )


class ChapterSummaryError(ValueError):
    """Raised when a chapter summary operation is invalid."""


class ChapterSummaryNotFoundError(LookupError):
    """Raised when a chapter summary id is absent from workspace records."""

    def __init__(self, summary_id: str) -> None:
        super().__init__(f"章节整理记录“{summary_id}”不存在")


class SummaryCandidateNotFoundError(LookupError):
    """Raised when a candidate id is absent from a summary."""

    def __init__(self, pending_fact_id: str) -> None:
        super().__init__(f"章节整理候选“{pending_fact_id}”不存在")


def _parse_summary_output(raw_output: str, markdown: str) -> SummaryWorkflowOutput:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return _fallback_summary(markdown)
    if not isinstance(parsed, dict):
        return _fallback_summary(markdown)
    try:
        return SummaryWorkflowOutput.model_validate(parsed)
    except ValidationError:
        return _fallback_summary(markdown)


def _fallback_summary(markdown: str) -> SummaryWorkflowOutput:
    excerpt = _plain_excerpt(markdown)
    return SummaryWorkflowOutput(
        summary=excerpt or "本章暂无可整理正文。",
        key_events=[excerpt] if excerpt else [],
    )


def _candidate_pending_facts(
    candidates: Sequence[object],
    source_ref: SourceRef,
    created_at: str,
) -> list[PendingFact]:
    pending_facts: list[PendingFact] = []
    seen: set[str] = set()
    for candidate in candidates:
        data = _candidate_data(candidate)
        title = _text_or_none(data.get("title"))
        if not title:
            continue
        content = data.get("content")
        if content is None:
            content = _text_or_none(data.get("body")) or title
        fact_type = _pending_fact_type(data.get("fact_type"))
        key = _candidate_key(fact_type.value, title, content)
        if key in seen:
            continue
        seen.add(key)
        pending_facts.append(
            PendingFact(
                id=f"pending_fact_{uuid4().hex}",
                fact_type=fact_type,
                title=title,
                content=content,
                proposed_by=ProposedBy.AI,
                source_refs=[source_ref],
                status=PendingFactStatus.PENDING,
                created_at=created_at,
            )
        )
    return pending_facts


def _candidate_data(candidate: object) -> dict[str, Any]:
    if hasattr(candidate, "model_dump"):
        dumped = candidate.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return candidate if isinstance(candidate, dict) else {}


def _pending_fact_type(value: object) -> PendingFactType:
    if isinstance(value, str):
        try:
            return PendingFactType(value)
        except ValueError:
            return PendingFactType.OTHER
    return PendingFactType.OTHER


def _candidate_key(
    fact_type: str,
    title: str,
    content: object,
) -> str:
    return json.dumps(
        {
            "fact_type": fact_type,
            "title": re.sub(r"\s+", "", title).casefold(),
            "content": content,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _chapter_segments(markdown: str) -> list[str]:
    body = markdown.strip()
    if not body:
        return ["空章节"]
    segments: list[str] = []
    current = ""
    for paragraph in _paragraphs(body):
        next_text = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(next_text) > _SEGMENT_CHAR_LIMIT and current:
            if current.startswith("#") and len(current) < 200:
                current = next_text
            else:
                segments.append(current)
                current = paragraph
        else:
            current = next_text
    if current:
        segments.append(current)
    return segments or ["空章节"]


def _chapter_source_ref(
    *,
    chapter_id: str,
    path: str,
    markdown: str,
) -> SourceRef:
    paragraphs = _paragraphs(markdown)
    excerpt = _plain_excerpt(markdown) or "空章节"
    if len(paragraphs) <= 1:
        anchor_type = (
            SourceAnchorType.PARAGRAPH if paragraphs else SourceAnchorType.DOCUMENT
        )
        paragraph_start = 0 if paragraphs else None
        paragraph_end = None
    else:
        anchor_type = SourceAnchorType.PARAGRAPH_RANGE
        paragraph_start = 0
        paragraph_end = len(paragraphs) - 1
    return SourceRef(
        source_type=SourceRefSourceType.CHAPTER,
        source_id=chapter_id,
        path=path,
        chapter_id=chapter_id,
        anchor_type=anchor_type,
        paragraph_start=paragraph_start,
        paragraph_end=paragraph_end,
        excerpt=excerpt,
        excerpt_hash=_sha256(excerpt),
        source_hash=_sha256(markdown),
        created_at=_now_iso(),
    )


def _paragraphs(markdown: str) -> list[str]:
    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", markdown.strip())
        if paragraph.strip()
    ]


def _is_empty_chapter(markdown: str) -> bool:
    body_lines = [
        line.strip()
        for line in markdown.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return not body_lines


def _plain_excerpt(markdown: str, limit: int = 240) -> str:
    text = re.sub(r"^#+\s*", "", markdown, flags=re.MULTILINE)
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip()


def _retrieval_query_text(markdown: str) -> str:
    return _plain_excerpt(markdown, 80)


def _clean_strings(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def _text_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
