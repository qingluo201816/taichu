"""Agent 相关端点。"""

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage

from taichu.api.deps import provide_agent_registry
from taichu.api.schemas.agents import (
    AgentInfo,
    AgentListResponse,
    ChatRequest,
    ChatResponse,
)
from taichu.application.agents.registry import AgentNotFoundError, AgentRegistry

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


@router.post("/chat", response_model=ChatResponse)
async def api_chat(
    request: ChatRequest,
    registry: AgentRegistry = Depends(provide_agent_registry),
) -> ChatResponse:
    """统一的对话入口，根据 agent 参数路由到对应 Agent。"""
    try:
        graph = registry.get_graph(request.agent)
    except AgentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    state = {"messages": [HumanMessage(content=request.message)]}
    result = await graph.ainvoke(state)

    last_msg = result["messages"][-1]
    return ChatResponse(agent=request.agent, response=str(last_msg.content))
