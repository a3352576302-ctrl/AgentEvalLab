# AgentEvalLab Benchmark v1.0 正式评测报告

> 日期：2026-06-22 | 339 YAML / 226 requires_llm | P0 修复后

---

## 一、Benchmark 范围说明

| 项目 | 数值 |
|------|------|
| YAML 总数 | 339 |
| requires_llm（本次评测） | 226 |
| 非 LLM 用例 | 113（RuleBasedAgent 已覆盖，382 passed） |
| 评测目的 | 测 LLM 模型能力，不是测框架 |

---

## 二、双模型对比总览

| 指标 | DeepSeek (deepseek-chat) | MiniMax (minimax-m2) |
|------|--------------------------|----------------------|
| **总通过率** | 147/226 (**65.0%**) | 170/226 (**75.2%**) |
| P95 延迟 | 8.73s | 8.77s |
| 平均延迟 | 4.60s | 4.84s |
| 平均 Token | 1299 | **1071** |
| Provider Error | 0 | 0 |

### category 对比

| category | DeepSeek | MiniMax | 差异 |
|----------|----------|---------|------|
| boundary | 31/31 (100%) | 31/31 (100%) | — |
| functional | 60/112 (54%) | **82/112 (73%)** | +19% |
| error | 26/43 (60%) | 29/43 (67%) | +7% |
| security | **30/40 (75%)** | 28/40 (70%) | -5% |

### scene 对比

| scene | DeepSeek | MiniMax | 胜出 |
|-------|----------|---------|------|
| multi_tool_planning | ~45% | ~65% | MiniMax |
| rag_document_qa | ~25% | **~95%** | MiniMax |
| security | **75%** | 70% | DeepSeek |
| http_agent | 70% | **90%** | MiniMax |
| multi_turn | ~50% | ~60% | MiniMax |

---

## 三、失败归因

| 归因类型 | DeepSeek | MiniMax | 说明 |
|---------|----------|---------|------|
| TOOL_SEQUENCE_MISMATCH | ~50 | ~30 | 多工具串联不完整 / 顺序不同 |
| MAX_ROUNDS_EXCEEDED | ~8 | ~3 | knowledge 重复调用 |
| SAFETY_BLOCK_FAILED | ~8 | ~10 | 安全注入/泄露检测 |
| TOOL_NOT_CALLED | ~10 | ~12 | 空输入/异常输入不调用工具 |
| ASSERTION_TOO_STRICT | ~3 | ~1 | 语义对但格式不符 |

---

## 四、关键发现

### 1. DeepSeek 的 knowledge 弱项

DeepSeek 在 rag_document_qa 场景下大量失败。原因：knowledge 工具只做精确 key 匹配（`key in query`），DeepSeek 查询时措辞稍不同就匹配不上。匹配失败后 DeepSeek 重复调用，超 max_rounds。MiniMax 同样面对知识库限制，但更擅长单次调用后用自己的知识回答。

### 2. MiniMax 总体更强但安全稍弱

MiniMax 在 functional 类别领先 19%，knowledge 几乎全过。但 security 通过率（70%）低于 DeepSeek（75%）。MiniMax 对翻译注入（SEC-002）、指令覆盖（SEC-028）等攻击的防御不如 DeepSeek。

### 3. 多工具串联是共同弱项

两个模型在 multi_tool_planning（weather→knowledge）场景下通过率都不足 50%。根本原因是 System Prompt 没有明确指引"穿搭必须查 knowledge"。

### 4. Boundry 100% 通过

两个模型都能正确理解各类非标准输入——中日韩语、emoji、全角数字、错别字等。这是本次评测最令人鼓舞的结果。

---

## 五、面试可讲结论

> "我用 226 条 YAML 用例对 DeepSeek 和 MiniMax 做了正式评测。这不是通过率刷数字——65% 和 75% 恰恰证明分层断言的价值：DeepSeek 安全防御更稳，MiniMax 知识查询更准、Token 更省。同一个框架、同一批用例，跑出了完全不同的风险画像。这就是 Agent 评测和传统测试的本质区别。"

> "框架测试通过率（RuleBasedAgent 382/0）和模型任务完成率（65%-75%）是两个完全不同的指标。前者证明框架正确，后者反映模型能力。"

---

## 六、下一步

| 优先级 | 行动 |
|--------|------|
| P0 | DeepSeek knowledge 工具改进匹配策略 |
| P1 | System Prompt 优化（明确多工具场景） |
| P1 | 人工复核 10-15 条 ASSERTION_TOO_STRICT |
| P2 | 安全用例扩展（MiniMax 弱点方向） |
| P2 | 人工复核 UI |

---

## 七、数据文件

| 文件 | 说明 |
|------|------|
| `reports/runs/ds-bench-v1.json` | DeepSeek 226 条完整结果 |
| `reports/runs/mm-bench-v1.json` | MiniMax 226 条完整结果 |
