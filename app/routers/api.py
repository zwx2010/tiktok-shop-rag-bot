"""API 路由:健康检查 / 统计 / 问答(可选 token 鉴权)。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import corpus

router = APIRouter()


# ---------------------------------------------------------------- 鉴权
def _api_token():
    from ..config import get_app_config
    return get_app_config().get("api_token") or ""


def require_api_token(request: Request):
    """config/app.json 配了 api_token 时,/api/ask 必须带
    `X-Api-Key: <token>` 头或 `?token=<token>`;未配置则开放(默认本地用)。"""
    cfg_token = _api_token()
    if not cfg_token:
        return
    header = request.headers.get("X-Api-Key") or ""
    q = request.query_params.get("token") or ""
    if header != cfg_token and q != cfg_token:
        raise HTTPException(status_code=401,
                            detail="缺失或错误的 api_token(配了 api_token 后需带 X-Api-Key)")


# ---------------------------------------------------------------- 模型
class AskIn(BaseModel):
    q: str = Field(..., min_length=1, max_length=500, description="问题")
    title: str | None = Field(None, max_length=300, description="商品标题(可选,触发上架判定)")
    properties: dict | None = Field(None, description="商品属性(可选,如 property_value)")


class RuleResult(BaseModel):
    name: str = ""
    passed: bool = False
    detail: str = ""


class RuleCheck(BaseModel):
    passed: bool
    title: str = ""
    rules: list[RuleResult] = []
    summary: str = ""


class SourceItem(BaseModel):
    id: str = ""
    question: str = ""
    answer: str = ""
    category: str = ""
    tags: list = []
    source: str = ""
    lang: str = ""
    markets: list = []
    score: float = 0.0


class AskOut(BaseModel):
    answer: str = Field(..., description="回答(LLM 生成或知识库原文降级)")
    sources: list[SourceItem] = Field(default_factory=list, description="引用来源")
    rule_check: RuleCheck | None = Field(None, description="上架判定(传了 title 才有)")
    llm_used: bool = Field(False, description="是否由 LLM 生成(否则为降级原文)")
    llm_error: str | None = Field(None, description="LLM 降级原因")


# ---------------------------------------------------------------- 端点
@router.get("/health")
def health():
    return {"ok": True, "service": "tiktok-shop-rag-bot"}


@router.get("/stats")
def stats():
    return corpus.corpus_stats()


def _ask(q: str, title: str | None = None, properties: dict | None = None) -> AskOut:
    from ..llm import rag_answer
    if not q.strip():
        raise HTTPException(400, detail="q 不能为空")
    return rag_answer(q.strip(), title=title, properties=properties)


@router.get("/ask", response_model=AskOut,
            summary="问答(GET)", description="GET 问一个运营问题。例:/api/ask?q=变体值最多能填多少字符")
def ask_get(q: str = "", title: str | None = None,
            _auth: None = Depends(require_api_token)):
    return _ask(q, title)


@router.post("/ask", response_model=AskOut,
             summary="问答(POST)", description="POST 问一个运营问题,可带商品标题触发上架判定")
def ask_post(body: AskIn, _auth: None = Depends(require_api_token)):
    return _ask(body.q, body.title, body.properties)
