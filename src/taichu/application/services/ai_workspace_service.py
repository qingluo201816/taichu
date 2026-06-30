"""MVP writing-area AI conversation use cases with mock output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from taichu.application.contracts.storage import ProjectAssetStorageContract
from taichu.domain.models import (
    AIReferenceScope,
    AIWorkspaceConversation,
    AIWorkspaceMessage,
    AIWorkspaceMessageRole,
    AIWorkspaceOutputType,
    AIWorkspaceSubtaskType,
    AIWorkspaceTaskType,
    PromptSnapshot,
    SourceReference,
    SourceReferenceType,
)

AI_WORKSPACE_CONVERSATIONS_FILE = "ai_workspace_conversations.jsonl"


@dataclass(frozen=True)
class AIHistoryFilters:
    """Filters supported by the MVP AI history page."""

    chapter_id: str | None = None
    task_type: AIWorkspaceTaskType | None = None
    has_source: bool | None = None
    has_error: bool | None = None


class AIWorkspaceService:
    """Manage writing-area AI conversations without real LLM calls."""

    def __init__(self, storage: ProjectAssetStorageContract) -> None:
        self._storage = storage

    async def create_conversation(
        self,
        chapter_id: str,
        task_type: AIWorkspaceTaskType,
        reference_scope: AIReferenceScope,
        subtask_type: AIWorkspaceSubtaskType | None = None,
        model_name: str = "mock-llm",
    ) -> AIWorkspaceConversation:
        """Create an empty writing-area AI conversation."""
        if task_type is AIWorkspaceTaskType.CHAT:
            raise AIConversationNotPersistedError(
                "纯对话不保存为写作区 AI 多轮对话记录。"
            )
        now = _now_iso()
        conversation = AIWorkspaceConversation(
            id=f"ai-conv-{uuid4().hex}",
            chapter_id=chapter_id,
            task_type=task_type,
            subtask_type=subtask_type,
            reference_scope=reference_scope,
            model_name=model_name or "mock-llm",
            is_mock=True,
            messages=[],
            source_refs=[],
            created_at=now,
            updated_at=now,
        )
        await self._append(conversation)
        return conversation

    async def send_message(
        self,
        conversation_id: str,
        user_input: str,
        reference: dict[str, Any],
    ) -> AIWorkspaceConversation:
        """Append a user message and a deterministic mock assistant response."""
        conversation = await self.get_conversation(conversation_id)
        now = _now_iso()
        snapshot = _prompt_snapshot(conversation, user_input, reference)
        user_message = AIWorkspaceMessage(
            message_id=f"msg-{uuid4().hex}",
            role=AIWorkspaceMessageRole.USER,
            content=user_input,
            task_type=conversation.task_type,
            subtask_type=conversation.subtask_type,
            reference_scope=conversation.reference_scope,
            prompt_snapshot=snapshot,
            skill=_skill_for(conversation),
            route=_route_for(conversation),
            source_refs=[],
            is_mock=True,
            created_at=now,
        )
        assistant_message = _mock_assistant_message(conversation, reference)
        source_refs = _merge_source_refs(
            conversation.source_refs,
            assistant_message.source_refs,
        )
        updated = conversation.model_copy(
            update={
                "messages": [
                    *conversation.messages,
                    user_message,
                    assistant_message,
                ],
                "source_refs": source_refs,
                "updated_at": assistant_message.created_at,
            }
        )
        await self._replace(updated)
        return updated

    async def list_conversations(
        self,
        filters: AIHistoryFilters | None = None,
    ) -> list[AIWorkspaceConversation]:
        """List conversations for the AI history page and writing panel lookup."""
        conversations = [
            AIWorkspaceConversation.model_validate(record)
            for record in await self._storage.list_workspace_records(
                AI_WORKSPACE_CONVERSATIONS_FILE
            )
        ]
        if filters:
            if filters.chapter_id:
                conversations = [
                    item for item in conversations if item.chapter_id == filters.chapter_id
                ]
            if filters.task_type:
                conversations = [
                    item for item in conversations if item.task_type is filters.task_type
                ]
            if filters.has_source is not None:
                conversations = [
                    item
                    for item in conversations
                    if bool(item.source_refs) is filters.has_source
                ]
            if filters.has_error is not None:
                conversations = [
                    item
                    for item in conversations
                    if _has_error(item) is filters.has_error
                ]
        return sorted(conversations, key=lambda item: item.updated_at, reverse=True)

    async def get_conversation(self, conversation_id: str) -> AIWorkspaceConversation:
        """Return one writing-area AI conversation."""
        for conversation in await self.list_conversations():
            if conversation.id == conversation_id:
                return conversation
        raise AIConversationNotFoundError(conversation_id)

    async def _append(self, conversation: AIWorkspaceConversation) -> None:
        await self._storage.append_workspace_record(
            AI_WORKSPACE_CONVERSATIONS_FILE,
            conversation.model_dump(mode="json"),
        )

    async def _replace(self, updated: AIWorkspaceConversation) -> None:
        records = await self._storage.list_workspace_records(
            AI_WORKSPACE_CONVERSATIONS_FILE
        )
        rewritten: list[dict[str, object]] = []
        replaced = False
        for record in records:
            conversation = AIWorkspaceConversation.model_validate(record)
            if conversation.id == updated.id:
                rewritten.append(updated.model_dump(mode="json"))
                replaced = True
            else:
                rewritten.append(conversation.model_dump(mode="json"))
        if not replaced:
            raise AIConversationNotFoundError(updated.id)
        await self._storage.rewrite_workspace_records(
            AI_WORKSPACE_CONVERSATIONS_FILE,
            rewritten,
        )


class AIConversationNotFoundError(LookupError):
    """Raised when a writing-area AI conversation does not exist."""

    def __init__(self, conversation_id: str) -> None:
        super().__init__(f"写作区 AI 对话“{conversation_id}”不存在")


class AIConversationNotPersistedError(ValueError):
    """Raised when a non-persisted entrance is sent to the AI history store."""


def _prompt_snapshot(
    conversation: AIWorkspaceConversation,
    user_input: str,
    reference: dict[str, Any],
) -> PromptSnapshot:
    route = _route_for(conversation)
    structured = {
        "user_input": user_input,
        "task_type": conversation.task_type.value,
        "subtask_type": (
            conversation.subtask_type.value if conversation.subtask_type else None
        ),
        "reference_scope": conversation.reference_scope.value,
        "reference": reference,
        "skill": _skill_for(conversation),
        "route": route,
    }
    final_prompt = (
        "【模拟提示词】"
        f"任务：{conversation.task_type.value}。"
        f"参考范围：{conversation.reference_scope.value}。"
        f"作者要求：{user_input}"
    )
    return PromptSnapshot(structured=structured, final_prompt=final_prompt)


def _mock_assistant_message(
    conversation: AIWorkspaceConversation,
    reference: dict[str, Any],
) -> AIWorkspaceMessage:
    now = _now_iso()
    output_type, content = _mock_content(conversation)
    source_refs: list[SourceReference] = []
    if conversation.task_type is AIWorkspaceTaskType.EVIDENCE:
        source_refs = [
            SourceReference(
                source_type=SourceReferenceType.CHAPTER,
                source_id=str(reference.get("chapter_id") or conversation.chapter_id),
                display_name=str(reference.get("display_name") or "模拟来源章节"),
                excerpt=str(reference.get("excerpt") or "模拟来源摘录，最多 300 字。")[:300],
                note="模拟来源引用，仅用于结构检查。",
            )
        ]
    return AIWorkspaceMessage(
        message_id=f"msg-{uuid4().hex}",
        role=AIWorkspaceMessageRole.ASSISTANT,
        content=content,
        task_type=conversation.task_type,
        subtask_type=conversation.subtask_type,
        reference_scope=conversation.reference_scope,
        output_type=output_type,
        source_refs=source_refs,
        is_mock=True,
        created_at=now,
    )


def _mock_content(
    conversation: AIWorkspaceConversation,
) -> tuple[AIWorkspaceOutputType, dict[str, Any]]:
    if conversation.task_type is AIWorkspaceTaskType.CONTINUE:
        return (
            AIWorkspaceOutputType.TEXT_CANDIDATE,
            {
                "text": (
                    "秦阳立在残碑之前，指尖的金色鳞光一点点沉入掌心。"
                    "山风从破碎的石阶间穿过，像有无数人在低声念诵。"
                )
            },
        )
    if conversation.task_type is AIWorkspaceTaskType.POLISH:
        return (
            AIWorkspaceOutputType.TEXT_CANDIDATE,
            {"text": "他没有立刻开口，只是抬眼望向那座沉在云后的山门。"},
        )
    if conversation.task_type is AIWorkspaceTaskType.SETTING:
        return (
            AIWorkspaceOutputType.SETTING_RESULT,
            {
                "setting_addition": "可以把金鳞异象设定为元神外显的早期征兆。",
                "usage_suggestion": "正文中先用感官和旁人反应暗示。",
                "possible_impact": "若后续确认为境界规则，需要补充到境界卡或规则卡。",
            },
        )
    if conversation.task_type is AIWorkspaceTaskType.SUGGESTION:
        return (
            AIWorkspaceOutputType.SUGGESTION_RESULT,
            {
                "problem": "这一段主要问题是压迫来源不够具体。",
                "judgement": "角色恐惧成立，但危险层级还不明确。",
                "suggestion": "增加外界人物沉默、法器失灵、空间变冷等细节。",
            },
        )
    if conversation.task_type is AIWorkspaceTaskType.EVIDENCE:
        return (
            AIWorkspaceOutputType.EVIDENCE_RESULT,
            {
                "conclusion": "当前没有可确认的正式依据，只能作为推测。",
                "evidence": [
                    {
                        "text": "模拟依据：这里展示来源字段结构，不代表真实检索结果。",
                        "source_ref_id": "src_mock_001",
                    }
                ],
                "inference": "如果该异象后续重复出现，可以考虑沉淀为规则卡。",
                "unconfirmed_points": ["金鳞异象是否属于境界规则尚未确认。"],
            },
        )
    if conversation.task_type is AIWorkspaceTaskType.CHAPTER_SUMMARY:
        return (
            AIWorkspaceOutputType.CHAPTER_SUMMARY,
            {
                "summary": "本章以模拟方式整理：主角遭遇异象，山门压力开始显现。",
                "key_events": ["金鳞异象出现", "山门气氛转冷"],
                "character_changes": [
                    {"name": "秦阳", "change": "意识到自身异象可能带来风险"}
                ],
                "new_setting_candidates": [],
                "foreshadow_candidates": ["金鳞异象来源尚未确认"],
                "next_chapter_hooks": ["山门长老注意到异常"],
            },
        )
    return (
        AIWorkspaceOutputType.ERROR,
        {"message": "当前入口不保存为写作区 AI 多轮对话记录。"},
    )


def _skill_for(conversation: AIWorkspaceConversation) -> str:
    return f"mock-{conversation.task_type.value}"


def _route_for(conversation: AIWorkspaceConversation) -> str:
    if conversation.subtask_type:
        return f"mock_{conversation.task_type.value}_{conversation.subtask_type.value}"
    return f"mock_{conversation.task_type.value}"


def _merge_source_refs(
    current: list[SourceReference],
    incoming: list[SourceReference],
) -> list[SourceReference]:
    seen = {(item.source_type.value, item.source_id, item.excerpt) for item in current}
    merged = list(current)
    for item in incoming:
        key = (item.source_type.value, item.source_id, item.excerpt)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


def _has_error(conversation: AIWorkspaceConversation) -> bool:
    return any(message.role is AIWorkspaceMessageRole.ERROR for message in conversation.messages)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
