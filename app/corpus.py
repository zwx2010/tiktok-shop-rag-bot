"""Q&A 语料层:读 corpus/*.jsonl。

schema 见 corpus/schema.md。每行一条 JSON:
  {id, question, answer, category, tags[], source, lang, markets[]}
空 question 的行丢弃;单行解析失败跳过(不中断)。
"""
import json

from .config import CORPUS_DIR


def iter_corpus_files():
    return sorted(CORPUS_DIR.glob("*.jsonl"))


def load_corpus():
    """读全部语料为规范 dict 列表。"""
    out = []
    for path in iter_corpus_files():
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        x = json.loads(line)
                    except Exception:
                        continue
                    q = (x.get("question") or "").strip()
                    if not q:
                        continue
                    out.append({
                        "id": str(x.get("id") or ""),
                        "question": q,
                        "answer": (x.get("answer") or "").strip(),
                        "category": (x.get("category") or "").strip(),
                        "tags": [t for t in (x.get("tags") or []) if str(t).strip()],
                        "source": (x.get("source") or "").strip(),
                        "lang": (x.get("lang") or "zh").strip(),
                        "markets": [m for m in (x.get("markets") or []) if str(m).strip()],
                    })
        except Exception:
            continue
    return out


def corpus_stats():
    c = load_corpus()
    by_cat = {}
    for x in c:
        by_cat[x["category"]] = by_cat.get(x["category"], 0) + 1
    return {"total": len(c), "files": len(iter_corpus_files()),
            "by_category": by_cat}
