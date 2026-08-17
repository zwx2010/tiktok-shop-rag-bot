"""飞书回调签名校验 + 加密载荷 AES 解密(移植自平台版,保持一致)。"""
import base64
import hashlib


def _sha1(*parts):
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


def _sha256(*parts):
    return hashlib.sha256(b"".join(parts)).hexdigest()


def verify_event_signature(timestamp, nonce, encrypt_key, signature):
    """旧版签名 v1: sha1(timestamp+nonce+encrypt_key)。"""
    if not signature:
        return False
    return _sha1(timestamp or "", nonce or "", encrypt_key or "") == signature


def verify_event_signature_v2(timestamp, nonce, encrypt_key, signature, raw_body):
    """新版签名 v2.0(飞书当前版本):
    sha256( (timestamp+nonce+encrypt_key).encode('utf-8') + 原始请求体字节 )。
    注意:是普通 sha256,不是 HMAC;encrypt_key 为空也要保留在拼接串里。
    """
    if not signature:
        return False
    if raw_body is None:
        raw_body = b""
    head = (timestamp or "") + (nonce or "") + (encrypt_key or "")
    return _sha256(head.encode("utf-8"), raw_body) == signature


def verify_token(body, verification_token):
    """verification_token 兜底(事件订阅 body 里带 token 时)。"""
    return bool(verification_token) and body.get("token") == verification_token


def decrypt(encrypt_key, payload_b64):
    """AES-256-CBC 解密飞书加密载荷(Encrypt Key 启用时)。"""
    try:
        from Crypto.Cipher import AES
    except ImportError:
        raise ValueError("pycryptodome 未安装,无法解密 Encrypt Key 载荷")
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    raw = base64.b64decode(payload_b64)
    iv, ct = raw[:16], raw[16:]
    pt = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
    pad = pt[-1]
    if 0 < pad <= 16:
        return pt[:-pad].decode("utf-8")
    return pt.decode("utf-8", "ignore")
