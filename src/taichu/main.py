"""Taichu - FastAPI 入口。"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from taichu.api.router import router
from taichu.config import settings

app = FastAPI(title="Taichu", description="太初 - 玄幻小说个人写作助手")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def main():
    uvicorn.run("taichu.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    main()
