"""FastAPI 入口。

运行:
    python -m uvicorn app.main:app --port 8000
或:
    python scripts/launcher.py --server
"""
import sys

# Windows 重定向 stdout/stderr 默认 GBK,emoji/中文可能编码失败,
# 强制 UTF-8 保证飞书回消息的日志正常落盘。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI

from .routers import api, feishu, pages

app = FastAPI(title="TikTok Shop 运营规则知识库问答", version="0.1.0",
              description="垂直 RAG 问答:混合检索 + 硬规则审核门 + 带引用回答。"
                          "可用飞书机器人 / HTTP API 接入。")

app.include_router(pages.router, tags=["pages"])
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(feishu.router, prefix="/api", tags=["feishu"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
