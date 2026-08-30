"""Unified real LLM workflow for writing-page AI buttons."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.output_parsers.openai_tools import (
    JsonOutputToolsParser,
    PydanticToolsParser,
)
from langchain_core.outputs import ChatGeneration
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ValidationError

from taichu.application.contracts.llm import (
    LLMModelCatalogContract,
    LLMModelProfile,
)
from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.application.invocations.config import model_call_config
from taichu.application.services.chapter_service import ChapterService
from taichu.application.vector_graph.models import (
    VectorGraphEvidence,
    VectorGraphIndexState,
)
from taichu.application.vector_graph.service import VectorGraphRAGService
from taichu.application.services.writing_ai_prompts import (
    PROMPT_VERSION,
    TAICHU_COMMON_SYSTEM_V1,
    WritingAIPromptRegistry,
)
from taichu.application.services.writing_ai_outputs import (
    ChapterSummaryOutput,
    ChatAnswerOutput,
    EvidenceAnswerOutput,
    InspirationOutput,
    PendingFactCandidatesOutput,
    PolishedTextOutput,
    SettingSuggestionOutput,
    TextCandidateOutput,
    WritingSuggestionOutput,
)
from taichu.domain.models import (
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

_OUTPUT_SCHEMAS: dict[WritingAIOutputType, type[BaseModel]] = {
    WritingAIOutputType.CHAT_ANSWER: ChatAnswerOutput,
    WritingAIOutputType.TEXT_CANDIDATE: TextCandidateOutput,
    WritingAIOutputType.POLISHED_TEXT: PolishedTextOutput,
    WritingAIOutputType.SETTING_SUGGESTION: SettingSuggestionOutput,
    WritingAIOutputType.WRITING_SUGGESTION: WritingSuggestionOutput,
    WritingAIOutputType.EVIDENCE_ANSWER: EvidenceAnswerOutput,
    WritingAIOutputType.CHAPTER_SUMMARY: ChapterSummaryOutput,
    WritingAIOutputType.INSPIRATION: InspirationOutput,
    WritingAIOutputType.PENDING_FACT_CANDIDATES: PendingFactCandidatesOutput,
}

_STREAM_PREVIEW_PATHS: dict[WritingAIOutputType, tuple[str | int, ...]] = {
    WritingAIOutputType.CHAT_ANSWER: ("answer",),
    WritingAIOutputType.TEXT_CANDIDATE: ("text",),
    WritingAIOutputType.POLISHED_TEXT: ("polished_text",),
    WritingAIOutputType.SETTING_SUGGESTION: (
        "setting_supplements",
        0,
        "content",
    ),
    WritingAIOutputType.WRITING_SUGGESTION: ("suggestions", 0, "action"),
    WritingAIOutputType.EVIDENCE_ANSWER: ("conclusion",),
    WritingAIOutputType.CHAPTER_SUMMARY: ("summary",),
    WritingAIOutputType.INSPIRATION: ("ideas", 0, "content"),
    WritingAIOutputType.PENDING_FACT_CANDIDATES: ("candidates", 0, "content"),
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
        retrieval_service: VectorGraphRAGService,
    ) -> None:
        self._chapter_service = chapter_service
        self._retrieval_service = retrieval_service

    async def build(
        self,
        command: WritingAICreateRunCommand,
        *,
        run_id: str | None = None,
    ) -> WritingAIContext:
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
            run_id=run_id,
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
        run_id: str | None,
    ) -> WritingAIRetrievalContext:
        query_text = "\n".join(
            part for part in (command.user_input, selected_text) if part.strip()
        )
        context_text = (
            chapter_excerpt or chapter_text[:3000]
            if command.reference_scope is not WritingAIReferenceScope.NONE
            else ""
        )
        del run_id
        retrieval_query = "\n".join(
            part
            for part in (
                query_text or _BUTTON_LABELS[command.button_type],
                context_text[:4_000],
            )
            if part.strip()
        )
        items: list[WritingAIRetrievalEvidenceItem] = []
        if chapter_excerpt.strip():
            items.append(_chapter_evidence_item(command, chapter_excerpt))
        try:
            status = await self._retrieval_service.status()
            if status.state is not VectorGraphIndexState.READY or not status.is_current:
                raise WritingAIError("Milvus 索引当前未就绪。")
            result = await asyncio.wait_for(
                self._retrieval_service.retrieve(retrieval_query, top_k=10),
                timeout=5,
            )
        except Exception:
            return WritingAIRetrievalContext(
                used=True,
                retrieval_id=None,
                strategy="milvus_hybrid_vector_graph",
                candidate_count=0,
                truncated=False,
                empty_reason="Milvus 索引当前不可用，本次仅使用已明确读取的章节正文",
                items=items,
                knowledge_context=(
                    "Milvus 索引当前不可用。模型只能使用本次明确读取的章节正文，"
                    "不得把未检索到的结构知识说成已确认事实。"
                ),
                evidence_context=_evidence_context(chapter_excerpt, items),
            )
        items.extend(_evidence_item(item) for item in result.evidences)
        if not result.evidences:
            empty_reason = "当前没有检索到可用的权威正文或已确认知识卡"
            return WritingAIRetrievalContext(
                used=True,
                retrieval_id=None,
                strategy="milvus_hybrid_vector_graph",
                candidate_count=0,
                truncated=False,
                empty_reason=empty_reason,
                items=items,
                knowledge_context=(
                    "当前没有检索到可用权威证据。模型不得把未检索到的内容说成已确认事实。"
                ),
                evidence_context=_evidence_context(chapter_excerpt, items),
            )
        return WritingAIRetrievalContext(
            used=True,
            retrieval_id=None,
            strategy="milvus_hybrid_vector_graph",
            candidate_count=len(result.evidences),
            truncated=False,
            empty_reason=None,
            items=items,
            knowledge_context="\n\n".join(
                _knowledge_context_block(index, item)
                for index, item in enumerate(result.evidences, start=1)
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
        retrieval_service: VectorGraphRAGService,
        llm: BaseChatModel,
        model_catalog: LLMModelCatalogContract,
        default_model_id: str,
        llm_configured: bool,
    ) -> None:
        self._storage = storage
        self._context_builder = WritingAIContextBuilder(
            chapter_service,
            retrieval_service,
        )
        self._llm = llm
        self._model_catalog = model_catalog
        self._default_model_id = default_model_id
        self._llm_configured = llm_configured
        self._prompt_registry = WritingAIPromptRegistry()

    async def create_run(self, command: WritingAICreateRunCommand) -> WritingAIRun:
        """Run the complete writing AI workflow and persist the trace."""
        _validate_scope(command.button_type, command.reference_scope)
        profile = _resolve_profile(
            self._model_catalog,
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
            context = await self._context_builder.build(command, run_id=run.run_id)
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
            raw_message, parsed_output = await self._invoke_structured(
                run,
                prompt_snapshot,
                command,
            )
            raw_output = _structured_response_payload(parsed_output)
            run = run.model_copy(
                update={
                    "raw_llm_output": raw_output,
                    **_response_updates(raw_message),
                    "updated_at": _now_iso(),
                }
            )
            await self._replace(run)
            run = await self._set_status(run, WritingAIRunStatus.PARSING)
            structured_output = _parse_structured_output(
                parsed_output,
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
        """执行写作任务并投影结构化结果中用户可见的主内容增量。"""
        _validate_scope(command.button_type, command.reference_scope)
        profile = _resolve_profile(
            self._model_catalog,
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
            context = await self._context_builder.build(command, run_id=run.run_id)
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
            output_type = self._prompt_registry.get(command.button_type).output_type
            output_schema = _OUTPUT_SCHEMAS[output_type]
            bound_model = self._llm.bind_tools(
                [output_schema],
                tool_choice=output_schema.__name__,
            ).bind(**_model_call_kwargs(run, command))
            final_response: AIMessage | AIMessageChunk | None = None
            preview_text = ""
            partial_parser = JsonOutputToolsParser(first_tool_only=True)
            async for chunk in bound_model.astream(
                _model_messages(prompt_snapshot),
                config=_model_config(run, command),
            ):
                if not isinstance(chunk, (AIMessage, AIMessageChunk)):
                    raise WritingAIError("模型流式输出返回了不支持的消息类型。")
                if final_response is None:
                    final_response = chunk
                elif isinstance(final_response, AIMessageChunk) and isinstance(
                    chunk, AIMessageChunk
                ):
                    final_response = final_response + chunk
                else:
                    raise WritingAIError("模型流式输出混用了完整消息与增量消息。")
                partial_call = partial_parser.parse_result(
                    [ChatGeneration(message=final_response)],
                    partial=True,
                )
                current_preview = _stream_preview_text(partial_call, output_type)
                if current_preview:
                    if not current_preview.startswith(preview_text):
                        raise WritingAIError(
                            "模型流式结构化正文发生非增量改写，请稍后重试。"
                        )
                    delta = current_preview[len(preview_text) :]
                    if delta:
                        yield {"type": "text_delta", "delta": delta}
                    preview_text = current_preview
                if chunk.usage_metadata is not None:
                    usage = chunk.usage_metadata
                    input_details = usage.get("input_token_details") or {}
                    output_details = usage.get("output_token_details") or {}
                    yield {
                        "type": "usage",
                        "input_tokens": usage.get("input_tokens"),
                        "cached_input_tokens": input_details.get("cache_read"),
                        "output_tokens": usage.get("output_tokens"),
                        "reasoning_tokens": output_details.get("reasoning"),
                        "total_tokens": usage.get("total_tokens"),
                    }
            if final_response is None:
                raise WritingAIError("模型流式输出中断，请稍后重试。")
            try:
                parsed_output = PydanticToolsParser(
                    tools=[output_schema],
                    first_tool_only=True,
                ).invoke(final_response)
            except Exception as error:
                raise WritingAIError(
                    "模型结构化输出不符合写作 AI 契约。"
                ) from error
            if parsed_output is None:
                raise WritingAIError("模型没有按要求提交写作结果。")
            raw_output = _structured_response_payload(parsed_output)
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
                parsed_output,
                output_type,
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
                "call_id": final_response.id,
            }
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, WritingAIError)
                else "模型调用失败，请稍后重试。"
            )
            await self._fail_run(run, message)
            yield {"type": "run_failed", "run_id": run.run_id, "message": message}

    async def _invoke_structured(
        self,
        run: WritingAIRun,
        prompt: WritingAIPromptSnapshot,
        command: WritingAICreateRunCommand,
    ) -> tuple[AIMessage, BaseModel]:
        output_type = self._prompt_registry.get(command.button_type).output_type
        output_schema = _OUTPUT_SCHEMAS[output_type]
        result = await self._llm.with_structured_output(
            output_schema,
            method="function_calling",
            strict=True,
            include_raw=True,
        ).ainvoke(
            _model_messages(prompt),
            config=_model_config(run, command),
        )
        if not isinstance(result, dict):
            raise WritingAIError("模型没有按原生结构化协议返回结果。")
        raw_message = result.get("raw")
        parsed_output = result.get("parsed")
        parsing_error = result.get("parsing_error")
        if parsing_error is not None:
            raise WritingAIError("模型结构化输出不符合写作 AI 契约。") from parsing_error
        if not isinstance(raw_message, AIMessage) or not isinstance(
            parsed_output, BaseModel
        ):
            raise WritingAIError("模型没有按原生结构化协议返回结果。")
        return raw_message, parsed_output

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
    response: BaseModel,
    expected_output_type: WritingAIOutputType,
) -> WritingAIStructuredOutput:
    try:
        parsed = (
            _OUTPUT_SCHEMAS[expected_output_type]
            .model_validate(response)
            .model_dump(mode="json")
        )
        content = {key: value for key, value in parsed.items() if key != "output_type"}
        return WritingAIStructuredOutput(
            output_type=expected_output_type,
            content=content,
        )
    except ValidationError as error:
        raise WritingAIError("模型结构化输出不符合写作 AI 契约。") from error


def _structured_response_payload(response: BaseModel) -> str:
    return response.model_dump_json()


def _stream_preview_text(
    partial_call: object,
    output_type: WritingAIOutputType,
) -> str:
    """从官方 partial tool parser 结果投影用户可见的主内容增量。"""

    if not isinstance(partial_call, dict):
        return ""
    value: object = partial_call.get("args")
    for segment in _STREAM_PREVIEW_PATHS[output_type]:
        if isinstance(segment, str) and isinstance(value, dict):
            value = value.get(segment)
        elif (
            isinstance(segment, int)
            and isinstance(value, list)
            and len(value) > segment
        ):
            value = value[segment]
        else:
            return ""
    return value if isinstance(value, str) else ""


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


def _evidence_item(evidence: VectorGraphEvidence) -> WritingAIRetrievalEvidenceItem:
    excerpt = evidence.context_content or evidence.content
    return WritingAIRetrievalEvidenceItem(
        item_id=f"{evidence.source_type.value}-{evidence.source_id}-{evidence.rank}",
        source_type=evidence.source_type.value,
        source_id=evidence.source_id,
        display_name=evidence.title,
        excerpt=excerpt[:300],
        usage="Milvus 混合检索并完成权威回源",
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
    item: VectorGraphEvidence,
) -> str:
    content = item.context_content or item.content
    return "\n".join(
        [
            f"【权威证据 {index}】",
            f"来源类型：{item.source_type.value}",
            f"标题：{item.title}",
            f"内容：{content}",
            f"来源引用：{item.context_source_ref or item.source_ref}",
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
    model_catalog: LLMModelCatalogContract,
    model_id: str,
    *,
    allow_disabled: bool = False,
) -> LLMModelProfile:
    for profile in model_catalog.list_models():
        if profile.id == model_id:
            if not profile.enabled and not allow_disabled:
                raise WritingAIError(
                    f"模型“{profile.display_name}”当前已停用，请选择其他模型。"
                )
            return profile
    raise WritingAIError("所选模型不存在，请刷新模型列表后重试。")


def _model_messages(
    prompt: WritingAIPromptSnapshot,
) -> list[BaseMessage]:
    return [
        SystemMessage(content=prompt.system_prompt),
        HumanMessage(content=prompt.user_prompt),
    ]


def _model_config(
    run: WritingAIRun,
    command: WritingAICreateRunCommand,
) -> RunnableConfig:
    return model_call_config(
        model_id=run.model_id,
        task_type=f"writing_{command.button_type.value}",
        task_name=run.button_label,
        run_id=run.run_id,
        chapter_ids=(run.chapter_id,),
        feature="写作 AI",
    )


def _model_call_kwargs(
    run: WritingAIRun,
    command: WritingAICreateRunCommand,
) -> dict[str, object]:
    """流式模型钩子通过 Runnable 绑定接收请求设置。"""
    return {
        "model_id": run.model_id,
        "task_type": f"writing_{command.button_type.value}",
        "task_name": run.button_label,
        "taichu_run_id": run.run_id,
        "chapter_ids": (run.chapter_id,),
        "feature": "写作 AI",
    }


def _response_updates(
    response: AIMessage | AIMessageChunk,
) -> dict[str, object]:
    usage: dict[str, Any] = dict(response.usage_metadata or {})
    input_details = usage.get("input_token_details") or {}
    output_details = usage.get("output_token_details") or {}
    metadata = response.response_metadata
    return {
        "llm_call_id": response.id,
        "input_tokens": usage.get("input_tokens"),
        "cached_input_tokens": input_details.get("cache_read"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": output_details.get("reasoning"),
        "total_tokens": usage.get("total_tokens"),
        "cost_amount": metadata.get("cost_amount"),
        "cost_currency": metadata.get("cost_currency", "CNY"),
        "cost_kind": metadata.get("cost_kind", "unavailable"),
    }
