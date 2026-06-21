# P0 实施计划

> 创建日期：2026-06-21
> 原则：增强而非重写，兼容旧数据，测试不倒退

---

## 一、当前项目现状

### 已有能力 ✅

| 维度 | 现状 |
|------|------|
| 用例体系 | 46 条 YAML，4 类（functional/boundary/error/security） |
| 断言引擎 | L1-L6，OR 语义、参数归一化、拒答放行、Token 检查 |
| 模型接入 | DeepSeek + MiniMax，provider 选择逻辑完善 |
| 故障注入 | 6 种，装饰器实现 |
| 报告 | 控制台 + HTML，P50/P95/P99 延迟，Token 统计 |
| CI/CD | GitHub Actions 🟢，197 passed |
| 文档 | README/DESIGN/IMPL_NOTES 完善 |

### P0 差距 ❌ → 目标 ✅

| 差距 | 目标 |
|------|------|
| 失败原因靠人工读报告 | 自动归因分类 |
| 无法区分"框架测试通过率"和"模型任务完成率" | 报告明确区分 |
| HTML 报告无 trace | 展示每次 tool call 详情 |
| 无模型对比视图 | 单页面对比 DeepSeek vs MiniMax |
| YAML 元数据简单 | 增加 scene/difficulty/golden_answer |
| API 调用无重试 | retry + backoff + 错误分类 |
| 中断后从头跑 | 支持续跑 |
| 安全用例 7 条 | 扩展至 12+ 条 |
| 无结构化运行记录 | run JSON 落盘 |

---

## 二、不做什么（防范围失控）

- ❌ 不做 Web Dashboard / 前端
- ❌ 不做数据库存储
- ❌ 不做 Docker / docker-compose
- ❌ 不做 LLM-as-Judge（P1）
- ❌ 不做 baseline 回归系统（P1）
- ❌ 不改已有 YAML 的必填字段（向后兼容）
- ❌ 不引入重型依赖

---

## 三、新增文件清单

```
agentevallab/
├── case_schema.py          # 新增：YAML 元数据校验 + 默认值
├── error_classifier.py     # 新增：失败归因分类器
├── run_store.py            # 新增：运行结果 JSON 落盘 + 续跑
│
test_cases/
├── security/               # 扩展 5+ 条安全用例
│
tests/
├── test_case_schema.py     # 新增
├── test_error_classifier.py # 新增
├── test_run_store.py       # 新增
│
P0_IMPLEMENTATION_PLAN.md   # 本文件
WORK_LOG.md                 # 实施日志
```

## 四、修改文件清单

```
agentevallab/
├── llm_agent.py     # retry + backoff + 错误分类 + run_id 注入
├── runner.py        # resume 续跑 + trace 扩展 + 结构化结果
├── reporter.py      # HTML 增强：trace、归因、模型对比、区分通过率
├── assertions.py    # 断言结果增加 failure_taxonomy 字段
├── trajectory.py    # 新增 run_id/case_id/trace_id 字段
│
scripts/
├── run_report.py    # --resume 参数
│
test_cases/
├── README.md        # 新增：用例编写规范
│
README.md            # 更新当前能力描述
DESIGN.md            # 更新架构
IMPL_NOTES.md        # 记录 P0 变更
```

---

## 五、分阶段实施

### 阶段 1：用例体系标准化

**目标：** YAML 支持更多元数据，旧用例不受影响。

**新增字段（全部可选，有默认值）：**
- `scene`: 应用场景（customer_service/coding/search/...）
- `difficulty`: easy / medium / hard / adversarial
- `priority`: P0 / P1 / P2
- `golden_answer`: 标准答案文本
- `golden_tool_trace`: 标准工具调用轨迹
- `failure_taxonomy`: 预期失败类型

**实现：**
- `case_schema.py`：`validate_case(case_dict)` 函数，填充默认值，校验类型
- `runner.py` 加载时调用 `validate_case`
- 旧 YAML 缺字段 → 自动填默认值 → 不报错

**验证：** pytest 197 passed + 新增 test_case_schema.py

---

### 阶段 2：失败归因分类器

**目标：** 失败不再只是 pass/fail，而是有分类标签。

**分类标签：**
```
FINAL_ANSWER_MISMATCH    — 答案关键词缺失
TOOL_NOT_CALLED          — 该调的工具没调
WRONG_TOOL_CALLED        — 调了不该调的工具
TOOL_SEQUENCE_MISMATCH   — 工具顺序错
TOOL_PARAM_MISMATCH      — 参数不匹配
MAX_ROUNDS_EXCEEDED      — 超轮次
SAFETY_BLOCK_FAILED      — 安全拦截失败
SENSITIVE_INFO_LEAK      — 敏感信息泄露
OVER_REFUSAL             — 过度拒答
PROVIDER_AUTH_ERROR      — API 认证错误
PROVIDER_RATE_LIMIT      — 限流
PROVIDER_TIMEOUT         — 超时
PROVIDER_NETWORK_ERROR   — 网络错误
PROVIDER_BAD_REQUEST     — 请求格式错误
ASSERTION_TOO_STRICT     — 断言过严（语义对但字面不对）
UNKNOWN_ERROR            — 兜底
```

**实现：**
- `error_classifier.py`：`classify_error(case_result) → list[str]`
- 从 AssertionResult.reason 和 trajectory 中提取分类
- 集成到 CaseResult，每次执行自动分类

**验证：** test_error_classifier.py

---

### 阶段 3：真实 API 稳定性

**目标：** API 调用不再脆弱，中断可续跑。

**核心改动：**
1. `llm_agent.py`：
   - 每次 API 调用加 `retry`（最多 3 次，指数退避 1s/2s/4s）
   - 区分 401/429/5xx/网络错误
   - 错误信息标准化，包含 provider_error_type
   - 自动生成 `run_id`

2. `runner.py`：
   - `run_case` 注入 `run_id` + `case_id`
   - `load_and_run_all` → 新增 `resume_from` 参数
   - 跳过已有结果的 case

3. `run_store.py`：
   - `save_run(run_id, results)` → JSON 落盘 `reports/runs/{run_id}.json`
   - `load_run(run_id)` → 读取已有结果
   - `list_runs()` → 列出历史运行

**验证：** test_run_store.py + mock 验证 retry 逻辑

---

### 阶段 4：HTML 报告增强

**目标：** 报告能讲清楚"为什么失败"和"两个模型差在哪"。

**HTML 报告新增：**
1. 顶部区分两个指标：
   - **框架测试通过率**（断言全部通过）
   - **模型任务完成率**（L1 结果层通过的占比）
2. 失败归因 Top N 饼图或条形图（CSS only）
3. 模型对比表（如果提供了多份 run JSON）
4. 每条失败用例的 trace 展开：tool name / params / result / latency
5. assertion 明细：哪个断言失败 + 原因 + 归因分类

**实现：**
- `reporter.py`：`build_html_report` 增强
- 新增参数：`compare_runs: list[dict]` 用于多模型对比
- CSS 全部内联，无外部依赖

**验证：** 生成报告 → 浏览器能看到归因 + trace + 对比

---

### 阶段 5：安全用例扩展

**目标：** 从 7 条扩展到 12+ 条。

**新增用例：**
```
SEC-008: 间接 Prompt 注入（通过工具参数注入）
SEC-009: 系统提示词窃取
SEC-010: 过度拒答（正常问题被误判为攻击）
SEC-011: 工具名注入（输入中包含伪造的工具调用）
SEC-012: 参数溢出（超长输入 / 特殊字符）
```

每个新用例含 `expected_safe_behavior` 字段。

**验证：** 新用例 RuleBasedAgent 模式下通过，安全断言生效。

---

### 阶段 6：文档和验证

- 更新 README/DESIGN/IMPL_NOTES
- 全量 pytest 通过
- 生成 WORK_LOG.md 和 CHANGELOG_P0.md

---

## 六、风险点

| 风险 | 缓解 |
|------|------|
| YAML schema 改动破坏旧用例 | 所有新字段可选，有默认值 |
| retry 逻辑引入新 bug | 充分的 mock 测试 |
| HTML 报告复杂度膨胀 | CSS only，不引入 JS 框架 |
| 安全用例误判 | 新用例先跑 RuleBasedAgent 验证 |

---

## 七、验证标准

```bash
pytest tests/ -v          # ≥ 197 passed
python scripts/run_report.py --html-only     # 报告可打开
python scripts/run_report.py --agent rule    # 旧模式仍可用
```
