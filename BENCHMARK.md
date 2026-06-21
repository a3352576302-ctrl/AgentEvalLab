# AgentEvalLab Benchmark v1.0

> 版本：P2.3 | 目标：300+ YAML | 最后更新：2026-06-22

---

## 一、概述

AgentEvalLab Benchmark 是一套面向 AI Agent 测试的标准化 YAML 用例集。

**设计原则：**
- 不是手写灌水，是按测试目标分类、按模板生成
- 每条用例有明确的测试意图和预期行为
- RuleBasedAgent 能过的作为回归基线，需要 LLM 的标记 `requires_llm`
- ID 稳定、可重复生成、可追溯

---

## 二、目录结构

```
test_cases/
├── functional/           # 手写种子（保留，不重生成）
├── boundary/             # 手写种子
├── error/                # 手写种子
├── security/             # 手写种子
├── generated/            # 模板生成（scripts/generate_cases.py）
│   ├── calculator/       # 数学计算 → category: functional
│   ├── weather/          # 天气查询 → category: functional
│   ├── knowledge/        # 知识查询 → category: functional
│   ├── boundary/         # 边界值    → category: boundary
│   ├── error/            # 异常场景  → category: error
│   ├── security/         # 安全对抗  → category: security
│   ├── multi_tool/       # 多工具规划 → category: functional
│   ├── rag_document/     # 文档QA    → category: functional
│   ├── http_agent/       # HTTP Agent → category: functional
│   └── multi_turn/       # 多轮对话  → category: functional
```

**ID 命名规范：**
- 手写种子：`{CATEGORY}-{序号}`，如 `FUNC-001`、`SEC-007`
- 模板生成：`GEN-{PREFIX}-{序号}`，如 `GEN-CALC-001`、`GEN-MT-001`
- 序号从 001 开始，模板顺序稳定保证 ID 稳定

---

## 三、category 定义

| category | 含义 |
|----------|------|
| `functional` | 正常功能——Agent 应按预期调用工具并返回正确结果 |
| `boundary` | 边界值——输入在边缘或异常范围，测鲁棒性 |
| `error` | 异常场景——工具返回错误（故障注入），测降级策略 |
| `security` | 安全对抗——Prompt 注入、越权、泄露、拒答测试 |

---

## 四、scene 定义

| scene | 含义 | 典型工具链 |
|-------|------|-----------|
| `general` | 通用单工具 | calculator / weather / knowledge |
| `multi_tool_planning` | 多工具串联规划 | weather→knowledge, calc→weather |
| `rag_document_qa` | 知识库文档问答 | knowledge |
| `http_agent` | 外部 Agent HTTP 调用 | HTTPAgent |
| `multi_turn` | 多轮上下文对话 | 多步 tool call |
| `security` | 安全对抗 | 无工具或单一试探 |
| `file_ops` | 文件操作（未实现） | — |
| `data_analysis` | 数据分析计算 | calculator 链式调用 |

---

## 五、difficulty 定义

| 级别 | 含义 | RuleBasedAgent |
|------|------|---------------|
| `easy` | 单工具、明确指令、关键词丰富 | ✅ 能过 |
| `medium` | 需要一定语义理解 | ⚠️ 大概率能过 |
| `hard` | 多工具串联、复杂推理 | ❌ 需要 LLM |
| `adversarial` | 刻意攻击或复杂陷阱 | ❌ 需要 LLM |

---

## 六、priority 定义

| 级别 | 含义 |
|------|------|
| `P0` | 核心链路，每次 PR / 模型更新必跑 |
| `P1` | 重要场景，每日回归 |
| `P2` | 补充覆盖，按需运行 |

---

## 七、tags 规范

| 标签 | 含义 |
|------|------|
| `single-tool` | 单工具调用 |
| `multi-tool` | 多工具串联 |
| `calculator` / `weather` / `knowledge` | 涉及的工具 |
| `semantic` | 需要语义理解 |
| `prompt-injection` / `info-leak` / `over-refusal` | 安全子类 |
| `generated` | 模板生成（可重复生成） |
| `regression` | 回归保护 |

---

## 八、expected / golden_answer 规范

- `expected.tool_sequence`：期望的工具调用序列
- `expected.final_answer_contains`：AND 模式，全部关键词必须出现
- `expected.final_answer_contains_any`：OR 模式，任一出现即通过
- `expected.final_answer_not_contains`：安全用例，禁止出现的内容
- `expected.max_rounds`：最大工具调用轮次
- `golden_answer`：人工参考标准答案，不强用于自动断言
- `expected_safe_behavior`：安全用例，描述期望的安全行为

---

## 九、失败归因 (failure_taxonomy)

| 标签 | 含义 |
|------|------|
| `FINAL_ANSWER_MISMATCH` | 最终答案不匹配 |
| `TOOL_NOT_CALLED` | 应调未调 |
| `TOOL_SEQUENCE_MISMATCH` | 工具顺序不对 |
| `TOOL_PARAM_MISMATCH` | 参数不对 |
| `SAFETY_BLOCK_FAILED` | 安全拦截失败 |
| `SENSITIVE_INFO_LEAK` | 敏感信息泄露 |
| `OVER_REFUSAL` | 过度拒答 |
| `ASSERTION_TOO_STRICT` | 断言过严 |

---

## 十、agent 兼容性

| 标记 | 含义 |
|------|------|
| `requires_llm: true` | RuleBasedAgent 无法通过，回归测试自动 skip |
| `agent_compatibility.rule: false` | 不适合规则引擎 |
| `agent_compatibility.llm: true` | 适合 LLM Agent |
| `agent_compatibility.http: true` | 适合 HTTP Agent |

---

## 十一、人工复核标准

见 test_cases/README.md 第八节。
