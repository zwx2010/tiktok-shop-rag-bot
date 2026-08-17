"""API 路由:健康检查 / 统计 / 问答。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import corpus

router = APIRouter()


class AskIn(BaseModel):
    q: str = Field(..., min_length=1, max_length=500, description="问题")
    title: str | None = Field(None, max_length=300, description="商品标题(可选,触发上架判定)")
    properties: dict | None = Field(None, description="商品属性(可选)")


@router.get("/health")
def health():
    return {"ok": True, "service": "tiktok-shop-rag-bot"}


@router.get("/stats")
def stats():
    return corpus.corpus_stats()


def _ask(q: str, title: str | None = None, properties: dict | None = None):
    from ..llm import rag_answer
    if not q.strip():
        raise HTTPException(400, detail="q 不能为空")
    return rag_answer(q.strip(), title=title, properties=properties)


@router.get("/ask")
def ask_get(q: str = "", title: str | None = None):
    """GET 问一个运营问题。例:/api/ask?q=变体值最多能填多少字符"""
    return _ask(q, title)


@router.post("/ask")
def ask_post(body: AskIn):
    return _ask(body.q, body.title, body.properties)
