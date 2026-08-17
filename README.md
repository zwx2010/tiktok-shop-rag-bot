# TikTok Shop 运营规则知识库问答（RAG Bot）

一个**垂直 RAG 问答机器人**：用真实 TikTok Shop 运营语料（话术库 + 定价税费表）建知识库，回答「变体值最多填多少字符」「标题能不能带品牌词」「菲律宾佣金率多少」「泰国税费怎么算」这类运营问题，**回答带引用来源、不瞎编**，并能对商品标题做**硬性规则拦截**（违禁词 / 上传规格）。

> 定位：给自己 6 个月 TikTok 运营经验做的「规则大脑」。同一套知识库，未来长成 **Phase 2 多语言 AI 客服**（买家语回复）+ **审核 agent**（上架表批量扫描）。

## 架构

```mermaid
flowchart LR
    A[桌面 Excel 语料源<br/>话术库 + 定价税费表] --> B[tools/build_corpus.py]
    B --> C[corpus/*.jsonl<br/>标准 Q&A 语料]
    B --> D[config/banned_keywords.json<br/>违禁词表]
    C --> E[scripts/build_index.py]
    D --> F{上架判定<br/>rules.evaluate_product}
    E --> G[(SQLite 索引<br/>BM25 + 向量)]
    Q[运营提问] --> H[retrieve_qa<br/>混合检索 0.6向量+0.4BM25]
    G --> H
    H --> I[DashScope LLM<br/>检索增强生成]
    I --> R[带引用回答<br/>[1][2]]
    Q --> F
    F -->|硬规则拦截| X[不通过 → 拦截]
    H -->|无命中| Y[知识库外 fallback]
```

- **Embedding 双后端**：优先千问 text-embedding-v3（真语义向量）；无 key / 断网自动降级为本地 crc32 特征哈希（确定性、离线可跑）。
- **检索**：`0.6 * 余弦 + 0.4 * BM25` 混合，中文按「单字 + 双字」切分（不依赖分词库）。
- **生成**：检索 top-5 → 系统提示「只依据知识库回答，禁止编造，[编号] 引用」→ qwen-plus；LLM 挂了 / 没配 key → **软降级**返回最佳命中原文，系统永远可用。
- **规则门**：带商品标题提问时先跑硬性规则（违禁词 / 属性值 ≤50 / 属性名 ≤20 / 商品名 ≤255），命中直接拦截、不生成回答。

## 快速开始

```bash
pip install -r requirements.txt

# 1) 解析桌面 Excel 语料源 → corpus/*.jsonl + 违禁词表
python tools/build_corpus.py --src "C:\Users\zwx\Desktop\新建文件夹"

# 2) 建索引（可选配置 embedding.local.json 用真语义向量）
python scripts/build_index.py --force

# 3) 起 Web 服务，浏览器打开 http://127.0.0.1:8000/
python scripts/launcher.py --server
```

或者交互菜单：

```bash
python scripts/launcher.py   # 回车默认起服务器
```

### 本地密钥配置（gitignored，不入库）

```bash
# config/embedding.local.json —— 真语义向量（可选，缺省用本地哈希）
{"endpoint":"https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
 "key":"sk-xxx","model":"text-embedding-v3"}
# config/llm.local.json —— 生成回答（可选，缺省降级为知识库原文）
{"endpoint":"https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
 "key":"sk-xxx","model":"qwen-plus"}
```

## API

| 端点 | 说明 |
|---|---|
| `GET /` | 对话页（`?q=` 问题，`&title=` 可选商品标题触发上架判定） |
| `GET /api/health` | 健康检查 |
| `GET /api/stats` | 语料统计 |
| `GET/POST /api/ask` | 问答。`POST` body: `{"q":"这个品能不能上架","title":"不锈钢折叠刀"}` |

`POST /api/ask` 返回结构：

```json
{
  "answer": "该商品命中硬性规则拦截,不建议上架。\nbanned:FAIL-1 hits: 折叠刀",
  "sources": [],
  "rule_check": {"passed": false, "rules": [
    {"name": "banned", "passed": false, "detail": "1 hits: 折叠刀", "hits": ["折叠刀"]},
    {"name": "upload_spec", "passed": true, "detail": "all within limits"}
  ]}
}
```

## 语料

`corpus/schema.md` 定义 Q&A 格式（question / answer / category / tags / markets）。来源：

| 源表 | 产出 | 类别 |
|---|---|---|
| 快捷回复 / 常见问题助理 / 客服的问题汇总 / 退货退款 | `qa_faq.jsonl` | 常见问题 / 快捷回复 |
| 违禁自动刊登关键词 | `qa_rules.jsonl` + `banned_keywords.json` | 违禁规则 |
| 佣金、支付费 / 类目佣金率 / 泰国税率 | `qa_pricing.jsonl` | 定价税费（**只聚合区间，不出明细**） |
| 定价 / 价卡 / 刷价（含真实 SKU/成本） | ❌ 永不打开 | — |

**脱敏守卫**：生成内容正则扫 6 位以上数字 / Seller-SKU 模式，命中即丢弃并记入 `data/parse_report.md`；原始 Excel 不入库。

## 目录结构

```
tiktok-shop-rag-bot/
  app/            config · io · corpus · vector(检索引擎) · rules(规则门) · llm(生成链路)
    routers/      api / pages（FastAPI）
    templates/    index.html（单页对话 UI，无前端构建）
  scripts/        build_index.py · launcher.py（一键启动器）
  tools/          build_corpus.py（Excel → 语料 + 违禁词表，含脱敏）
  corpus/         qa_manual.jsonl（种子）· qa_faq/rules/pricing.jsonl（生成）· schema.md
  config/         app.json · embedding.example.json · llm.example.json · banned_keywords.json
  data/           rag_qa.db（索引，gitignored）
```

## Roadmap

- [x] **主版本**：RAG 问答 + 规则拦截 + 语料生成 + 脱敏
- [ ] **审核 agent**：读上架表 → 逐行过硬规则 → 输出拦截报告（复用 `rules.py`，薄薄一层）
- [ ] **Phase 2 多语言 AI 客服**：语料加 `lang`/`markets` 字段已预留，买家语（EN/TH/VN）回复
- [ ] 语料扩充（真实上架反馈反哺规则）

## 免责声明

本项目的语料来源于个人经营积累的模板话术与公开的平台费率区间，已做脱敏（不包含真实定价 / SKU / 成本明细）。规则数据请以 TikTok Shop 官方最新政策为准。本项目仅用于个人学习与自研工具。
