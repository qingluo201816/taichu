"""Agent 相关端点。"""

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from taichu.api.deps import get_agent_graph
from taichu.core.registry import list_agents
from taichu.models.schemas import AgentInfo, AgentListResponse, ChatRequest, ChatResponse

router = APIRouter(prefix="/api")


@router.get("/agents", response_model=AgentListResponse)
async def api_list_agents():
    """列出所有可用的 Agent。"""
    agents = list_agents()
    return AgentListResponse(
        agents=[
            AgentInfo(name=name, label=meta["label"], description=meta["description"])
            for name, meta in agents.items()
        ]
    )


@router.post("/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest):
    """统一的对话入口，根据 agent 参数路由到对应 Agent。"""
    try:
        graph = get_agent_graph(req.agent)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent}' not found")

    state = {"messages": [HumanMessage(content=req.message)]}
    result = await graph.ainvoke(state)

    last_msg = result["messages"][-1]
    return ChatResponse(agent=req.agent, response=last_msg.content)
