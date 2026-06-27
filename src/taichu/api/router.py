"""汇总并挂载 FastAPI 路由。"""

from fastapi import FastAPI

from taichu.api.routes import agents, ai_cards, chapters


def register_routes(app: FastAPI) -> None:
    """向 FastAPI 应用注册所有功能路由。"""
    app.include_router(agents.router)
    app.include_router(ai_cards.router)
    app.include_router(chapters.router)
