"""Agent 相关端点。"""

from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import provide_agent_registry, provide_chat_agent_service
from taichu.api.schemas.ai_cards import AIResultCardInfo
from taichu.api.schemas.agents import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConversationInfo,
    AgentInfo,
    AgentListResponse,
)
from taichu.application.agents.chat.service import (
    ChatAgentRequest as ServiceChatAgentRequest,
)
from taichu.application.agents.chat.service import ChatAgentService
from taichu.application.agents.registry import AgentRegistry
from taichu.application.services.chapter_service import ChapterNotFoundError
from taichu.domain.models.agent_chat import AgentConversation
from taichu.domain.models.ai_card import AIResultCard

router = APIRouter(prefix="/api")


@router.get("/agents", response_model=AgentListResponse)
async def api_list_agents(
    registry: AgentRegistry = Depends(provide_agent_registry),
) -> AgentListResponse:
    """列出所有可用的 Agent。"""
    return AgentListResponse(
        agents=[
            AgentInfo(
                name=manifest.name,
                label=manifest.label,
                description=manifest.description,
                required_capabilities=sorted(manifest.required_capabilities),
                exposures=sorted(manifest.exposures),
                supports_streaming=manifest.supports_streaming,
            )
            for manifest in registry.list_manifests()
        ]
    )


@router.post("/agents/chat", response_model=AgentChatResponse)
async def api_run_agent_chat(
    request: AgentChatRequest,
    service: ChatAgentService = Depends(provide_chat_agent_service),
) -> AgentChatResponse:
    """Run Basic Agent Chat and return an AIResultCard."""
    try:
        result = await service.run(
            ServiceChatAgentRequest(
                message=request.message,
                chapter_id=request.chapter_id,
                include_current_chapter=request.include_current_chapter,
                include_confirmed_facts=request.include_confirmed_facts,
            )
        )
    except ChapterNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return AgentChatResponse(
        conversation=_conversation_info(result.conversation),
        card=_card_info(result.card),
    )


def _conversation_info(conversation: AgentConversation) -> AgentConversationInfo:
    return AgentConversationInfo(
        id=conversation.id,
        agent_name=conversation.agent_name,
        message=conversation.message,
        chapter_id=conversation.chapter_id,
        used_current_chapter=conversation.used_current_chapter,
        used_confirmed_facts=conversation.used_confirmed_facts,
        source_refs=conversation.source_refs,
        card_id=conversation.card_id,
        created_at=conversation.created_at,
    )


def _card_info(card: AIResultCard) -> AIResultCardInfo:
    return AIResultCardInfo(
        id=card.id,
        type=card.type.value,
        workflow=card.workflow.value,
        status=card.status.value,
        chapter_id=card.chapter_id,
        input_context=card.input_context,
        content=card.content,
        source_refs=card.source_refs,
        parent_card_id=card.parent_card_id,
        created_at=card.created_at,
        updated_at=card.updated_at,
    )
