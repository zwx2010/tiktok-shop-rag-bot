"""规则层:结构化硬门槛(上架前拦截)。

- 违禁词:config/banned_keywords.json(由「违禁自动刊登关键词」表生成,
  tools/build_corpus.py 负责),分 keywords(一般违禁)与 free_keywords(战术词
  如 防弹/子弹/折叠刀),命中任一即 FAIL。
- 上传规格:TikTok 真实校验反馈沉淀的默认值 ——
  属性名 ≤20 字符、属性值 ≤50 字符、商品名 ≤255 字符(可变体值)。
"""
import re
from functools import lru_cache

from .config import CONFIG_DIR
from .io import read_json


@lru_cache(maxsize=1)
def _banned_cfg():
    """懒加载违禁词表;文件不存在时返回空(检查放行)。"""
    p = CONFIG_DIR / "banned_keywords.json"
    return read_json(p) if p.is_file() else {}


def check_banned(title, text=None):
    """违禁词检查。title 商品标题必查;text 可选(描述/属性)。"""
    cfg = _banned_cfg()
    terms = [t for t in (cfg.get("keywords") or []) if str(t).strip()]
    terms += [t for t in (cfg.get("free_keywords") or []) if str(t).strip()]
    hay = ((title or "") + " " + (text or "")).lower()
    hits = []
    for t in terms:
        t = str(t).strip().lower()
        if t and t in hay:
            hits.append(t)
    detail = ", ".join(hits[:6]) if hits else "no banned hits"
    return {"name": "banned", "passed": len(hits) == 0,
            "detail": "%d hits: %s" % (len(hits), detail), "hits": hits[:8]}


# 上传规格默认值(可被 config/app.json 的 upload_spec 覆盖)
DEFAULT_UPLOAD_SPEC = {
    "property_name": 20,
    "property_value": 50,
    "product_name": 255,
}


def check_upload_spec(properties=None):
    """上传规格检查:属性名/属性值/商品名的最大字符数(TikTok 校验)。"""
    from .config import get_app_config
    spec = dict(DEFAULT_UPLOAD_SPEC)
    spec.update((get_app_config().get("upload_spec") or {}))
    props = properties or {}
    checks = [
        ("property_name", spec["property_name"], props.get("property_name")),
        ("property_value", spec["property_value"], props.get("property_value")),
        ("product_name", spec["product_name"], props.get("product_name")),
    ]
    fails = []
    for name, max_len, val in checks:
        text = "" if val is None else str(val)
        if text and len(text) > max_len:
            fails.append("%s=%d>%d" % (name, len(text), max_len))
    detail = "; ".join(fails) if fails else "all within limits"
    return {"name": "upload_spec", "passed": not fails,
            "detail": detail, "fails": fails[:6]}


def evaluate_product(title, properties=None):
    """对一个商品跑全部硬性规则。返回 {passed, title, rules, summary}。"""
    rules = [
        check_banned(title),
        check_upload_spec(properties),
    ]
    passed = all(r["passed"] for r in rules)
    summary = "; ".join(
        "%s:%s" % (r["name"], "OK" if r["passed"] else "FAIL-" + r["detail"])
        for r in rules)
    return {"passed": passed, "title": title,
            "rules": rules, "summary": summary}
