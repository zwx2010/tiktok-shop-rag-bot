"""重建/确保 RAG 索引。

用法:
    python scripts/build_index.py            # 语料/后端没变则跳过
    python scripts/build_index.py --force    # 强制重建
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.vector import build_index, Embedder  # noqa: E402

if __name__ == "__main__":
    force = "--force" in sys.argv
    n, backend = build_index(force=force, embedder=Embedder.default())
    print(f"[build_index] {n} 条语料已入索引,backend={backend}"
          f"{'(强制重建)' if force else ''}", flush=True)
