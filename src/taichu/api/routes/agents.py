"""Agent 相关端点。"""

from fastapi import APIRouter, Depends

from taichu.api.deps import provide_agent_registry
from taichu.api.schemas.agents import (
    AgentInfo,
    AgentListResponse,
)
from taichu.application.agents.registry import AgentRegistry

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
