"""RAG 生成链路:检索 → 拼 prompt → LLM → 带引用的回答。

流程:
1. retrieve_qa 检索 top_k 条知识条目;
2. 带商品标题时跑 rules.evaluate_product(硬门槛拦截);
3. 无命中 → 知识库外 fallback;命中分数过低 → 同样 fallback;
4. 命中 → 拼系统提示(只依据知识库,禁止编造,编号引用)→ DashScope chat 生成;
5. LLM 出错/未配置 → 降级返回最佳命中答案原文(llm_error 标记,无 key 也能用)。
"""
import json
import urllib.request

from . import rules
from .config import CONFIG_DIR
from .io import read_json
from .vector import retrieve_qa

MIN_SCORE = 0.12  # 低于此分视为无命中(可被 config/app.json 覆盖)


def _min_score():
    from .config import get_app_config
    return get_app_config().get("min_score", MIN_SCORE)


def _llm_config():
    """读 config/llm.local.json,无则返回 {}(走降级)。"""
    p = CONFIG_DIR / "llm.local.json"
    return read_json(p) if p.is_file() else {}


def _chat(messages, cfg):
    endpoint = cfg.get("endpoint") or \
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    model = cfg.get("model") or "qwen-plus"
    key = cfg.get("key") or ""
    req = urllib.request.Request(
        endpoint,
        data=json.dumps({"model": model, "messages": messages}).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _sources_block(hits):
    return "\n".join(
        "[%d] %s\n%s" % (i + 1, h["question"], h["answer"])
        for i, h in enumerate(hits))


def rag_answer(question, title=None, properties=None, top_k=5):
    """返回 {answer, sources, rule_check, llm_used, llm_error}。"""
    hits = retrieve_qa(question, top_k=top_k)
    rule_check = rules.evaluate_product(title, properties) if title else None

    # 硬门槛:标题违规 → 直接拦截,不生成回答
    if rule_check and not rule_check["passed"]:
        return {
            "answer": "该商品命中硬性规则拦截,不建议上架。\n" + rule_check["summary"],
            "sources": [],
            "rule_check": rule_check,
            "llm_used": False, "llm_error": None,
        }

    fallback = {
        "answer": "该问题不在当前知识库范围内。可补充语料(corpus/*.jsonl)后重建索引。",
        "sources": [], "rule_check": rule_check,
        "llm_used": False, "llm_error": None,
    }
    if not hits or hits[0]["score"] < _min_score():
        return fallback

    cfg = _llm_config()
    ctx = _sources_block(hits)
    sys_prompt = (
        "你是 TikTok Shop 跨境运营知识库助手。只依据下方知识库内容回答,"
        "禁止编造不存在的规则或数字。回答中用 [编号] 标注引用来源,如 [1][2]。"
        "若问题与知识库无关,只回答'该问题不在当前知识库范围内。'。\n\n"
        "===== 知识库 =====\n" + ctx
    )
    user_msg = question
    if title:
        user_msg += "\n\n(附带商品标题供参考: %s)" % title

    try:
        ans = _chat([{"role": "system", "content": sys_prompt},
                     {"role": "user", "content": user_msg}], cfg)
        return {"answer": ans, "sources": hits, "rule_check": rule_check,
                "llm_used": True, "llm_error": None}
    except Exception as exc:
        # 降级:LLM 挂了/没配 key,直接用最佳命中答案原文
        return {"answer": hits[0]["answer"], "sources": hits,
                "rule_check": rule_check,
                "llm_used": False, "llm_error": str(exc)}
