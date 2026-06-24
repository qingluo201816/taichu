"""主路由：挂载所有功能模块的子路由。

新增功能模块：
  1. 在 routes/ 下创建 feature.py（或 feature/ 目录）
  2. 定义一个 APIRouter，内部定义该模块的端点
  3. 回到此文件，加上 app.include_router(feature.router)
"""

from fastapi import FastAPI

from taichu.api.routes import agents


def register_routes(app: FastAPI) -> None:
    """向 FastAPI 应用注册所有功能路由。"""
    app.include_router(agents.router)

    # 未来扩展示例：
    # from taichu.api.routes import auth, knowledge, files
    # app.include_router(auth.router)
    # app.include_router(knowledge.router)
    # app.include_router(files.router)
