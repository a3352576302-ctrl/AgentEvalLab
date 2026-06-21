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
