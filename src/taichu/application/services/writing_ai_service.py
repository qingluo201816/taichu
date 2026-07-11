"""Unified real LLM workflow for writing-page AI buttons."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)
from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMMessage,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    response_text,
)
from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.writing_ai_prompts import (
    PROMPT_VERSION,
    TAICHU_COMMON_SYSTEM_V1,
    WritingAIPromptRegistry,
)
from taichu.domain.models import (
    StructuredKnowledgeCard,
    WritingAIButtonType,
    WritingAIInput,
    WritingAIOutputType,
    WritingAIPromptSnapshot,
    WritingAIReferenceScope,
    WritingAIRetrievalContext,
    WritingAIRetrievalEvidenceItem,
    WritingAIRun,
    WritingAIRunStatus,
    WritingAISelectionRange,
    WritingAIStructuredOutput,
    knowledge_type_label,
)

WRITING_AI_RUNS_FILE = "writing_ai_runs.jsonl"
MODEL_NOT_CONFIGURED_MESSAGE = "当前未配置可用模型，无法调用真实 LLM。"

_BUTTON_LABELS: dict[WritingAIButtonType, str] = {
    WritingAIButtonType.CHAT: "纯对话",
    WritingAIButtonType.CONTINUE: "续写",
    WritingAIButtonType.POLISH: "润色",
    WritingAIButtonType.SETTING: "设定",
    WritingAIButtonType.SUGGESTION: "建议",
    WritingAIButtonType.EVIDENCE: "证据",
    WritingAIButtonType.CHAPTER_SUMMARY: "章节摘要",
    WritingAIButtonType.INSPIRATION: "灵感",
    WritingAIButtonType.FACT: "事实",
}

_SCOPE_LABELS: dict[WritingAIReferenceScope, str] = {
    WritingAIReferenceScope.NONE: "无小说上下文",
    WritingAIReferenceScope.SELECTION: "选区",
    WritingAIReferenceScope.CHAPTER: "本章",
    WritingAIReferenceScope.FULL_TEXT: "全文",
}

_ALLOWED_SCOPES: dict[WritingAIButtonType, set[WritingAIReferenceScope]] = {
    WritingAIButtonType.CHAT: {WritingAIReferenceScope.NONE},
    WritingAIButtonType.CONTINUE: {
        WritingAIReferenceScope.CHAPTER,
        WritingAIReferenceScope.SELECTION,
    },
    WritingAIButtonType.POLISH: {WritingAIReferenceScope.SELECTION},
    WritingAIButtonType.SETTING: {
        WritingAIReferenceScope.SELECTION,
        WritingAIReferenceScope.CHAPTER,
        WritingAIReferenceScope.FULL_TEXT,
    },
    WritingAIButtonType.SUGGESTION: {
        WritingAIReferenceScope.SELECTION,
        WritingAIReferenceScope.CHAPTER,
        WritingAIReferenceScope.FULL_TEXT,
    },
    WritingAIButtonType.EVIDENCE: {
        WritingAIReferenceScope.CHAPTER,
        WritingAIReferenceScope.FULL_TEXT,
    },
    WritingAIButtonType.CHAPTER_SUMMARY: {WritingAIReferenceScope.CHAPTER},
    WritingAIButtonType.INSPIRATION: {
        WritingAIReferenceScope.SELECTION,
        WritingAIReferenceScope.CHAPTER,
    },
    WritingAIButtonType.FACT: {
        WritingAIReferenceScope.SELECTION,
        WritingAIReferenceScope.CHAPTER,
    },
}


@dataclass(frozen=True)
class WritingAIContext:
    """Rendered context pieces used by the prompt and run trace."""

    chapter_id: str
    chapter_title: str
    user_input: str
    selected_text: str
    before_selection: str
    after_selection: str
    chapter_excerpt: str
    target_words: str
    retrieval_context: WritingAIRetrievalContext


@dataclass(frozen=True)
class WritingAICreateRunCommand:
    """Application command for creating one writing AI run."""

    button_type: WritingAIButtonType
    chapter_id: str
    reference_scope: WritingAIReferenceScope
    user_input: str = ""
    selected_text: str = ""
    selection_range: WritingAISelectionRange | None = None
    target_words: int | None = None
    draft_chapter_text: str | None = None
    model_id: str | None = None


@dataclass(frozen=True)
class WritingAIListFilters:
    """Filters supported by writing AI history."""

    chapter_id: str | None = None
    button_type: WritingAIButtonType | None = None
    status: WritingAIRunStatus | None = None


class WritingAIContextBuilder:
    """Build chapter and active-knowledge context for every AI button."""

    def __init__(
        self,
        chapter_service: ChapterService,
        knowledge_repository: StructuredKnowledgeRepository,
    ) -> None:
        self._chapter_service = chapter_service
        self._knowledge_repository = knowledge_repository

    async def build(self, command: WritingAICreateRunCommand) -> WritingAIContext:
        """Read chapter and active knowledge before an LLM call."""
        chapter_content = await self._chapter_service.read_chapter(command.chapter_id)
        chapter_text = command.draft_chapter_text
        if chapter_text is None:
            chapter_text = chapter_content.markdown
        selected_text = command.selected_text.strip()
        before_selection, after_selection = _selection_context(
            chapter_text,
            selected_text,
            command.selection_range,
        )
        chapter_excerpt = _chapter_excerpt(chapter_text, command.reference_scope)
        retrieval_context = await self._build_retrieval_context(
            command=command,
            chapter_text=chapter_text,
            selected_text=selected_text,
            chapter_excerpt=chapter_excerpt,
        )
        return WritingAIContext(
            chapter_id=chapter_content.chapter.id,
            chapter_title=chapter_content.chapter.title,
            user_input=command.user_input.strip(),
            selected_text=selected_text,
            before_selection=before_selection,
            after_selection=after_selection,
            chapter_excerpt=chapter_excerpt,
            target_words=str(command.target_words or 500),
            retrieval_context=retrieval_context,
        )

    async def _build_retrieval_context(
        self,
        *,
        command: WritingAICreateRunCommand,
        chapter_text: str,
        selected_text: str,
        chapter_excerpt: str,
    ) -> WritingAIRetrievalContext:
        cards = await self._knowledge_repository.list_active_cards()
        corpus = _retrieval_corpus(command, selected_text, chapter_excerpt, chapter_text)
        query_terms = _query_terms(command.user_input, selected_text)
        items: list[WritingAIRetrievalEvidenceItem] = []
        if chapter_excerpt.strip():
            items.append(_chapter_evidence_item(command, chapter_excerpt))
        knowledge_items: list[WritingAIRetrievalEvidenceItem] = []
        for card in cards:
            reason = _match_reason(card, corpus, query_terms)
            if not reason:
                continue
            knowledge_items.append(_evidence_item(card, reason))
            if len(knowledge_items) >= 12:
                break
        items.extend(knowledge_items)
        if not knowledge_items:
            empty_reason = "当前没有检索到可用有效知识卡"
            return WritingAIRetrievalContext(
                used=True,
                empty_reason=empty_reason,
                items=items,
                knowledge_context=(
                    "当前没有检索到可用有效知识卡。模型不得把未检索到的内容说成已确认事实。"
                ),
                evidence_context=_evidence_context(chapter_excerpt, items),
            )
        return WritingAIRetrievalContext(
            used=True,
            empty_reason=None,
            items=items,
            knowledge_context="\n\n".join(
                _knowledge_context_block(index, item, cards)
                for index, item in enumerate(knowledge_items, start=1)
            ),
            evidence_context=_evidence_context(chapter_excerpt, items),
        )


class WritingAIService:
    """Create, persist, list and replay writing-page AI runs."""

    def __init__(
        self,
        *,
        storage: ProjectAssetStorageContract,
        chapter_service: ChapterService,
        knowledge_repository: StructuredKnowledgeRepository,
        llm: LLMGatewayContract,
        default_model_id: str,
        llm_configured: bool,
    ) -> None:
        self._storage = storage
        self._context_builder = WritingAIContextBuilder(
            chapter_service,
            knowledge_repository,
        )
        self._llm = llm
        self._default_model_id = default_model_id
        self._llm_configured = llm_configured
        self._prompt_registry = WritingAIPromptRegistry()

    async def create_run(self, command: WritingAICreateRunCommand) -> WritingAIRun:
        """Run the complete writing AI workflow and persist the trace."""
        _validate_scope(command.button_type, command.reference_scope)
        profile = _resolve_profile(
            self._llm,
            command.model_id or self._default_model_id,
            allow_disabled=not self._llm_configured,
        )
        now = _now_iso()
        run = WritingAIRun(
            run_id=_new_run_id(),
            status=WritingAIRunStatus.QUEUED,
            button_type=command.button_type,
            button_label=_BUTTON_LABELS[command.button_type],
            model=profile.display_name,
            model_id=profile.id,
            model_display_name=profile.display_name,
            upstream_model=profile.upstream_model,
            wire_protocol=profile.wire_protocol,
            chapter_id=command.chapter_id,
            reference_scope=command.reference_scope,
            input=WritingAIInput(
                user_input=command.user_input,
                selected_text=command.selected_text,
                selection_range=command.selection_range,
                target_words=command.target_words,
                draft_chapter_text=command.draft_chapter_text,
            ),
            created_at=now,
            updated_at=now,
        )
        await self._append(run)
        run = await self._set_status(run, WritingAIRunStatus.RETRIEVING)
        try:
            context = await self._context_builder.build(command)
            run = run.model_copy(
                update={
                    "chapter_title": context.chapter_title,
                    "retrieval_context": context.retrieval_context,
                    "updated_at": _now_iso(),
                }
            )
            await self._replace(run)
            prompt_snapshot = self._render_prompt(command, context)
            run = run.model_copy(
                update={"prompt_snapshot": prompt_snapshot, "updated_at": _now_iso()}
            )
            await self._replace(run)
            if not self._llm_configured:
                return await self._fail_run(run, MODEL_NOT_CONFIGURED_MESSAGE)
            run = await self._set_status(run, WritingAIRunStatus.CALLING_LLM)
            llm_response = await self._llm.complete(
                _llm_request(run, prompt_snapshot, command)
            )
            raw_output = response_text(llm_response)
            run = run.model_copy(
                update={
                    "raw_llm_output": raw_output,
                    **_response_updates(llm_response),
                    "updated_at": _now_iso(),
                }
            )
            await self._replace(run)
            run = await self._set_status(run, WritingAIRunStatus.PARSING)
            structured_output = _parse_structured_output(
                raw_output,
                self._prompt_registry.get(command.button_type).output_type,
            )
            completed = run.model_copy(
                update={
                    "status": WritingAIRunStatus.COMPLETED,
                    "structured_output": structured_output,
                    "error": None,
                    "updated_at": _now_iso(),
                }
            )
            await self._replace(completed)
            return completed
        except Exception as error:
            if isinstance(error, WritingAIError):
                message = str(error)
            else:
                message = f"写作 AI 运行失败：{error}"
            return await self._fail_run(run, message)

    async def stream_run(self, command: WritingAICreateRunCommand):
        """执行写作任务并输出 NDJSON 所需的增量事件。"""
        _validate_scope(command.button_type, command.reference_scope)
        profile = _resolve_profile(
            self._llm,
            command.model_id or self._default_model_id,
            allow_disabled=not self._llm_configured,
        )
        now = _now_iso()
        run = WritingAIRun(
            run_id=_new_run_id(),
            status=WritingAIRunStatus.QUEUED,
            button_type=command.button_type,
            button_label=_BUTTON_LABELS[command.button_type],
            model=profile.display_name,
            model_id=profile.id,
            model_display_name=profile.display_name,
            upstream_model=profile.upstream_model,
            wire_protocol=profile.wire_protocol,
            chapter_id=command.chapter_id,
            reference_scope=command.reference_scope,
            input=WritingAIInput(
                user_input=command.user_input,
                selected_text=command.selected_text,
                selection_range=command.selection_range,
                target_words=command.target_words,
                draft_chapter_text=command.draft_chapter_text,
            ),
            created_at=now,
            updated_at=now,
        )
        await self._append(run)
        yield {"type": "run_started", "run_id": run.run_id, "model_id": profile.id}
        try:
            run = await self._set_status(run, WritingAIRunStatus.RETRIEVING)
            context = await self._context_builder.build(command)
            prompt_snapshot = self._render_prompt(command, context)
            run = run.model_copy(
                update={
                    "chapter_title": context.chapter_title,
                    "retrieval_context": context.retrieval_context,
                    "prompt_snapshot": prompt_snapshot,
                    "updated_at": _now_iso(),
                }
            )
            await self._replace(run)
            if not self._llm_configured:
                raise WritingAIError(MODEL_NOT_CONFIGURED_MESSAGE)
            run = await self._set_status(run, WritingAIRunStatus.CALLING_LLM)
            raw_parts: list[str] = []
            final_response: LLMResponse | None = None
            async for event in self._llm.stream(
                _llm_request(run, prompt_snapshot, command)
            ):
                if event.event_type == "text_delta":
                    raw_parts.append(event.delta)
                    yield {"type": "text_delta", "delta": event.delta}
                elif event.event_type == "usage" and event.usage is not None:
                    yield {
                        "type": "usage",
                        "input_tokens": event.usage.input_tokens,
                        "cached_input_tokens": event.usage.cached_input_tokens,
                        "output_tokens": event.usage.output_tokens,
                        "reasoning_tokens": event.usage.reasoning_tokens,
                        "total_tokens": event.usage.total_tokens,
                    }
                elif event.event_type == "completed":
                    final_response = event.response
                elif event.event_type == "failed":
                    raise WritingAIError(event.error or "模型调用失败，请稍后重试。")
            if final_response is None:
                raise WritingAIError("模型流式输出中断，请稍后重试。")
            raw_output = "".join(raw_parts) or final_response.text
            run = run.model_copy(
                update={
                    "raw_llm_output": raw_output,
                    **_response_updates(final_response),
                    "updated_at": _now_iso(),
                }
            )
            await self._replace(run)
            run = await self._set_status(run, WritingAIRunStatus.PARSING)
            structured_output = _parse_structured_output(
                raw_output,
                self._prompt_registry.get(command.button_type).output_type,
            )
            run = run.model_copy(
                update={
                    "status": WritingAIRunStatus.COMPLETED,
                    "structured_output": structured_output,
                    "error": None,
                    "updated_at": _now_iso(),
                }
            )
            await self._replace(run)
            yield {
                "type": "run_completed",
                "run_id": run.run_id,
                "call_id": final_response.call_id,
            }
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, WritingAIError)
                else "模型调用失败，请稍后重试。"
            )
            await self._fail_run(run, message)
            yield {"type": "run_failed", "run_id": run.run_id, "message": message}

    async def list_runs(
        self,
        *,
        filters: WritingAIListFilters | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[WritingAIRun], int]:
        """List saved writing AI runs newest first."""
        runs = [
            WritingAIRun.model_validate(record)
            for record in await self._storage.list_workspace_records(
                WRITING_AI_RUNS_FILE
            )
        ]
        if filters:
            if filters.chapter_id:
                runs = [run for run in runs if run.chapter_id == filters.chapter_id]
            if filters.button_type:
                runs = [run for run in runs if run.button_type is filters.button_type]
            if filters.status:
                runs = [run for run in runs if run.status is filters.status]
        runs = sorted(runs, key=lambda run: run.updated_at, reverse=True)
        start = (page - 1) * page_size
        return runs[start : start + page_size], len(runs)

    async def get_run(self, run_id: str) -> WritingAIRun:
        """Read one writing AI run by id."""
        for run in await self._all_runs():
            if run.run_id == run_id:
                return run
        raise WritingAIRunNotFoundError(run_id)

    async def replay_run(self, run_id: str) -> WritingAIRun:
        """Replay only returns the saved trace and never calls the LLM."""
        return await self.get_run(run_id)

    async def _append(self, run: WritingAIRun) -> None:
        await self._storage.append_workspace_record(
            WRITING_AI_RUNS_FILE,
            run.model_dump(mode="json"),
        )

    async def _replace(self, updated: WritingAIRun) -> None:
        records = await self._storage.list_workspace_records(WRITING_AI_RUNS_FILE)
        rewritten: list[dict[str, object]] = []
        replaced = False
        for record in records:
            run = WritingAIRun.model_validate(record)
            if run.run_id == updated.run_id:
                rewritten.append(updated.model_dump(mode="json"))
                replaced = True
            else:
                rewritten.append(run.model_dump(mode="json"))
        if not replaced:
            raise WritingAIRunNotFoundError(updated.run_id)
        await self._storage.rewrite_workspace_records(
            WRITING_AI_RUNS_FILE,
            rewritten,
        )

    async def _all_runs(self) -> list[WritingAIRun]:
        return [
            WritingAIRun.model_validate(record)
            for record in await self._storage.list_workspace_records(
                WRITING_AI_RUNS_FILE
            )
        ]

    async def _set_status(
        self,
        run: WritingAIRun,
        status: WritingAIRunStatus,
    ) -> WritingAIRun:
        updated = run.model_copy(update={"status": status, "updated_at": _now_iso()})
        await self._replace(updated)
        return updated

    async def _fail_run(self, run: WritingAIRun, message: str) -> WritingAIRun:
        failed = run.model_copy(
            update={
                "status": WritingAIRunStatus.FAILED,
                "error": message,
                "updated_at": _now_iso(),
            }
        )
        await self._replace(failed)
        return failed

    def _render_prompt(
        self,
        command: WritingAICreateRunCommand,
        context: WritingAIContext,
    ) -> WritingAIPromptSnapshot:
        variables = {
            "button_label": _BUTTON_LABELS[command.button_type],
            "reference_scope_label": _SCOPE_LABELS[command.reference_scope],
            "chapter_id": context.chapter_id,
            "chapter_title": context.chapter_title,
            "user_input": context.user_input,
            "selected_text": context.selected_text,
            "before_selection": context.before_selection,
            "after_selection": context.after_selection,
            "chapter_excerpt": context.chapter_excerpt,
            "knowledge_context": context.retrieval_context.knowledge_context,
            "evidence_context": context.retrieval_context.evidence_context,
            "target_words": context.target_words,
        }
        template = self._prompt_registry.get(command.button_type)
        user_prompt = self._prompt_registry.render_user_prompt(
            command.button_type,
            variables,
        )
        return WritingAIPromptSnapshot(
            prompt_id=template.prompt_id,
            prompt_version=PROMPT_VERSION,
            system_prompt=TAICHU_COMMON_SYSTEM_V1,
            user_prompt=user_prompt,
            rendered_at=_now_iso(),
        )


class WritingAIError(ValueError):
    """Raised when writing AI workflow data violates the taskpack contract."""


class WritingAIRunNotFoundError(LookupError):
    """Raised when a writing AI run id is not found."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"写作 AI 运行“{run_id}”不存在")


def _validate_scope(
    button_type: WritingAIButtonType,
    reference_scope: WritingAIReferenceScope,
) -> None:
    if reference_scope not in _ALLOWED_SCOPES[button_type]:
        raise WritingAIError("当前功能入口不支持这个正文参考范围。")


def _parse_structured_output(
    raw_output: str,
    expected_output_type: WritingAIOutputType,
) -> WritingAIStructuredOutput:
    try:
        parsed = json.loads(_strip_json_fence(raw_output))
    except json.JSONDecodeError as error:
        raise WritingAIError("模型返回内容不是合法 JSON，已保存原始输出。") from error
    if not isinstance(parsed, dict):
        raise WritingAIError("模型返回 JSON 必须是对象。")
    output_type_value = parsed.get("output_type")
    if output_type_value != expected_output_type.value:
        raise WritingAIError("模型返回的输出类型不符合当前入口契约。")
    content = {key: value for key, value in parsed.items() if key != "output_type"}
    try:
        return WritingAIStructuredOutput(
            output_type=expected_output_type,
            content=content,
        )
    except ValidationError as error:
        raise WritingAIError("模型结构化输出不符合写作 AI 契约。") from error


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _selection_context(
    chapter_text: str,
    selected_text: str,
    selection_range: WritingAISelectionRange | None,
) -> tuple[str, str]:
    if not selected_text:
        return "", ""
    start = selection_range.char_start if selection_range else None
    end = selection_range.char_end if selection_range else None
    if start is None or end is None or start < 0 or end < start:
        found_at = chapter_text.find(selected_text)
        if found_at == -1:
            return "", ""
        start = found_at
        end = found_at + len(selected_text)
    before = chapter_text[max(0, start - 1200) : start]
    after = chapter_text[end : end + 1200]
    return before.strip(), after.strip()


def _chapter_excerpt(
    chapter_text: str,
    reference_scope: WritingAIReferenceScope,
) -> str:
    if reference_scope is WritingAIReferenceScope.NONE:
        return ""
    if len(chapter_text) <= 6000:
        return chapter_text
    return f"{chapter_text[:3000]}\n\n……\n\n{chapter_text[-3000:]}"


def _retrieval_corpus(
    command: WritingAICreateRunCommand,
    selected_text: str,
    chapter_excerpt: str,
    chapter_text: str,
) -> str:
    parts = [command.user_input, selected_text]
    if command.reference_scope is not WritingAIReferenceScope.NONE:
        parts.append(chapter_excerpt or chapter_text[:3000])
    return "\n".join(part for part in parts if part)


def _query_terms(user_input: str, selected_text: str) -> set[str]:
    text = f"{user_input}\n{selected_text}"
    terms = {
        item.casefold()
        for item in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]{2,24}", text)
    }
    return {term for term in terms if len(term.strip()) >= 2}


def _match_reason(
    card: StructuredKnowledgeCard,
    corpus: str,
    query_terms: set[str],
) -> str | None:
    compact_corpus = "".join(corpus.split()).casefold()
    for value in [card.name, *card.aliases]:
        normalized = "".join(value.split()).casefold()
        if normalized and normalized in compact_corpus:
            return f"正文或输入命中名称“{value}”"
    card_text = _card_search_text(card)
    for term in query_terms:
        if term in card_text:
            return f"用户输入或选区命中知识卡内容“{term}”"
    return None


def _card_search_text(card: StructuredKnowledgeCard) -> str:
    payload = card.model_dump(mode="json", exclude_none=True)
    return " ".join(str(value) for value in payload.values()).casefold()


def _evidence_item(
    card: StructuredKnowledgeCard,
    reason: str,
) -> WritingAIRetrievalEvidenceItem:
    type_label = knowledge_type_label(card.type)
    excerpt = card.summary or card.source_note
    return WritingAIRetrievalEvidenceItem(
        item_id=f"knowledge-{card.id}",
        source_type="knowledge",
        source_id=card.id,
        display_name=f"{type_label}：{card.name}",
        excerpt=excerpt[:300],
        usage=reason,
    )


def _chapter_evidence_item(
    command: WritingAICreateRunCommand,
    chapter_excerpt: str,
) -> WritingAIRetrievalEvidenceItem:
    scope_label = _SCOPE_LABELS[command.reference_scope]
    return WritingAIRetrievalEvidenceItem(
        item_id=f"chapter-{command.chapter_id}",
        source_type="chapter",
        source_id=command.chapter_id,
        display_name=f"当前章节（{scope_label}）",
        excerpt=chapter_excerpt[:300],
        usage="当前章节正文上下文",
    )


def _knowledge_context_block(
    index: int,
    item: WritingAIRetrievalEvidenceItem,
    cards: list[StructuredKnowledgeCard],
) -> str:
    card = next((candidate for candidate in cards if candidate.id == item.source_id), None)
    if card is None:
        return ""
    type_label = knowledge_type_label(card.type)
    return "\n".join(
        [
            f"【知识 {index}】",
            f"类型：{type_label}",
            f"名称：{card.name}",
            f"摘要：{card.summary}",
            f"重要程度：{card.importance.value}",
            f"来源说明：{card.source_note}",
            f"命中原因：{item.usage}",
        ]
    )


def _chapter_evidence_context(chapter_excerpt: str) -> str:
    if not chapter_excerpt.strip():
        return "当前入口未注入章节正文。"
    return f"当前章节正文节选已注入 Prompt，长度约 {len(chapter_excerpt)} 字。"


def _evidence_context(
    chapter_excerpt: str,
    items: list[WritingAIRetrievalEvidenceItem],
) -> str:
    return "\n".join(
        [
            _chapter_evidence_context(chapter_excerpt),
            *(
                f"【来源 {index}】{item.display_name}：{item.excerpt}"
                for index, item in enumerate(items, start=1)
            ),
        ]
    ).strip()


def _new_run_id() -> str:
    now = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"writing-ai-run-{now}-{uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _resolve_profile(
    llm: LLMGatewayContract, model_id: str, *, allow_disabled: bool = False
) -> LLMModelProfile:
    if not hasattr(llm, "list_models"):
        return LLMModelProfile(
            id=model_id,
            display_name=model_id,
            provider="rightcode",
            upstream_model=model_id,
            wire_protocol="openai_responses",
            base_url_key="RIGHTCODE_RESPONSES_BASE_URL",
            enabled=True,
            is_default=True,
            supports_streaming=False,
        )
    for profile in llm.list_models():
        if profile.id == model_id:
            if not profile.enabled and not allow_disabled:
                raise WritingAIError(
                    f"模型“{profile.display_name}”当前已停用，请选择其他模型。"
                )
            return profile
    raise WritingAIError("所选模型不存在，请刷新模型列表后重试。")


def _llm_request(
    run: WritingAIRun,
    prompt: WritingAIPromptSnapshot,
    command: WritingAICreateRunCommand,
) -> LLMRequest:
    return LLMRequest(
        model_id=run.model_id,
        messages=(
            LLMMessage(role="system", content=prompt.system_prompt),
            LLMMessage(role="user", content=prompt.user_prompt),
        ),
        task_type=f"writing_{command.button_type.value}",
        task_name=run.button_label,
        run_id=run.run_id,
        chapter_ids=(run.chapter_id,),
        response_mode="json",
        feature="写作 AI",
    )


def _response_updates(response: LLMResponse | str) -> dict[str, object]:
    if not isinstance(response, LLMResponse):
        return {}
    return {
        "llm_call_id": response.call_id,
        "input_tokens": response.usage.input_tokens,
        "cached_input_tokens": response.usage.cached_input_tokens,
        "output_tokens": response.usage.output_tokens,
        "reasoning_tokens": response.usage.reasoning_tokens,
        "total_tokens": response.usage.total_tokens,
        "cost_amount": response.cost.amount,
        "cost_currency": response.cost.currency,
        "cost_kind": response.cost.kind,
    }
