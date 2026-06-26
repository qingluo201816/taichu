"""组装并启动太初 FastAPI 应用。"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from taichu.api.router import register_routes
from taichu.application.agents.registry import AgentRegistry
from taichu.application.capabilities import CapabilityContext
from taichu.application.tools.registry import ToolRegistry
from taichu.config import Settings, settings
from taichu.infrastructure.llm.factory import create_llm
from taichu.infrastructure.plugin_discovery import (
    discover_agents,
    discover_tools,
)
from taichu.infrastructure.storage.json_backend import JsonStorageBackend


def create_app(
    app_settings: Settings = settings,
    *,
    llm: BaseChatModel | None = None,
) -> FastAPI:
    """创建并组装 FastAPI 应用。"""
    storage = JsonStorageBackend(app_settings.project_assets_dir / "source")
    chat_model = llm or create_llm(app_settings)
    capability_context = CapabilityContext(
        capabilities={
            "llm": chat_model,
            "storage": storage,
        }
    )
    agent_registry = AgentRegistry(capability_context)
    agent_registry.register_all(
        discover_agents("taichu.application.agents")
    )
    tool_registry = ToolRegistry(capability_context)
    tool_registry.register_all(
        discover_tools("taichu.application.tools")
    )

    application = FastAPI(
        title="Taichu",
        description="太初 - 单本玄幻小说个人写作助手",
    )
    application.state.agent_registry = agent_registry
    application.state.tool_registry = tool_registry
    application.state.storage = storage
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_routes(application)
    return application


app = create_app()


def main() -> None:
    """启动开发服务器。"""
    uvicorn.run(
        "taichu.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
