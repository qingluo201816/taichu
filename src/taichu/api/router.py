"""汇总并挂载 FastAPI 路由。"""

from fastapi import FastAPI

from taichu.api.routes import (
    agents,
    ai_cards,
    ai_history,
    ai_workspace,
    chapters,
    export,
    inbox,
    knowledge,
    mvp_knowledge,
    outline,
    settings,
)


def register_routes(app: FastAPI) -> None:
    """向 FastAPI 应用注册所有功能路由。"""
    app.include_router(agents.router)
    app.include_router(ai_cards.router)
    app.include_router(ai_workspace.router)
    app.include_router(ai_history.router)
    app.include_router(chapters.router)
    app.include_router(export.router)
    app.include_router(inbox.router)
    app.include_router(knowledge.router)
    app.include_router(mvp_knowledge.router)
    app.include_router(outline.router)
    app.include_router(settings.router)
