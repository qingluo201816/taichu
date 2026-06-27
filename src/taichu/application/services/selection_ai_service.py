"""Selection AI workflow service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from taichu.application.contracts.llm import LLMContract
from taichu.application.services.ai_card_service import AICardService
from taichu.application.workflows.selection.schemas import SelectionWorkflowInput
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
from taichu.domain.models.source_ref import SourceRef


class SelectionMode(StrEnum):
    """Selection AI modes exposed by the editor workflow."""

    ASK = "ask"
    ENRICH_SETTING = "enrich_setting"
    CONTINUE_TEXT = "continue_text"


@dataclass(frozen=True)
class SelectionAIRequest:
    """Input to SelectionAIService from the API layer."""

    mode: SelectionMode
    chapter_id: str
    selected_text: str
    surrounding_text: str
    selection_ref: SourceRef
    selection_range: dict[str, int] | None = None
    user_prompt: str | None = None
    target_words: int | None = None
    parent_card_id: str | None = None


class SelectionAIService:
    """Application service for editor selection AI workflows."""

    def __init__(
        self,
        llm: LLMContract,
        ai_card_service: AICardService,
    ) -> None:
        self._llm = llm
        self._ai_card_service = ai_card_service

    async def run_selection(self, request: SelectionAIRequest) -> AIResultCard:
        """Generate and persist one AIResultCard for selected text."""
        workflow = _workflow_for_mode(request.mode)
        selection_input = SelectionWorkflowInput(
            workflow=workflow,
            chapter_id=request.chapter_id,
            selected_text=request.selected_text,
            selection_ref=request.selection_ref,
            prompt=request.user_prompt,
            target_word_count=request.target_words,
            context={
                "surrounding_text": request.surrounding_text,
                "mode": request.mode.value,
                "parent_card_id": request.parent_card_id,
            },
        )

        if request.parent_card_id:
            await self._ai_card_service.mark_retried(request.parent_card_id)

        prompt = build_selection_prompt(request)
        raw_output = await self._llm.complete(prompt)
        card = self._build_card(
            request=request,
            selection_input=selection_input,
            raw_output=raw_output,
        )
        return await self._ai_card_service.create_card(card)

    def _build_card(
        self,
        *,
        request: SelectionAIRequest,
        selection_input: SelectionWorkflowInput,
        raw_output: str,
    ) -> AIResultCard:
        now = _now_iso()
        parsed = _parse_json_object(raw_output)
        if parsed is None:
            card_type = AIResultCardType.SUGGESTION
            content: dict[str, Any] | str = {
                "title": "智能助手输出解析失败",
                "body": "模型没有返回结构化 JSON，本次结果已降级为建议卡。",
                "raw_text": raw_output,
            }
        else:
            card_type = _card_type_for_response(request.mode, parsed)
            content = _content_for_card_type(
                card_type=card_type,
                parsed=parsed,
                request=request,
                created_at=now,
            )

        return AIResultCard(
            id=f"card_{uuid4().hex}",
            type=card_type,
            workflow=selection_input.workflow,
            status=AIResultCardStatus.GENERATED,
            chapter_id=request.chapter_id,
            input_context={
                "mode": request.mode.value,
                "chapter_id": request.chapter_id,
                "selected_text": request.selected_text,
                "surrounding_text": request.surrounding_text,
                "selection_range": request.selection_range,
                "selection_ref": request.selection_ref.model_dump(mode="json"),
                "user_prompt": request.user_prompt,
                "target_words": request.target_words,
            },
            content=content,
            source_refs=[request.selection_ref],
            parent_card_id=request.parent_card_id,
            created_at=now,
            updated_at=now,
        )


def build_selection_prompt(request: SelectionAIRequest) -> str:
    """Build the strict JSON prompt for Selection AI."""
    mode_instruction = {
        SelectionMode.ASK: (
            "返回 suggestion 卡。给出面向作者的建议，不直接改写正文。"
        ),
        SelectionMode.ENRICH_SETTING: (
            "返回 suggestion 或 pending_fact 卡。若提出新设定，只能作为待确认候选。"
        ),
        SelectionMode.CONTINUE_TEXT: (
            "返回 text_candidate 卡。content.text 只写可插入正文，不解释、不跳剧情。"
        ),
    }[request.mode]
    target_line = (
        f"目标字数：约 {request.target_words} 字。"
        if request.target_words is not None
        else "目标字数：未指定。"
    )
    user_prompt = request.user_prompt or ""
    return "\n".join(
        [
            "你是太初编辑器内的选区智能助手工作流。",
            mode_instruction,
            target_line,
            "必须只返回一个 JSON object，不要 Markdown 代码块。",
            (
                'JSON 形状：{"card_type":"suggestion|text_candidate|pending_fact",'
                '"content":{...}}'
            ),
            f"章节：{request.chapter_id}",
            f"选中文本：{request.selected_text}",
            f"周边上下文：{request.surrounding_text}",
            f"作者提示：{user_prompt}",
        ]
    )


def _workflow_for_mode(mode: SelectionMode) -> AIWorkflow:
    if mode is SelectionMode.ASK:
        return AIWorkflow.ASK_SELECTION
    if mode is SelectionMode.ENRICH_SETTING:
        return AIWorkflow.ENRICH_SETTING
    return AIWorkflow.CONTINUE_TEXT


def _parse_json_object(raw_output: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _card_type_for_response(
    mode: SelectionMode,
    parsed: dict[str, Any],
) -> AIResultCardType:
    raw_card_type = parsed.get("card_type")
    if isinstance(raw_card_type, str):
        try:
            parsed_type = AIResultCardType(raw_card_type)
        except ValueError:
            parsed_type = _default_card_type(mode)
        else:
            if _card_type_allowed_for_mode(mode, parsed_type):
                return parsed_type
    return _default_card_type(mode)


def _default_card_type(mode: SelectionMode) -> AIResultCardType:
    if mode is SelectionMode.CONTINUE_TEXT:
        return AIResultCardType.TEXT_CANDIDATE
    return AIResultCardType.SUGGESTION


def _card_type_allowed_for_mode(
    mode: SelectionMode,
    card_type: AIResultCardType,
) -> bool:
    if mode is SelectionMode.ASK:
        return card_type is AIResultCardType.SUGGESTION
    if mode is SelectionMode.CONTINUE_TEXT:
        return card_type is AIResultCardType.TEXT_CANDIDATE
    return card_type in {
        AIResultCardType.SUGGESTION,
        AIResultCardType.PENDING_FACT,
    }


def _content_for_card_type(
    *,
    card_type: AIResultCardType,
    parsed: dict[str, Any],
    request: SelectionAIRequest,
    created_at: str,
) -> dict[str, Any] | str:
    raw_content = parsed.get("content")
    if card_type is AIResultCardType.TEXT_CANDIDATE:
        return _text_candidate_content(raw_content)
    if card_type is AIResultCardType.PENDING_FACT:
        return _pending_fact_content(raw_content, request, created_at)
    if isinstance(raw_content, dict):
        return raw_content
    if isinstance(raw_content, str) and raw_content.strip():
        return {"body": raw_content}
    return {"body": request.user_prompt or "未提供建议内容"}


def _text_candidate_content(raw_content: object) -> str:
    if isinstance(raw_content, str):
        return raw_content.strip()
    if isinstance(raw_content, dict):
        text = raw_content.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _pending_fact_content(
    raw_content: object,
    request: SelectionAIRequest,
    created_at: str,
) -> dict[str, Any]:
    content = raw_content if isinstance(raw_content, dict) else {}
    fact_type = _pending_fact_type(content.get("fact_type"))
    title = _text_field(content.get("title")) or request.selected_text[:40]
    fact_content = content.get("content")
    if fact_content is None:
        fact_content = _text_field(content.get("body")) or request.selected_text
    pending_fact = PendingFact(
        id=f"pending_fact_{uuid4().hex}",
        fact_type=fact_type,
        title=title,
        content=fact_content,
        proposed_by=ProposedBy.AI,
        source_refs=[request.selection_ref],
        status=PendingFactStatus.PENDING,
        target_knowledge_id=None,
        created_at=created_at,
        confirmed_at=None,
    )
    return pending_fact.model_dump(mode="json")


def _pending_fact_type(value: object) -> PendingFactType:
    if isinstance(value, str):
        try:
            return PendingFactType(value)
        except ValueError:
            return PendingFactType.OTHER
    return PendingFactType.OTHER


def _text_field(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
