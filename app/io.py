"""共享 IO:带 BOM 容错的 JSON 读取。"""
import json
from pathlib import Path


def read_json(path):
    """读 JSON,容忍 UTF-8 BOM(PowerShell 写的配置常带 BOM)。"""
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig") if raw.startswith(b"\xef\xbb\xbf") else raw.decode("utf-8")
    return json.loads(text)
