"""飞书事件订阅路由。

- POST /api/feishu/webhook  事件订阅(消息 / URL 验证握手)

配置: config/feishu.local.json {app_id, app_secret, verification_token, encrypt_key, bot_name}
签名: sha1(timestamp+nonce+encrypt_key),verification_token 兜底。
本地调试: env ALLOW_UNVERIFIED=1 跳过校验(默认关闭)。
"""
import json
import os
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import CONFIG_DIR
from ..feishu import handlers, signature as sig
from ..io import read_json

router = APIRouter()

_MSG_DEDUP = set()
_DEDUP_LOCK = threading.Lock()


def _cfg():
    p = CONFIG_DIR / "feishu.local.json"
    return read_json(p) if p.is_file() else {}


def _mask(s, n=6):
    if not s:
        return "空"
    return s[:n] + "..." + s[-2:] + f"(长{len(s)})"


def _verified(timestamp, nonce, signature, body=None, raw=None):
    if os.environ.get("ALLOW_UNVERIFIED") == "1":
        return True
    cfg = _cfg()
    enc = cfg.get("encrypt_key", "")
    tok = cfg.get("verification_token", "")
    if sig.verify_event_signature_v2(timestamp, nonce, enc, signature, raw):
        return True
    if sig.verify_event_signature(timestamp, nonce, enc, signature):
        return True
    if body is not None and tok:
        bt = (body.get("header") or {}).get("token") or body.get("token")
        if bt and bt == tok:
            return True
    # 诊断:为什么验不过(全部脱敏)
    print("[feishu] 签名校验失败诊断:", flush=True)
    print(f"  收到 timestamp={timestamp!r} nonce={nonce!r}", flush=True)
    print(f"  收到 signature={_mask(signature)} | 配置 encrypt_key={_mask(enc)} "
          f"verification_token={_mask(tok)}", flush=True)
    if body is not None:
        bt = (body.get("header") or {}).get("token") or body.get("token")
        print(f"  body 里 token={_mask(bt)}", flush=True)
        print(f"  body 里是否含 encrypt 字段={'encrypt' in body}", flush=True)
        print(f"  body schema={body.get('schema')} event_type="
              f"{(body.get('header') or {}).get('event_type')}", flush=True)
    return False


async def _read_and_verify(request):
    raw = await request.body()
    ts = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    sign = request.headers.get("X-Lark-Signature", "")
    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        body = {}
    if not _verified(ts, nonce, sign, body, raw):
        return None, {"ok": False, "detail": "signature mismatch"}
    return body, None


@router.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    print("[feishu] RAW hit webhook", flush=True)
    body, err = await _read_and_verify(request)
    if err:
        return JSONResponse(status_code=401, content=err)
    print("[feishu] recv body:", json.dumps(body, ensure_ascii=False)[:300], flush=True)

    enc = _cfg().get("encrypt_key", "")
    if enc and "encrypt" in body:
        try:
            body = json.loads(sig.decrypt(enc, body["encrypt"]))
        except ValueError as exc:
            return JSONResponse(status_code=400,
                                content={"ok": False, "detail": str(exc)})

    # URL 验证握手:飞书订阅回调地址时,回显 challenge
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    header = body.get("header") or {}
    etype = (body.get("event") or {}).get("type") \
        or header.get("event_type") or body.get("type")
    if etype == "im.message.receive_v1":
        # 问答+回卡大约 1~3s,后台线程跑,立即回 200 避免飞书重试
        eid = header.get("event_id") or ""
        if eid:
            with _DEDUP_LOCK:
                if eid in _MSG_DEDUP:
                    return {"code": 0}
                _MSG_DEDUP.add(eid)
        threading.Thread(target=_dispatch, args=(body,), daemon=True).start()
        return {"code": 0}
    return handlers.on_message(body)


def _dispatch(body):
    try:
        print("[feishu] dispatch start", flush=True)
        result = handlers.on_message(body)
        print("[feishu] replied:", json.dumps(result, ensure_ascii=True)[:160],
              flush=True)
    except Exception as exc:
        print("[feishu] dispatch error:", exc, flush=True)
