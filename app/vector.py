"""向量层:知识库条目的混合检索(BM25 + 向量余弦)。

设计决策(与平台版 app/rag/vector.py 一致):
- 语料小(数十~几百条),索引放 SQLite(`data/rag_qa.db`),查询在内存算 ——
  零服务、可离线;不引 sqlite-vec 原生扩展(兼容性风险)。
- Embedding 双后端:
  1. API:千问 DashScope text-embedding(真语义向量),config/embedding.local.json 可配;
  2. 本地确定性 feature-hash(crc32 分词),无网/无 key 时兜底,同一文本必得同一向量。
- 混合分 = 0.6*cosine + 0.4*bm25(权重建表时固定)。
- 索引按「语料文件集合 + embedding 后端」双指纹自动过期重建:
  embedding 后端变了(哈希→API)向量维度可能不同,必须重建,否则余弦比对错位。
"""
import json
import math
import re
import sqlite3
import urllib.request
import zlib
from pathlib import Path

from . import corpus as _corpus
from .config import CONFIG_DIR, DB_PATH
from .io import read_json

VEC_DIM = 512
BM25_K1 = 1.5
BM25_B = 0.75
WEIGHTS = {"vector": 0.6, "bm25": 0.4}


# ---------------------------------------------------------------- 分词
def _tokenize(text):
    """中文按 单字+双字 切,英文/数字按词切。中文不依赖分词库。"""
    toks = []
    for run in re.findall(r"[一-鿿]+|[a-z0-9]+", (text or "").lower()):
        if re.search(r"[一-鿿]", run):
            chars = list(run)
            toks.extend(chars)
            if len(chars) >= 2:
                toks.extend(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
        else:
            toks.append(run)
    return toks


# ---------------------------------------------------------------- Embedding
class Embedder:
    """本地确定性 feature-hash 向量(兜底,保证离线/无 key 也能跑)。"""

    def __init__(self, dim=VEC_DIM):
        self.dim = dim
        self.backend = "hash:%d" % dim

    def embed(self, text):
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            h = zlib.crc32(tok.encode("utf-8"))
            vec[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    @staticmethod
    def default():
        """优先真语义向量(ApiEmbedder 有配置时),否则本地哈希兜底。"""
        api = ApiEmbedder.from_config()
        return api if api else Embedder()


class ApiEmbedder(Embedder):
    """千问 DashScope text-embedding,OpenAI 兼容 /embeddings 端点。"""

    def __init__(self, endpoint, key, model="text-embedding-v3", dim=VEC_DIM):
        super().__init__(dim)
        self.endpoint = endpoint
        self.key = key
        self.model = model
        self.backend = "api:" + model

    def embed(self, text):
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"model": self.model, "input": text}).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.key,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        vec = data["data"][0]["embedding"]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    @staticmethod
    def from_config():
        """读 config/embedding.local.json(带 BOM 容错)。"""
        p = CONFIG_DIR / "embedding.local.json"
        emb = read_json(p) if p.is_file() else None
        if emb and emb.get("endpoint") and emb.get("key"):
            return ApiEmbedder(emb["endpoint"], emb["key"],
                               emb.get("model", "text-embedding-v3"))
        return None


# ---------------------------------------------------------------- BM25
def _bm25_scores(docs, query_tokens):
    n = len(docs)
    if not n:
        return []
    lens = [len(d["tokens"]) for d in docs]
    avg = sum(lens) / n or 1.0
    df = {}
    for d in docs:
        for t in set(d["tokens"]):
            df[t] = df.get(t, 0) + 1
    scores = []
    for i, d in enumerate(docs):
        tf = {}
        for t in d["tokens"]:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in set(query_tokens):
            f = df.get(t, 0)
            if f and t in tf:
                idf = math.log(1 + (n - f + 0.5) / (f + 0.5))
                k = BM25_K1 * (1 - BM25_B + BM25_B * lens[i] / avg)
                s += idf * (tf[t] * (BM25_K1 + 1)) / (tf[t] + k)
        scores.append(s)
    mx = max(scores) or 1.0
    return [s / mx for s in scores]


def _cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


# ---------------------------------------------------------------- 索引
def _doc_text(x):
    """一条知识条目的检索文本:问题 + 答案 + 标签。"""
    return " ".join((x["question"], x["answer"], " ".join(x["tags"])))


def _index_meta(db):
    cur = db.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS index_meta(key TEXT PRIMARY KEY, value TEXT)")
    return dict(cur.execute("SELECT key,value FROM index_meta"))


def _current_fingerprint(embedder):
    """指纹 = 语料文件集合(路径+mtime+大小)+ embedding 后端。

    语料内容改了(mtime/大小变)或后端换了都会触发重建。
    """
    files = []
    for p in _corpus.iter_corpus_files():
        st = p.stat() if p.is_file() else None
        files.append([str(p.resolve()),
                      st.st_mtime if st else 0,
                      st.st_size if st else 0])
    return json.dumps({
        "sources": files,
        "backend": getattr(embedder, "backend", embedder.__class__.__name__),
    })


def build_index(force=False, embedder=None):
    """重建向量索引。返回 (条数, backend 名)。幂等,语料/后端没变则跳过。"""
    embedder = embedder or Embedder.default()
    corpus = _corpus.load_corpus()
    db = sqlite3.connect(DB_PATH)
    try:
        cur = db.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS qa_embeddings("
                    "id INTEGER PRIMARY KEY, category TEXT, tags TEXT, "
                    "meta TEXT, vector TEXT)")
        meta = _index_meta(db)
        if not force and meta.get("fingerprint", "") == _current_fingerprint(embedder):
            return len(corpus), embedder.backend
        cur.execute("DELETE FROM qa_embeddings")
        for x in corpus:
            cur.execute(
                "INSERT INTO qa_embeddings(category,tags,meta,vector)"
                " VALUES(?,?,?,?)",
                (x["category"], json.dumps(x["tags"], ensure_ascii=False),
                 json.dumps(x, ensure_ascii=False),
                 json.dumps(embedder.embed(_doc_text(x)))))
        # 过期判断靠指纹(语料文件集合 + embedding 后端),避免时钟依赖
        cur.execute("INSERT OR REPLACE INTO index_meta(key,value) VALUES('fingerprint',?)",
                    (_current_fingerprint(embedder),))
        db.commit()
        return len(corpus), embedder.backend
    finally:
        db.close()


def ensure_index():
    """查询前保证索引存在且与当前语料/后端一致。"""
    embedder = Embedder.default()
    db = sqlite3.connect(DB_PATH)
    try:
        meta = _index_meta(db)
        if meta.get("fingerprint", "") != _current_fingerprint(embedder):
            build_index(force=True, embedder=embedder)
    finally:
        db.close()


# ---------------------------------------------------------------- 检索
def retrieve_qa(question, markets=None, top_k=5):
    """按问题检索 top_k 条知识条目。

    - markets 提供时做硬过滤(条目声明了市场且不在其中则排除);
    - 返回 [{id, question, answer, category, tags, source, lang, markets, score}]。
    """
    ensure_index()
    docs = []
    db = sqlite3.connect(DB_PATH)
    try:
        cur = db.cursor()
        cur.execute("SELECT category,tags,meta,vector FROM qa_embeddings")
        for cat, tags, meta, vec in cur.fetchall():
            x = json.loads(meta)
            if markets:
                xm = x.get("markets") or []
                if xm and not (set(xm) & set(markets)):
                    continue
            x["tokens"] = _tokenize(_doc_text(x))
            x["_vec"] = json.loads(vec)
            docs.append(x)
    finally:
        db.close()

    if not docs:
        return []

    query_tokens = _tokenize(question)
    embedder = Embedder.default()
    q_vec = embedder.embed(question)

    bm25 = _bm25_scores(docs, query_tokens)
    scored = []
    for i, d in enumerate(docs):
        v = _cosine(q_vec, d["_vec"])
        hybrid = WEIGHTS["vector"] * v + WEIGHTS["bm25"] * bm25[i]
        scored.append((hybrid, i))
    scored.sort(key=lambda p: p[0], reverse=True)

    out = []
    for hybrid, i in scored[:top_k]:
        d = docs[i]
        out.append({
            "id": d["id"],
            "question": d["question"],
            "answer": d["answer"],
            "category": d["category"],
            "tags": d["tags"],
            "source": d["source"],
            "lang": d["lang"],
            "markets": d.get("markets") or [],
            "score": round(hybrid, 4),
        })
    return out
