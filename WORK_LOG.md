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
