"""页面路由:单页对话 UI(GET /?q=…&title=…)。"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import corpus

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates"))

EXAMPLES = [
    {"q": "变体值最多能填多少字符？", "desc": "上传规格"},
    {"q": "标题能不能带品牌词？", "desc": "品牌违禁"},
    {"q": "菲律宾佣金率是多少？", "desc": "定价税费"},
    {"q": "泰国税费怎么算？", "desc": "定价税费"},
    {"q": "这个品能不能上架？", "desc": "上架判定", "title": "不锈钢折叠刀户外"},
]


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    q = (request.query_params.get("q") or "").strip()
    title = (request.query_params.get("title") or "").strip() or None
    result = None
    if q:
        from ..llm import rag_answer
        result = rag_answer(q, title=title)
    stats = corpus.corpus_stats()
    return templates.TemplateResponse(
        request, "index.html",
        {"examples": EXAMPLES, "stats": stats,
         "q": q, "title": title or "", "result": result})
