"""Basic Agent Chat use case with source-aware AIResultCard output."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from taichu.application.agents.chat.prompts import build_chat_prompt
from taichu.application.contracts.llm import LLMContract
from taichu.application.contracts.retrieval import RetrievalContract, RetrievalQuery
from taichu.application.services.ai_card_service import AICardService
from taichu.application.services.chapter_service import (
    ChapterContent,
    ChapterService,
)
from taichu.application.services.knowledge_service import (
    KnowledgeService,
    knowledge_category_for_type,
)
from taichu.domain.models.agent_chat import AgentConversation
from taichu.domain.models.ai_card import (
    AIResultCard,
    AIResultCardStatus,
    AIResultCardType,
    AIWorkflow,
)
from taichu.domain.models.knowledge import KnowledgeCard
from taichu.domain.models.retrieval import RetrievalHit
from taichu.domain.models.source_ref import (
    SourceAnchorType,
    SourceRef,
    SourceRefSourceType,
)

_MAX_CHAPTER_EXCERPT = 1600
_MAX_CONFIRMED_FACTS = 8
_MAX_RETRIEVAL_HITS = 6


@dataclass(frozen=True)
class ChatAgentRequest:
    """Input for one Basic Agent Chat exchange."""

    message: str
    chapter_id: str | None = None
    include_current_chapter: bool = True
    include_confirmed_facts: bool = True


@dataclass(frozen=True)
class ChatAgentRunResult:
    """Persisted chat card plus conversation metadata."""

    conversation: AgentConversation
    card: AIResultCard


@dataclass(frozen=True)
class _ChatSource:
    source_ref: SourceRef
    prompt_line: str


class ChatAgentService:
    """Run source-aware Basic Agent Chat without writing fact assets."""

    def __init__(
        self,
        *,
        chapter_service: ChapterService,
        knowledge_service: KnowledgeService,
        retrieval: RetrievalContract,
        llm: LLMContract,
        ai_card_service: AICardService,
    ) -> None:
        self._chapter_service = chapter_service
        self._knowledge_service = knowledge_service
        self._retrieval = retrieval
        self._llm = llm
        self._ai_card_service = ai_card_service

    async def run(self, request: ChatAgentRequest) -> ChatAgentRunResult:
        """Generate one chat answer and persist it as an AIResultCard."""
        now = _now_iso()
        chapter_content = await self._selected_chapter(request)
        chapter_ref = (
            _chapter_source_ref(chapter_content, now)
            if chapter_content is not None
            else None
        )
        confirmed_cards = (
            (await self._knowledge_service.list_cards())[:_MAX_CONFIRMED_FACTS]
            if request.include_confirmed_facts
            else []
        )
        retrieval_hits = (
            await self._retrieval.search(
                RetrievalQuery(text=request.message, limit=_MAX_RETRIEVAL_HITS)
            )
            if request.include_confirmed_facts
            else []
        )

        sources = _dedupe_sources(
            [
                *(
                    [
                        _ChatSource(
                            source_ref=chapter_ref,
                            prompt_line=(
                                "当前章节"
                                f"《{chapter_content.chapter.title}》摘录：\n"
                                f"{_compact_excerpt(chapter_content.markdown, _MAX_CHAPTER_EXCERPT)}"
                            ),
                        )
                    ]
                    if chapter_ref is not None and chapter_content is not None
                    else []
                ),
                *[
                    _ChatSource(
                        source_ref=_knowledge_source_ref(card, now),
                        prompt_line=f"confirmed Knowledge：{_confirmed_fact_line(card)}",
                    )
                    for card in confirmed_cards
                ],
                *[
                    _ChatSource(
                        source_ref=hit.source_ref,
                        prompt_line=f"检索证据：{_retrieval_line(hit)}",
                    )
                    for hit in retrieval_hits
                ],
            ]
        )
        source_refs = [source.source_ref for source in sources]
        raw_answer = await self._llm.complete(
            build_chat_prompt(
                message=request.message,
                source_lines=[source.prompt_line for source in sources],
            )
        )
        card = await self._ai_card_service.create_card(
            AIResultCard(
                id=f"card_{uuid4().hex}",
                type=AIResultCardType.SUGGESTION,
                workflow=AIWorkflow.CHAT,
                status=AIResultCardStatus.GENERATED,
                chapter_id=(
                    chapter_content.chapter.id
                    if chapter_content is not None
                    else request.chapter_id
                ),
                input_context={
                    "agent": "chat",
                    "message": request.message,
                    "chapter_id": request.chapter_id,
                    "include_current_chapter": request.include_current_chapter,
                    "include_confirmed_facts": request.include_confirmed_facts,
                    "confirmed_fact_count": len(confirmed_cards),
                    "retrieval_hit_count": len(retrieval_hits),
                },
                content={
                    "answer": raw_answer,
                    "source_status": (
                        "source_backed" if source_refs else "speculative"
                    ),
                    "citations": [
                        _citation(ref, index)
                        for index, ref in enumerate(source_refs, start=1)
                    ],
                },
                source_refs=source_refs,
                created_at=now,
                updated_at=now,
            )
        )
        conversation = AgentConversation(
            id=f"conversation_{uuid4().hex}",
            agent_name="chat",
            message=request.message,
            chapter_id=card.chapter_id,
            used_current_chapter=chapter_content is not None,
            used_confirmed_facts=request.include_confirmed_facts,
            source_refs=source_refs,
            card_id=card.id,
            created_at=now,
        )
        return ChatAgentRunResult(conversation=conversation, card=card)

    async def _selected_chapter(
        self,
        request: ChatAgentRequest,
    ) -> ChapterContent | None:
        if not request.include_current_chapter:
            return None
        chapter_id = request.chapter_id
        if chapter_id is None:
            manifest = await self._chapter_service.get_manifest()
            chapter_id = manifest.current_chapter_id
            if chapter_id is None and manifest.chapters:
                chapter_id = sorted(
                    manifest.chapters,
                    key=lambda chapter: chapter.order,
                )[0].id
        if chapter_id is None:
            return None
        return await self._chapter_service.read_chapter(chapter_id)


def _confirmed_fact_line(card: KnowledgeCard) -> str:
    aliases = f"（别名：{'、'.join(card.aliases)}）" if card.aliases else ""
    return f"{card.name}{aliases}：{card.summary}"


def _retrieval_line(hit: RetrievalHit) -> str:
    return f"{hit.source_type.value}:{hit.source_id}：{hit.excerpt}"


def _chapter_source_ref(content: ChapterContent, created_at: str) -> SourceRef:
    paragraphs = _paragraphs(content.markdown)
    excerpt = _compact_excerpt(content.markdown) or content.chapter.title
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
        source_id=content.chapter.id,
        path=f"project_assets/source/{content.chapter.markdown_path}",
        chapter_id=content.chapter.id,
        anchor_type=anchor_type,
        paragraph_start=paragraph_start,
        paragraph_end=paragraph_end,
        excerpt=excerpt,
        excerpt_hash=_sha256(excerpt),
        source_hash=_sha256(content.markdown),
        created_at=created_at,
    )


def _knowledge_source_ref(card: KnowledgeCard, created_at: str) -> SourceRef:
    source_text = json.dumps(
        card.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
    )
    excerpt = _compact_excerpt(card.summary) or card.name
    return SourceRef(
        source_type=SourceRefSourceType.KNOWLEDGE,
        source_id=card.id,
        path=(
            "project_assets/source/knowledge/"
            f"{knowledge_category_for_type(card.type)}/{card.id}.json"
        ),
        anchor_type=SourceAnchorType.KNOWLEDGE_FIELD,
        field_path="summary",
        excerpt=excerpt,
        excerpt_hash=_sha256(excerpt),
        source_hash=_sha256(source_text),
        created_at=created_at,
    )


def _dedupe_sources(sources: list[_ChatSource]) -> list[_ChatSource]:
    deduped: list[_ChatSource] = []
    seen: set[tuple[object, ...]] = set()
    for source in sources:
        source_ref = source.source_ref
        key = (
            source_ref.source_type,
            source_ref.source_id,
            source_ref.path,
            source_ref.anchor_type,
            source_ref.paragraph_start,
            source_ref.paragraph_end,
            source_ref.field_path,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _citation(source_ref: SourceRef, index: int) -> dict[str, object]:
    return {
        "label": f"S{index}",
        "source_type": source_ref.source_type.value,
        "source_id": source_ref.source_id,
        "path": source_ref.path,
        "excerpt": source_ref.excerpt,
    }


def _paragraphs(markdown: str) -> list[str]:
    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", markdown.strip())
        if paragraph.strip()
    ]


def _compact_excerpt(text: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
