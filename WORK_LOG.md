# P0 工作日志

> 项目：AgentEvalLab | 启动：2026-06-21 | 基线：197 passed

---

## 2026-06-21：阶段 1 — 用例体系标准化 ✅

**做了什么：**
- 新增 `agentevallab/case_schema.py`：YAML 元数据校验 + 默认值填充
- 新增字段（全部可选）：scene, difficulty, priority, golden_answer, golden_tool_trace, expected_safe_behavior, failure_taxonomy
- 旧 YAML 缺字段 → 自动填充默认值，不报错
- 集成到 `runner.py` 的 `load_yaml_case`，校验 + 警告输出
- 新增 `tests/test_case_schema.py`（9 条测试）

**为什么这样做：**
- 用例体系标准化是 P0 基础——后续报告、归因、安全都依赖统一的元数据
- 旧 YAML 必须兼容，不能为了新字段改 46 条用例
- 校验和默认值分离，保证加载不中断

**改了哪些文件：**
- 新增：agentevallab/case_schema.py
- 新增：tests/test_case_schema.py
- 修改：agentevallab/runner.py（集成 schema 校验）

**测试结果：**
- 206 passed (+9)，0 failed

**遇到的坑：**
- `result.data` 和局部 `data` 变量引用分离 → 改为直接操作 `result.data`
- 空字符串 `input: ""`（BOUND-003）被误判为缺失 → 放宽校验，只拦截 None 和不存在

**下一步：** 阶段 2 — 失败归因分类器（error_classifier.py）

---

## 2026-06-21：阶段 2 — 失败归因分类器 ✅

**做了什么：**
- 新增 `agentevallab/error_classifier.py`：17 种错误标签
- 三大类：断言失败（9 种）、Provider 错误（5 种）、特殊模式（3 种）
- `classify_error(result)` → 单条归因
- `classify_results(results)` → 批量统计
- `get_taxonomy_description(label)` → 中文说明

**为什么这样做：**
- 失败不只是 pass/fail——面试官问"为什么失败"时，你能答出具体类型
- 报告系统（阶段 4）需要结构化归因数据
- 区分"模型答错了"和"API 挂了"和"断言太严"

**改了哪些文件：**
- 新增：agentevallab/error_classifier.py
- 新增：tests/test_error_classifier.py（16 条测试）

**测试结果：**
- 222 passed (+16)，0 failed

**下一步：** 阶段 3 — 真实 API 稳定性（retry + backoff + run_store）

---

## 2026-06-21：阶段 3 — 真实 API 稳定性 ✅

**做了什么：**
- `llm_agent.py`：新增 retry + exponential backoff（1s/2s/4s，最多 3 次）
- `_is_retryable()`：区分可重试（429/5xx/超时/网络）和不可重试（401/402/403/400）
- `agentevallab/run_store.py`：运行结果 JSON 持久化
  - `save_run()` / `load_run()` / `list_runs()`
  - `get_completed_case_ids()`：续跑时跳过已完成用例
- `tests/test_run_store.py`：8 条测试

**为什么这样做：**
- API 不可能永远稳定——retry 是生产级调用的底线
- 不可重试错误（如 401 key 错了）应该立即失败，不浪费时间
- run JSON 落盘后，阶段 4 的 HTML 对比报告可以直接读取历史数据

**改了哪些文件：**
- 修改：agentevallab/llm_agent.py（retry + _is_retryable）
- 新增：agentevallab/run_store.py
- 新增：tests/test_run_store.py

**测试结果：**
- 230 passed (+8)，0 failed

**遇到的坑：**
- `max_retries` 参数加了但忘记 `self.max_retries = max_retries` → AttributeError

**下一步：** 阶段 4 — HTML 报告增强（归因 + trace + 模型对比）

---

## 2026-06-21：阶段 4 — HTML 报告增强 ✅

**做了什么：**
- 新增"框架测试通过率 vs 模型任务完成率"双指标展示
- 新增失败归因 Top 5 卡片
- 失败用例详情：每条的归因标签 + 完整 tool trace（可展开）+ Token 信息
- `build_html_report` 支持 `compare_run`、`provider`、`model` 参数

**为什么这样做：**
- 面试官看报告时，要能一眼区分"框架测试结果"和"模型真实能力"
- 归因标签让失败不只是一个 fail，而是能解释原因
- trace 展开让调试时不用翻终端日志

**改了哪些文件：**
- 修改：agentevallab/reporter.py（build_html_report + import error_classifier）

**测试结果：**
- 230 passed，HTML 报告正常生成

**下一步：** 阶段 5 — 安全用例扩展

---

## 2026-06-21：阶段 5 — 安全用例扩展 ✅

**做了什么：**
- 新增 5 条安全用例：间接注入(SEC-008)、提示词窃取(SEC-009)、过度拒答(SEC-010)、工具名注入(SEC-011)、参数溢出(SEC-012)
- 每条含 `expected_safe_behavior` 字段
- 从 7 条扩展到 12 条安全用例

**为什么这样做：**
- 安全测试是面试差异化优势
- P0 计划要求至少覆盖 Prompt 注入、间接注入、越权、泄露、窃取、溢出

**改了哪些文件：**
- 新增：test_cases/security/SEC-008 ~ SEC-012（5 条 YAML）

**测试结果：**
- 235 passed (+5)，0 failed

**遇到的坑：**
- YAML 不支持 Python 表达式（SEC-012 用了字符串拼接）
- RuleBasedAgent 关键词匹配需要输入里有关键词（SEC-008/010 的输入调优）

**下一步：** 阶段 6 — 文档更新 + 最终验证

---

## 2026-06-21：P0 闭环修复 ✅

**修复的"未接入主流程"问题：**

1. **run_report.py 接入 run_store：**
   - 新增 `--save-run`：保存 reports/runs/{run_id}.json
   - 新增 `--run-id`：指定运行 ID
   - 新增 `--resume RUN_ID`：跳过已完成用例，续跑
   - 新增 `--compare-run RUN_ID`：加载历史运行对比

2. **reporter.py provider/model 传入：**
   - `build_html_report()` 的 provider/model 从 CLI 传入
   - 新增"框架测试通过率 vs 模型任务完成率"双指标卡片
   - 新增 `compare_run` 对比表（provider/model/通过率/通过/失败）

3. **Provider 错误归因断层修复：**
   - `error_classifier.py`：同时检查 case_result.error 和 trajectory.final_answer
   - LLMAgent 把错误写入 final_answer 后，error_classifier 能从 "LLM 调用失败" 中识别 401/429/400/timeout
   - 新增 3 条 Provider→error_classifier 联动测试

4. **Retry 测试补全：**
   - 429 重试 ✅
   - 500 重试 ✅
   - Timeout 重试 ✅
   - 401 不重试 ✅
   - 400 不重试 ✅
   - 402 不重试 ✅
   - max_retries 生效 ✅

**验证：**
- 245 passed (+10 新测试)
- `--save-run` 生成 run JSON ✅
- `--help` 显示所有新参数 ✅
- HTML 报告显示 provider + 双指标 ✅

**生成的 run JSON 位置：** reports/runs/{run_id}.json

**下一步：** 真实 API 评测（需要 API Key）
