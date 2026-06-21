# AgentEvalLab 测试用例规范

> 版本：v1.0 | 用例总数：150+ | 最后更新：2026-06-22

---

## 一、用例来源

| 来源 | 目录 | 说明 |
|------|------|------|
| 手写种子用例 | `functional/` `boundary/` `error/` `security/` | 51 条核心场景，人工设计 |
| 模板生成用例 | `generated/` | 80-100 条，`scripts/generate_cases.py` 从模板批量生成 |
| 场景用例 | `scenarios/` | 20+ 条，覆盖多工具规划、文档QA、数据分析等真实场景 |

---

## 二、分类体系

| category | 含义 | 示例 |
|----------|------|------|
| `functional` | 正常功能——Agent 应按预期调用工具 | 计算器、天气查询、知识查询 |
| `boundary` | 边界值——输入在边缘或异常范围 | 超大数、空输入、不存在的城市 |
| `error` | 异常场景——工具返回错误，测降级策略 | 超时、500、脏数据 |
| `security` | 安全对抗——Prompt 注入、越权、泄露 | 注入攻击、角色越狱 |
| `scenarios` | 真实场景——模拟业务任务 | 多工具规划、文档QA、数据分析 |

---

## 三、difficulty 定义

| 级别 | 含义 | 判定标准 |
|------|------|---------|
| `easy` | 单工具、明确指令 | RuleBasedAgent 能过 |
| `medium` | 需要语义理解和基本推理 | LLM 大概率能过 |
| `hard` | 多工具串联、对抗性输入 | LLM 可能失败 |
| `adversarial` | 刻意攻击或复杂陷阱 | 期待 LLM 拒答或复杂推理 |

---

## 四、priority 定义

| 级别 | 含义 |
|------|------|
| `P0` | 核心链路，每次 PR 必跑 |
| `P1` | 重要场景，每日回归 |
| `P2` | 补充覆盖，按需运行 |

---

## 五、tags 规范

| 标签 | 含义 |
|------|------|
| `single-tool` | 单工具调用 |
| `multi-tool` | 多工具串联 |
| `calculator` / `weather` / `knowledge` | 涉及的工具 |
| `highlight` | 面试展示用 |
| `adversarial` | 对抗性 |
| `prompt-injection` / `info-leak` / `over-refusal` | 安全子类 |
| `regression` | 回归保护 |
| `semantic` | 语义等价判断场景 |

---

## 六、golden_answer 规范

`golden_answer` 是人工标注的标准答案文本，**不强用于自动断言**。

- 用于人工复核时的参考基准
- 格式：自然语言，覆盖关键信息点
- 对于拒答类用例，写 `"应拒答"`

---

## 七、expected_tool_trace 规范

`golden_tool_trace` 是标准工具调用轨迹，格式：

```yaml
golden_tool_trace:
  - tool: "weather"
    params: { city: "北京" }
    expected_result: "包含温度、天气状况"
```

- 用于人工参考，非自动断言（LLM 的合理路径可能不同）
- 安全类和边界类不强制填写

---

## 八、人工复核标准

| reviewer_decision | 含义 | 何时使用 |
|-------------------|------|---------|
| `correct` | 断言判定正确 | 确实是模型错误 |
| `incorrect` | 断言判定错误 | 模型答案正确但断言过严 |
| `semantic_equivalent` | 语义等价 | 答案意思对但表述不同 |
| `assertion_too_strict` | 断言过严 | 需要放宽匹配规则 |
| `update_golden_answer` | 更新标准答案 | 原有 golden_answer 不准确 |
| `ignore` | 忽略 | 非关键失败，暂不处理 |

---

## 九、RuleBasedAgent 限制

以下类别的用例 RuleBasedAgent（关键词匹配）无法通过，专为 LLMAgent 设计：

| 类别 | 原因 | 条数 |
|------|------|------|
| `generated/calculator` 含语义标签 | 中文数字、文字嵌入需要语义理解 | 5 |
| `generated/knowledge` | 知识库 key 不完全匹配，需要模糊理解 | 7 |
| `generated/security` 含 JSON/编码注入 | 复杂注入模式需要推理 | 2 |
| `generated/weather` 部分用例 | "气温""中文变异"不在关键词列表 | 2 |
| `scenarios/*` 全部 | 多工具串联、语义理解、上下文推理 | 13 |

> **总数：** 29 条需要 LLM。365 条 pytest 通过（RuleBasedAgent 能过的全过）。

## 十、新增用例规范

新增用例必须：
1. 遵循 `case_schema.validate_case()` 的字段规范
2. `id` 命名规则：`{PREFIX}-{序号}`，如 `FUNC-023`、`GEN-CALC-001`
3. 所有新字段（scene/difficulty/priority/golden_answer）建议填写
4. 不破坏已有用例
