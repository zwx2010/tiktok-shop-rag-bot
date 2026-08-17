"""飞书消息处理:收到的群消息 → rag_answer → 回卡片。

- 只回「@机器人 或 私聊机器人」的消息(群聊不 @ 不回,避免刷屏);
  bot_name 在 config/feishu.local.json 配(机器人显示名,事件 content 里能看到)。
- 解析 body.event.message: content 是 JSON 串 {"text":"..."},去掉 @ 标记。
"""
import json
import re

from . import client

_AT_RE = re.compile(r"<at[^>]*>.*?</at>|<at[^>]*/>")


def _extract_text(message):
    """从飞书消息事件里取纯文本(去 @ 标记)。返回 (chat_id, text)。"""
    chat_id = (message.get("chat_id") or "")
    content = message.get("content") or "{}"
    try:
        body = json.loads(content)
    except (ValueError, TypeError):
        body = {}
    text = body.get("text") or ""
    text = _AT_RE.sub("", text).strip()
    return chat_id, text


def _should_reply(body):
    """私聊必回;群聊只在提到机器人时回。"""
    message = body.get("event", {}).get("message", {})
    chat_type = message.get("chat_type", "")
    if chat_type == "p2p":
        return True
    content = message.get("content") or ""
    cfg = client.feishu_config()
    name = cfg.get("bot_name") or ""
    if name and name in content:
        return True
    # 没配 bot_name 时:出现 @ 标记即视为点机器人(避免回复无关群消息)
    return bool(name or "<at" in content)


def on_message(body):
    """收到 im.message.receive_v1 → 问答并回卡片。返回 {ok, detail}。"""
    event = body.get("event", {})
    message = event.get("message", {})
    chat_id, text = _extract_text(message)
    if not chat_id or not text:
        return {"ok": False, "detail": "empty chat/text"}
    if not _should_reply(body):
        return {"ok": False, "detail": "not mention, skipped"}

    from ..llm import rag_answer
    result = rag_answer(text)
    ok, err = client.reply_to_chat(chat_id, result, question=text)
    return {"ok": ok, "detail": err or ("replied: %s" % result["answer"][:40])}
