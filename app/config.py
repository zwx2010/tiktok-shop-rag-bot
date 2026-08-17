"""全局配置:目录约定 + 默认参数。"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
CORPUS_DIR = BASE_DIR / "corpus"

# 索引库路径(vector.py 使用)
DB_PATH = DATA_DIR / "rag_qa.db"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def get_app_config() -> dict:
    """读 config/app.json,不存在返回 {}。"""
    p = CONFIG_DIR / "app.json"
    if not p.is_file():
        return {}
    return load_json(p)
