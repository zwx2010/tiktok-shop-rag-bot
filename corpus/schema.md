# 语料格式 schema

`corpus/*.jsonl` 每行一条 JSON,字段如下:

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 唯一标识,如 `manual-001` / `faq-0012` |
| `question` | 是 | 运营/买家会问的问题(检索匹配文本) |
| `answer` | 是 | 规范回答 |
| `category` | 建议 | 归类:常见问题 / 快捷回复 / 退货退款 / 违禁规则 / 上传规格 / 定价税费 |
| `tags` | 建议 | 标签数组,参与检索(属性名/变体值/佣金/税率…) |
| `source` | 建议 | 语料来源,如 `话术库/常见问题助理` |
| `lang` | 否 | 语言,默认 `zh`(Phase 2 多语言客服用) |
| `markets` | 否 | 市场代码数组 `["ph","th","vn"]`,空 = 通用 |

## 示例

```json
{"id":"manual-001","question":"变体值最多能填多少字符？","answer":"TikTok Shop 变体属性值上限 50 个字符。","category":"上传规格","tags":["变体","属性值","字符","上传"],"source":"种子语料","lang":"zh","markets":[]}
```

## 生成与维护

- `qa_manual.jsonl` — 手写种子,人工维护,永远存在。
- `qa_faq.jsonl` / `qa_rules.jsonl` / `qa_pricing.jsonl` — 由
  `python scripts/launcher.py --ingest`(tools/build_corpus.py)从桌面 Excel
  生成,可反复重跑覆盖。
- 生成脚本含脱敏守卫:原始 Excel 的定价/价卡/刷价表永不打开,生成内容
  正则扫 6 位以上数字 / Seller-SKU 模式,命中即丢弃。

## 数据来源

本地私有,不入库: `C:\Users\zwx\Desktop\新建文件夹\常用话术参考模板参考.xlsx`(话术)
+ `原表5.xlsx`(定价税费,只聚合区间)。
