"""FastAPI 入口。

运行:
    python -m uvicorn app.main:app --port 8000
或:
    python scripts/launcher.py --server
"""
from fastapi import FastAPI

from .routers import api, pages

app = FastAPI(title="TikTok Shop 运营规则知识库问答", version="0.1.0")

app.include_router(pages.router, tags=["pages"])
app.include_router(api.router, prefix="/api", tags=["api"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
