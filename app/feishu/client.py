"""飞书客户端 —— 用自建应用 API 收发消息(urllib,不引 requests)。

- 收:事件订阅 im.message.receive_v1 打到 /api/feishu/webhook(见 routers/feishu.py)
- 发:tenant_access_token + im/v1/messages 回文本/卡片到原群

配置: config/feishu.local.json
  {app_id, app_secret, verification_token, encrypt_key, bot_name}
"""
import json
import threading
import time
import urllib.request

from ..config import CONFIG_DIR
from ..io import read_json

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MSG_SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

_lock = threading.Lock()
_token_cache = {}


def feishu_config():
    p = CONFIG_DIR / "feishu.local.json"
    return read_json(p) if p.is_file() else {}


def _post_json(url, payload, token=None, timeout=15):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_tenant_access_token():
    """tenant_access_token(缓存到过期前 60s)。返回 (token, err)。"""
    cfg = feishu_config()
    app_id = cfg.get("app_id") or ""
    app_secret = cfg.get("app_secret") or ""
    if not app_id or not app_secret:
        return None, "app_id/app_secret 未配置"
    with _lock:
        c = _token_cache.get(app_id)
        if c and c["expire_at"] > time.time() + 60:
            return c["token"], ""
    try:
        d = _post_json(TOKEN_URL,
                       {"app_id": app_id, "app_secret": app_secret})
    except Exception as exc:
        return None, "token 请求异常: %s" % exc
    if d.get("code") != 0:
        return None, "token 失败: %s %s" % (d.get("code"), d.get("msg"))
    tok = d["tenant_access_token"]
    with _lock:
        _token_cache[app_id] = {"token": tok,
                                "expire_at": time.time() + int(d.get("expire", 7200)) - 60}
    return tok, ""


def send_message_app(token, chat_id, msg_type, content, timeout=15):
    """用应用身份发消息到群/单聊。content 为 dict(飞书按 msg_type 序列化)。"""
    try:
        d = _post_json(MSG_SEND_URL,
                       {"receive_id": chat_id, "msg_type": msg_type,
                        "content": json.dumps(content, ensure_ascii=False)},
                       token=token, timeout=timeout)
    except Exception as exc:
        return False, {"error": str(exc)}
    return d.get("code") == 0, d


def send_text(token, chat_id, text):
    return send_message_app(token, chat_id, "text", {"text": text})


def send_card(token, chat_id, card):
    return send_message_app(token, chat_id, "interactive", card)


def reply_to_chat(chat_id, result, question=""):
    """把 rag_answer 结果回成飞书卡片到原群。返回 (ok, err)。"""
    token, err = get_tenant_access_token()
    if err:
        return False, err
    card = build_answer_card(result, question)
    ok, resp = send_card(token, chat_id, card)
    if not ok:
        # 卡失败退回纯文本,保证能回
        ok2, _ = send_text(token, chat_id, result["answer"])
        return ok2, "card fallback text: %s" % resp
    return ok, ""


def build_answer_card(result, question=""):
    """回答卡片:违规拦截红色 / 正常蓝色;内容 = 回答 + 来源 + 上架判定。"""
    rc = result.get("rule_check")
    color = "red" if (rc and not rc["passed"]) else "blue"
    title = "TikTok 运营知识库"
    if question:
        title = "TikTok 运营知识库 · %s" % (question[:20])

    answer = result.get("answer") or ""
    elements = []
    # 回答正文
    elements.append({"tag": "div",
                     "text": {"tag": "lark_md", "content": answer}})
    # 上架判定明细(命中时)
    if rc and not rc["passed"]:
        lines = []
        for r in rc.get("rules", []):
            mark = "✅" if r.get("passed") else "⛔"
            lines.append("%s **%s**: %s" % (mark, r["name"], r.get("detail", "")))
        elements.append({"tag": "div",
                         "text": {"tag": "lark_md",
                                  "content": "\n".join(lines)}})
    # 引用来源(top 3)
    srcs = result.get("sources") or []
    if srcs:
        lines = ["**引用来源**"]
        for s in srcs[:3]:
            lines.append("- [%s] %s" % (s.get("category", ""), s.get("question", "")))
        elements.append({"tag": "div",
                         "text": {"tag": "lark_md",
                                  "content": "\n".join(lines)}})
    return {"header": {"template": color,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": elements}
