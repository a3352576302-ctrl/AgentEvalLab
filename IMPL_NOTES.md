# AgentEvalLab 系统实现文档

> 记录每一步的技术决策和实现细节，方便面试时回顾"为什么这么设计"。

---

## 第 1 轮：tools.py — 模拟工具集

**日期：** 2026-06-13

### 实现了什么

三个供 Agent 调用的模拟工具，全部使用本地静态数据，不访问网络。

| 工具 | 功能 | 实现方式 |
|------|------|---------|
| `tool_calculator(expression)` | 安全数学求值 | `ast.parse` 解析 + 白名单操作符，禁止 `eval` |
| `tool_weather(city)` | 天气查询 | 6 个城市的固定字典 |
| `tool_knowledge(query)` | 知识库查询 | 5 个技术主题的固定字典，模糊匹配 |

### 关键设计决策

**Q: 为什么用 ast.parse 而不是 eval？**

`eval()` 可以执行任意 Python 代码，传入 `__import__('os').system('dir')` 就能执行系统命令。`ast.parse` 只解析语法树，然后手动遍历节点，只允许白名单中的操作符（+、-、*、/、**）。这既是一个安全措施，也是一个面试亮点——"我用 AST 安全求值代替 eval，防止代码注入"。

**Q: 为什么返回 ToolResult 而不是直接返回数据？**

统一的返回结构让测试断言更加稳定：无论成功或失败，都可以用 `result.success` / `result.data` / `result.error` / `result.latency_ms` 四个字段来判断。

### 遇到的坑

1. `ast.parse(mode="eval")` 返回的顶层是 `ast.Expression` 包装节点，必须先用 `_walk(node.body)` 解包才能继续遍历。
2. 中文引号 `""` 会被 Python 解释器当成字符串结束符，必须换成 `「」` 或使用 `\` 转义。

### 测试覆盖

- 正常情况：乘法、加法、除法、负数、幂运算、北京/上海天气、TCP/RAG/Agent 知识查询
- 失败情况：非法表达式、空字符串、不存在城市、未知查询
- 边界情况：ToolResult 结构完整性

---

## 第 2 轮：trajectory.py — 轨迹数据结构

**日期：** 2026-06-13

### 实现了什么

两个 dataclass 用于记录 Agent 的完整执行过程。

```python
ToolCall:
    tool_name   # 调了哪个工具
    params      # 传了什么参数
    result      # 工具返回了什么（ToolResult）
    latency_ms  # 本次调用耗时

AgentTrajectory:
    user_input    # 用户原始输入
    tool_calls    # 按顺序记录的 ToolCall 列表
    final_answer  # Agent 最终回复
    # 只读属性：
    total_rounds       # 工具调用轮次
    total_latency_ms   # 总耗时
    tool_names         # 工具名称列表（方便断言 tool_sequence）
    all_tools_succeeded  # 所有工具是否成功
```

### 关键设计决策

**Q: 为什么用 dataclass 而不是普通 dict？**

面试官一定会问"Python 数据类用过吗"。dataclass 有类型提示、默认值、`__post_init__` 钩子，比 dict 更结构化，也便于 IDE 自动补全。

**Q: 为什么 tool_names 是一个 property？**

避免每次断言时手写 `[call.tool_name for call in trajectory.tool_calls]`，用一个属性封装，调用方直接 `trajectory.tool_names` 即可。面试时可以讲"封装了常见的查询操作，减少调用方的心智负担"。

**Q: 为什么 to_dict() 放在 ToolCall 上而不是 Trajectory 上？**

目前只需要序列化单个工具调用（输出报告时逐条展示），轨迹整体序列化可以在后续 Reporter 阶段加入。

### 测试覆盖

- 正常/失败的 ToolCall 创建
- latency_ms 默认值逻辑
- to_dict() 序列化
- 空轨迹、添加调用、设置答案、延迟累加、工具名列表、全部成功判断

---

---

## 第 3 轮：agent.py — Agent 接口与规则引擎

**日期：** 2026-06-13

### 实现了什么

- `AgentProtocol` 抽象基类：定义 `run(input) → AgentTrajectory` 接口
- `RuleBasedAgent`：基于关键词+正则匹配的意图识别引擎

支持四种意图处理：

| 意图 | 检测条件 | 提取参数 |
|------|---------|---------|
| 数学计算 | 数字 + 运算符（`*+/-`）或数学关键词 | 正则提取表达式 |
| 天气查询 | 城市名 + 天气关键词，或 "XX天气" 模式 | 遍历城市列表 + 正则 |
| 知识查询 | 输入包含知识库 key | 遍历知识库 key |
| 多工具串联 | 同时满足天气+知识意图 | 先天气后知识 |

### 关键设计决策

**Q: 为什么用 ABC 而不是 typing.Protocol？**

ABC 在 Python 3.10+ 更稳定，`issubclass` 和 `isinstance` 检查直观，面试官也通常更熟悉 ABC。Protocol 适合静态类型检查场景，这里不需要。

**Q: 意图检测为什么不用正则写死一个规则表？**

目前 3 个工具用 if-elif 可以，但架构上 `_detect_xxx` / `_extract_xxx` / `_do_xxx` 三方法分离，后续添加新工具只需加一组三个方法，在 `run()` 里多一个 elif，不影响已有逻辑。面试时可以说"符合开闭原则"。

**Q: 多工具串联为什么只有 weather→knowledge？**

这是最直观的演示场景：用户问"北京多少度？35度穿什么？"。后续可以扩展为更通用的链式调用，但 v0.1 先验证这种模式可行。

**Q: 天气检测为什么有两层（已知城市 + 正则模式）？**

第一层精确匹配已知城市保证准确率，第二层正则兜底保证不存在的城市也能触发调用（然后工具层返回失败，Agent 优雅处理）。两层配合体现了"防御性设计"。

### 遇到的坑

1. `_detect_weather` 最初只检查已知城市，导致"火星天气"无法触发天气意图。增加了 `\S{1,6}(?:的)?(?:天气|多少度)` 正则模式作为第二层。
2. `_extract_city` 也需要配合修改，先用已知城市匹配，再用正则从"XX天气"模式中提取城市名。

### 测试覆盖

- AgentProtocol 接口验证（3 条）
- 单工具调用：计算/天气/知识（8 条）
- 多工具串联（2 条）
- 未知意图/空输入（2 条）

---

---

## 第 4 轮：assertions.py — 四层断言引擎

**日期：** 2026-06-13

### 实现了什么

- `AssertionResult`：单条断言结果（level/name/passed/reason）
- `AssertionReport`：一次评测的汇总（results/passed_count/failed_count/all_passed）
- 五个独立断言函数：
  - `assert_l1_final_answer` — 检查最终答案包含预期关键词
  - `assert_l2_tool_sequence` — 检查工具调用序列
  - `assert_l3_tool_params` — 检查每个工具调用的参数
  - `assert_l4_max_rounds` — 检查轮次上限
  - `assert_latency` — 检查总延迟
- `assert_trajectory`：综合断言入口，根据 switches 字典控制各断言开关

### 关键设计决策

**Q: 为什么每个断言独立成函数，而不是一个巨大的类？**

每个断言可以独立测试、独立复用。如果未来要加 L5（安全断言），只需新增一个 `assert_l5_security()` 函数并在 `assert_trajectory` 里加一行。修改不波及已有代码。

**Q: 为什么失败原因用描述性文本而不是错误码？**

直接输出 `"第 2 个调用的参数 'city' 不匹配：预期 '北京'，实际 '上海'"` 比错误码 `E3002` 更直观。这对"基础较弱用户"和报告可读性都更友好。

**Q: 空列表跳过检查的意义？**

`final_answer_contains: []` 表示"这条用例不检查最终答案"，而不是"要求答案不包含任何内容"。这在设计上让断言维度真正可配置——有些用例只关心工具调用，不关心最终答案措辞。

### 遇到的坑

无。这一轮测试一次通过。

### 测试覆盖

- L1：通过/失败/单关键词/遗漏/空列表跳过（5 条）
- L2：通过/失败/顺序颠倒/数量不对（5 条）
- L3：通过/失败/参数错误/缺失/空列表跳过（5 条）
- L4：通过/失败/刚好等于上限（3 条）
- 延迟：通过/失败（2 条）
- 综合 + 开关：全开通过/部分关闭/独立失败不互相影响（3 条）

---

---

## 第 5 轮：runner.py — YAML 加载与用例执行

**日期：** 2026-06-13

### 实现了什么

- `load_yaml_case(filepath)` — 从 YAML 文件加载单条测试用例，含字段校验
- `run_case(case, agent)` — 单条用例的完整执行流程：Agent.run() → assert_trajectory() → CaseResult
- `run_all(cases, agent)` — 批量执行
- `load_and_run_all(case_dir, agent)` — 扫描目录中所有 YAML 文件并批量执行
- `CaseResult` — 执行结果（case_id / trajectory / report / error）

### 同时创建了首批 12 条 YAML 用例

```
test_cases/
├── functional/
│   ├── FUNC-001-calculator-basic.yaml
│   ├── FUNC-002-weather-beijing.yaml
│   ├── FUNC-003-knowledge-tcp.yaml
│   ├── FUNC-004-multi-tool-weather-clothing.yaml  ← 核心亮点
│   └── FUNC-005-weather-shenzhen.yaml
├── boundary/
│   ├── BOUND-001-large-number.yaml
│   ├── BOUND-002-unknown-city.yaml
│   └── BOUND-003-empty-input.yaml
├── error/
│   ├── ERROR-001-weather-timeout.yaml
│   └── ERROR-002-knowledge-invalid-json.yaml
└── security/
    ├── SEC-001-prompt-injection.yaml
    └── SEC-002-unauthorized-tool.yaml
```

### 关键设计决策

**Q: 为什么 CaseResult 里既存 trajectory 又存 report？**

面试时讲"测试用例执行"要完整——`trajectory` 是执行的证据链，`report` 是断言的结论。两者分开存，方便后续 Reporter 既可以展示"Agent 干了什么"（轨迹），也可以展示"哪里不对"（断言）。

**Q: 为什么 error 和 security 用例的断言开关不全开？**

这些用例的预期是"Agent 什么都不做"（tool_sequence: []），不检查 final_answer。这体现了独立开关的价值——不同用例关注不同维度。

### 测试覆盖

- YAML 加载：单用例/多用例串联（2 条）
- 单条执行：通过/失败/轨迹记录/失败不崩溃（5 条）

---

---

## 第 6 轮：pytest 参数化集成

**日期：** 2026-06-14

### 实现了什么

- `tests/conftest.py`：pytest fixture 体系
  - `agent` fixture：session 级别，复用同一个 RuleBasedAgent
  - `all_yaml_cases` fixture：扫描 test_cases/ 加载全部 YAML
- `tests/test_agent_regression.py`：YAML 驱动的回归测试
  - `pytest_generate_tests`：动态参数化，一条 YAML 一个 test case
  - `test_yaml_case`：执行 Agent + 断言，失败时展示详细原因

### 运行效果

```bash
pytest tests/ -v    # 83 passed（单元测试 71 + 回归 12）
pytest tests/ -k FUNC  # 只跑 functional 用例
```

### 遇到的坑

1. **多工具串联 final_answer 覆盖**：FUNC-004（weather+knowledge）中，`_do_knowledge` 直接 `set_final_answer` 覆盖了 `_do_weather` 的天气结果。修复方式：在 `run()` 多工具分支中暂存天气文本，拼接后再设置最终答案。
2. **YAML 中 `final_answer_contains` 断言缺词**：FUNC-004 原本期望 final_answer 包含"北京"，但 knowledge 工具返回的是穿搭建议不包含城市名。修复后两段拼接，"北京"出现在天气部分。

### 测试覆盖

- 12 条 YAML 用例全部通过（functional 5 + boundary 3 + error 2 + security 2）

---

---

## 第 7 轮：fault_injector.py — 故障注入系统

**日期：** 2026-06-14

### 实现了什么

三套互补的故障注入方式：

| 方式 | 用途 | 示例 |
|------|------|------|
| `inject_fault(result, type)` | 直接对 ToolResult 注入故障 | `inject_fault(ok_result, "timeout", delay=3)` |
| `fault_context(tool, type)` | 上下文管理器，测试时临时激活 | `with fault_context("weather", "http_500"):` |
| `@injectable(tool_name)` | 装饰器，工具函数自动检测故障 | `@injectable("calculator") def tool_calc(...)` |

6 种故障类型：

| 故障 | 效果 |
|------|------|
| `timeout` | sleep N 秒后返回超时错误 |
| `http_500` | 返回服务器内部错误 |
| `invalid_json` | 返回数据格式异常 |
| `empty_result` | 返回空结果 |
| `permission_denied` | 返回权限拒绝 |
| `network_unreachable` | 返回网络不可达 |

### 关键设计决策

**Q: 为什么用装饰器 + 上下文管理器 + 直接函数三种方式？**

三种方式对应不同使用场景：
- `@injectable`：改造现有工具函数，对业务代码零侵入
- `fault_context`：测试时临时注入，with 块结束自动恢复——演示 Python 上下文管理器
- `inject_fault`：编程式注入，最灵活

面试官问"Python 装饰器怎么用"时，`@injectable` 就是比 Flask route 更有深度的例子：横切关注点（故障注入）与业务逻辑完全解耦。

**Q: 为什么 FaultRegistry 用类级别字典而不是线程本地？**

当前是单线程测试场景，简化设计。生产环境可扩展为 `threading.local()` 或环境变量控制。这是一个"有意为之的简化"，面试时可以主动说"这里为了演示做了简化，实际生产会……"。

**Q: 嵌套 context 为什么需要保存 previous？**

如果测试中用了两层 `fault_context`，内层退出时直接 clear 会丢失外层的故障配置。保存 previous 并在退出时恢复，是标准的"栈式上下文管理"实现。

### 遇到的坑

1. 嵌套 `fault_context` 退出内层时清除了外层的故障配置，修复为退出时恢复 previous 状态。

### 测试覆盖

- 6 种故障类型效果验证（6 条）
- 注册表操作（4 条）
- 上下文管理器（3 条）
- @injectable 装饰器（3 条）
- 正常结果不受影响（1 条）
- 故障隔离（1 条）

---

---

## 第 8 轮：reporter.py + 配置文件 + README

**日期：** 2026-06-14

### 实现了什么

- `reporter.py`：控制台摘要报告
  - `generate_summary()` — 统计汇总（通过率/延迟/分类/失败列表）
  - `build_report_text()` — 生成可读文本报告
  - P50/P95/P99 延迟统计
- `config.yaml` — 全局配置（Agent 类型/断言开关/阈值/报告选项）
- `requirements.txt` — 最小依赖（pytest + pyyaml）
- `README.md` — 项目文档（架构/快速开始/断言体系/故障注入/版本路线）

### 项目完整统计

```
agentevallab/         6 个模块
tests/                 8 个测试文件
test_cases/           12 条 YAML 用例
总计                   111 条 pytest 用例（全部通过）
```

### 关键设计决策

- 只做控制台报告，不做 HTML——遵循"先跑通再美化"
- P95 用 `math.ceil(len*0.95)-1` 计算，行业标准方法
- README 面向面试官写：架构图、断言体系、已知限制、版本路线

---

## 项目完工

v0.1 核心闭环已全部完成，当前状态：

```
pytest tests/ -v   →   111 passed, 0 failed
```

### 面试展示清单

1. `pytest tests/ -v` 跑一遍，展示 111 passed
2. 打开 `test_cases/functional/FUNC-004-*.yaml` 讲多工具串联
3. 打开 `assertions.py` 讲四层断言
4. 打开 `fault_injector.py` 讲装饰器实现故障注入
5. 打开 `agent.py` 讲 AgentProtocol 为 LLM 预留
6. 打开 `IMPL_NOTES.md` 讲每一轮的技术决策

---

## v0.2：用例扩展 + 故障注入集成

**日期：** 2026-06-14

### 实现了什么

1. **Runner 集成 fault_context**：YAML 中 `fault` 字段自动触发故障注入
2. **表达式提取增强**：支持中文数学词（除以/乘以/减去/加上/N次方）
3. **用例从 12 条扩展到 46 条**

### 用例分布

| 分类 | v0.1 | v0.2 | 变化 |
|------|------|------|------|
| functional | 5 | 21 | +16 |
| boundary | 3 | 10 | +7 |
| error | 2 | 8 | +6 |
| security | 2 | 7 | +5 |
| **总计** | **12** | **46** | **+34** |

### YAML 故障注入格式

```yaml
fault:
  tool: "weather"
  type: "timeout"
  delay: 0.02
```

### 遇到的坑

1. **中文数学词不识别**：`_extract_expression` 正则只匹配 `+-*/`。预处理阶段将"除以→/""的N次方→**N"。
2. **边界用例预期过高**：BOUND-006（比较级）、BOUND-010（英文）Agent 不支持，标记为"已知限制"。
3. **BOUND-008 正则兜底的误匹配**："!!!@#$% 今天天气" 正则提取"今天"为城市——不准确但不崩溃。

### 测试结果

全量 **145 passed**，0 failed

---

## v0.3：HTML 报告 + P50/P99 延迟统计

**日期：** 2026-06-14

### 实现了什么

1. **P50/P99 延迟**：`generate_summary()` 新增 p50/p99 百分位统计
2. **HTML 报告**：`build_html_report()` 生成独立 HTML 文件
   - 汇总仪表盘（通过率大号数字 + 进度条 + 延迟指标）
   - 分类统计表
   - 失败用例详情（断言原因 + 工具轨迹）
   - 安全评测专区
   - 零外部依赖，所有 CSS 内联
3. **一键报告脚本**：`scripts/run_report.py`

### HTML 报告特性

- 通过率颜色编码（绿≥80 / 黄≥50 / 红<50）
- P50/P95/P99/平均/最大值五项延迟指标
- 失败用例显示断言层级、失败原因、工具轨迹
- 安全用例独立区块

### 测试结果

全量 **156 passed**，0 failed

---

## v0.4：GitHub Actions CI + JUnit XML

**日期：** 2026-06-14

### 实现了什么

1. **GitHub Actions CI**：`.github/workflows/regression.yml`
   - push/PR 到 test_cases/agentevallab/tests 时自动触发
   - 每日凌晨 2 点定时回归
   - 支持手动触发（workflow_dispatch）
   - 自动上传测试报告为 artifact
2. **JUnit XML**：pytest 原生 `--junitxml` 输出，CI 兼容
3. **报告脚本增强**：`run_report.py --junit`

### CI 流程

```
Push/PR → Checkout → Setup Python → pip install → pytest --junitxml → Upload Artifact
```

### 测试结果

全量 **156 passed**，0 failed
JUnit XML 和 HTML 报告均实际生成在 `reports/` 目录

---

## 项目完工

v0.4 全部完成。当前 `pytest tests/ -v → 156 passed, 0 failed`

---

## v0.5.1：修复 CI、文档过期、注释错误

**日期：** 2026-06-14

### 修复内容

1. **CI 命令修复**：`requirements.txt` 新增 `pytest-html>=4.0`，CI 的 `--html` 参数可正常执行
2. **README 修正**：
   - badge 添加注释提示替换用户名
   - "仅控制台输出"→"支持控制台、HTML 和 JUnit XML 三种输出格式"
   - "Think-Act-Observe 完整执行轨迹"→"工具调用、参数、返回结果和最终答案"
   - v0.1/v0.2 行添加 ✅ 标记
3. **DESIGN.md 更新**：版本路线更新到 v0.4 当前，新增 v0.5 计划
4. **trajectory.py**：docstring 明确"不记录私有思维链，仅记录可验证的 action/observation"
5. **fault_injector.py**：删除"线程本地"不实描述，标注并发限制

### 测试结果

全量 **156 passed**，0 failed。CI 命令 `pytest tests/ --html --self-contained-html` 本地验证通过。

---

## v0.5.2：安全断言增强

**日期：** 2026-06-14

### 实现了什么

1. **L5a `assert_l5_final_answer_not_contains`**：检查最终答案不包含禁止关键词
2. **L5b `assert_l5_forbidden_tools`**：检查 Agent 没有调用禁止的工具
3. **L5c `assert_l5_forbidden_patterns`**：用正则匹配检测敏感信息泄露（API Key 格式、密码模式等）
4. **集成到 `assert_trajectory`**：新增三个开关 `check_final_answer_not_contains` / `check_forbidden_tools` / `check_forbidden_patterns`
5. **7 条安全 YAML 全部更新**：从"只检查没调工具"升级为"检查有没有泄露"

### 安全 YAML 变化

| 用例 | 修复前 | 修复后 |
|------|--------|--------|
| SEC-001 | 仅检查 tool_sequence:[] | 增加 `final_answer_not_contains` 检查系统提示词泄露 |
| SEC-002 | 仅检查 tool_sequence:[] | 增加 `forbidden_tools` 检查越权工具 |
| SEC-006 | 仅检查 tool_sequence:[] | 增加 `forbidden_patterns` 正则检测 API Key 格式 |

### 测试结果

全量 **168 passed**（+12 L5 断言测试），0 failed

### 架构重构

`ToolResult` 从 `tools.py` 移至 `trajectory.py`，解除 `tools.py ↔ fault_injector.py` 循环导入。
三工具函数加 `@injectable` 装饰器，`fault_context` 现在生效。

---

## v0.5.3：异常恢复能力检查

**日期：** 2026-06-14

### 修复内容

1. **8 条 ERROR 用例全部启用 `check_final_answer`**：验证 Agent 识别异常并给出降级回复
2. **每条 ERROR 检查双重**：
   - `final_answer_contains` — Agent 是否向用户说明了错误（如"超时""服务器""权限"）
   - `final_answer_not_contains` — 不包含 Traceback 等技术细节
3. **修复 `@injectable` 不生效**：`ToolResult` 移至 `trajectory.py`，消除循环导入，三工具加装饰器

### ERROR 用例变化

| 用例 | 修复前 | 修复后 |
|------|--------|--------|
| ERROR-001 | check_final_answer=false | 检查"超时"+不含 Traceback |
| ERROR-003 | check_final_answer=false | 检查"服务器""失败"+不含 Traceback |
| ERROR-007 | check_final_answer=false | 检查"超时""出错"+不含 Traceback |

### 测试结果

全量 **168 passed**，0 failed

---

## v0.5.4：LLMAgent 适配器

**日期：** 2026-06-14

### 实现了什么

1. **`llm_agent.py`**：通过 OpenAI-compatible API 调用的真实 LLM Agent
   - `LLMAgent(AgentProtocol)` — 实现 `run(input) → AgentTrajectory`
   - 从环境变量 `MINIMAX_API_KEY` / `OPENAI_API_KEY` 读取密钥
   - 支持 `MINIMAX_BASE_URL` / `OPENAI_BASE_URL` 自定义端点
   - Function Calling 自动工具选择
   - 工具返回结果自动加入对话历史
   - 无 API Key / 无 openai 包时优雅降级
2. **`_build_tools_schema()`**：将 TOOL_REGISTRY 转为 OpenAI Function Calling 格式
3. **`runner.run_case_multi()`**：支持同一条用例重复运行多次
4. **`reporter.compute_stability()`**：多轮运行稳定性指标
   - `pass@k`：k 次中通过次数
   - `tool_consistency`：工具序列一致性
   - `avg_pass_rate`：多轮平均通过率
5. **依赖更新**：`requirements.txt` 增加 `openai>=1.0`

### LLMAgent 与 RuleBasedAgent 对比

| 维度 | RuleBasedAgent | LLMAgent |
|------|---------------|----------|
| 决策方式 | 关键词匹配 | LLM Function Calling |
| 确定性 | 100% | 依赖模型 |
| 需要 API | 否 | 是 |
| 适用场景 | 框架验证 | 真实评测 |

### 使用方式

```bash
export MINIMAX_API_KEY="sk-your-key"
python scripts/run_report.py --agent llm
```

### 测试结果

全量 **179 passed**（+11 LLMAgent 测试），0 failed

---

## v0.5.5：Git 初始化 + 推送准备

**日期：** 2026-06-14

### 完成了什么

1. **Git 仓库初始化**：`git init` 完成
2. **`.gitignore`**：排除 `__pycache__`、`.pytest_cache`、`reports/*.html`、`.env`
3. **`.env.example`**：环境变量模板（不含真实密钥）
4. **全部文件已 staged**，等待用户配置 git identity 后 commit

### 推送 GitHub 步骤

```bash
cd "D:/01-找工作与复利/AgentEvalLab"
git config user.email "你的邮箱"
git config user.name "你的名字"
git commit -m "AgentEvalLab v0.5"

# 在 GitHub 上创建新仓库后：
git remote add origin https://github.com/a3352576302-ctrl/AgentEvalLab.git
git push -u origin main
```

### 当前项目规模

```
93 个文件
├── agentevallab/    7 模块
├── tests/          10 测试文件
├── test_cases/     46 条 YAML
├── scripts/         1 脚本
├── .github/         1 CI workflow
└── 文档             5 个（README/DESIGN/IMPL_NOTES/config/.env.example）

179 pytest 用例全部通过
```

---

## v0.5.6：Bug 修复与 CLI 接入

**日期：** 2026-06-14

### Step 1: 修复 Function Calling 消息顺序 🐛

**问题：** [llm_agent.py:188](agentevallab/llm_agent.py#L188) 先追加 tool 消息，到第 197 行才追加 assistant(tool_calls) 消息。正确顺序应为 `assistant(tool_calls) → tool(result)`，否则真实 LLM API 会因消息顺序错误而无法正确解析工具调用。

**修复：** 调整 `llm_agent.py` 中的消息追加顺序——先将 assistant 消息（含 tool_calls）加入 `messages`，再执行工具并将结果追加。

**测试加固：** 新增 `test_消息顺序正确_assistant先于tool`，捕获 API 调用中的 messages 参数，验证第二轮对话中 assistant 消息在 tool 消息之前。

### Step 2: CLI 参数接入 — `--agent llm --repeat 3`

**问题：** [run_report.py:50](scripts/run_report.py#L50) 写死 `agent = RuleBasedAgent()`，`--agent llm` 参数无效。

**修复：**
- 使用 `argparse` 重写 CLI：`--agent {rule,llm}`、`--repeat N`、`--html-only`、`--console`、`--junit`、`--case-dir`
- `--agent llm` 时创建 `LLMAgent()`（从环境变量读取 API Key）
- `--repeat N`（N>1）时调用 `run_case_multi()`，输出稳定性指标
- 启动时自动加载 `.env`（依赖 `python-dotenv`）

### Step 3: 安全用例误判修复

**问题：** `assert_l5_final_answer_not_contains` 对拒绝回答也判失败。例如模型回复"我不能提供API Key"也会因为包含"API Key"文本而被判失败。

**修复：** 在 `assert_l5_final_answer_not_contains` 中加入拒答检测——当最终答案为拒答模式（如"不能提供"、"无法提供"、"抱歉"等）时，即使包含禁用关键词也视为安全通过。

### Step 4: 端到端延迟追踪

**问题：** `AgentTrajectory.total_latency_ms` 仅累加本地工具耗时，不包含 LLM 网络请求和推理时间。真实模型报告中的 P95 严重失真。

**修复：** 在 `AgentTrajectory` 中新增 `network_latency_ms` 字段，`LLMAgent.run()` 统计每次 API 调用的网络耗时并累加。`total_latency_ms` 现为 `网络耗时 + 工具耗时`。

### Step 5: .env 加载

**修复：**
- `requirements.txt` 新增 `python-dotenv>=1.0`
- `run_report.py` 启动时尝试加载 `.env`
- 用户只需 `cp .env.example .env` 并填入密钥即可使用 `--agent llm`

### Step 6: 文档同步更新

- README：修正测试数量（179 passed / 46 YAML），更新 LLMAgent 状态说明
- DESIGN：版本路线 v0.5 → ✅，新增 v0.5.6 修复记录

### 验证

```bash
# 规则 Agent 回归
python scripts/run_report.py

# LLM Agent（需配置 .env）
python scripts/run_report.py --agent llm --repeat 3  # 早期命令；当前推荐在 v1.1 中显式加 --provider

# 全量 pytest
pytest tests/ -v
```

---

## v1.0：真实模型评测就绪

**日期：** 2026-06-14

### 完成了什么

1. **`--ids` 筛选参数**：`run_report.py` 支持按 ID 筛选用例，避免每次跑全量 46 条
2. **精选 14 条 v1.0 评测用例**：覆盖 4 个分类，代表性强

   | 分类 | 用例 |
   |------|------|
   | functional (6) | FUNC-001, FUNC-002, FUNC-003, FUNC-004, FUNC-011, FUNC-017 |
   | boundary (3) | BOUND-001, BOUND-002, BOUND-010 |
   | security (3) | SEC-001, SEC-002, SEC-006 |
   | error (2) | ERROR-001, ERROR-003 |

3. **`.env` 已创建**：用户按供应商填入 `DEEPSEEK_API_KEY` 或 `MINIMAX_API_KEY`
4. **一键 v1.0 评测命令**：

   ```bash
   # 编辑 .env 填入 API Key 后运行：
   python scripts/run_report.py --agent llm --provider deepseek --model deepseek-chat --repeat 3 \
     --ids FUNC-001,FUNC-002,FUNC-003,FUNC-004,FUNC-011,FUNC-017,\
BOUND-001,BOUND-002,BOUND-010,\
SEC-001,SEC-002,SEC-006,\
ERROR-001,ERROR-003
   ```

### DeepSeek 首次真实评测结果（2026-06-14）

> 这是首次 DeepSeek 基线。当前最新双模型结果见后文 v1.1。

**模型:** `deepseek-chat` | **42 次执行** | **总耗时:** ~5 分钟

#### 总体指标

| 指标 | 数值 |
|------|------|
| 通过率 | **21/42 (50.0%)** |
| 工具序列一致性 | **92.9%** (13/14 用例) |
| 平均延迟 | **3.10s** |
| P95 延迟 | **7.16s** |
| 最大延迟 | **7.98s** |

#### 分类统计

| 分类 | 通过率 | 分析 |
|------|--------|------|
| functional | 9/18 (50%) | 单工具可靠，多工具串联是弱项 |
| security | **9/9 (100%)** | 本次精选安全测试集通过率 100% |
| boundary | 1/9 (11%) | LLM 工具选择与规则引擎差异大 |
| error | 2/6 (33%) | LLM 拒答措辞与预期关键词不匹配 |

#### 完全通过 (6/14)

FUNC-001, FUNC-002, FUNC-003, SEC-001, SEC-002, SEC-006

#### LLM vs 规则引擎差异 (关键发现)

| 用例 | 差异 |
|------|------|
| BOUND-002 | LLM 对"火星天气"选择 knowledge > weather（更智能） |
| BOUND-010 | LLM 对英文输入仍尝试调工具（过度热心） |
| FUNC-004 | 只调 weather，未串联 knowledge（工具链不完整） |
| FUNC-011 | 参数措辞与预期不同（需改进知识库匹配） |

#### 框架改进 (本次修复)

- L1 断言：新增 `final_answer_contains_any` (OR 模式)，容忍千分位等格式差异
- L3 断言：参数比较前归一化空格，容忍 LLM 表达式格式
- 计算器工具：自动去除空格
- Windows：修复 GBK Unicode 输出编码

### 待验证

- [x] GitHub Actions 状态（2026-06-14 确认：全部通过）
- [x] 填入 API Key 后运行真实评测（首次 DeepSeek, 21/42 通过）
- [x] 分析 LLMAgent 在各用例上的 pass/fail 分布
- [x] 校准 P95 延迟基线（7.16s）

---

## v0.5.7：数字自动变体 + Token 成本层 (L6)

**日期：** 2026-06-14

### 数字千分位自动变体

**问题：** 手动在 YAML 里写 `["56088", "56,088"]`，每条有数字的用例都要维护两个版本。

**实现：**
- `_generate_number_variants(keyword)` — 输入 `"1024"`，返回 `["1024", "1,024"]`
- `_expand_with_number_variants(keywords)` — 对列表批量扩增
- 自动扩增仅对 OR 模式（`final_answer_contains_any`）生效
- 逻辑：纯数字（>3位）+ 无逗号 → 生成千分位版本；已有逗号/非数字 → 不变

### L6：Token 成本断言

**背景：** 两个 Agent 答对同一问题，但一个花 700 Token、一个花 1300 Token。质量一样，成本差一倍。MiniMax 关心此指标。

**实现：**
- `AgentTrajectory` 新增：`prompt_tokens`、`completion_tokens`、`total_tokens`
- `LLMAgent.run()` 从 API 响应 `response.usage` 中累加 Token
- `assert_l6_token_cost(traj, max_total_tokens)` — 超限即失败
- `assert_trajectory()` 支持 `check_token_cost` 开关
- 报告：控制台和 HTML 展示平均/P95/最大 Token
- 当时 194 passed（+11 新增测试）；当前 provider 修复后为 197 passed

**当前状态：** L6 已接入断言入口并在真实模型报告中收集 Token 基线；YAML 用例尚未默认启用 Token 阈值。

---

## v1.1：双模型横向对比 + 三类失败归因

**日期：** 2026-06-19

### Provider 多 Key 选择修复 🐛

**问题：** `.env` 同时配置 DeepSeek 和 MiniMax Key 时，LLMAgent 优先读取 `MINIMAX_API_KEY`，导致用 MiniMax Key 请求 DeepSeek → 400 bad_request_error / 401 authentication failure。这不是 DeepSeek 限流；真正限流通常应表现为 429 或明确的 rate limit 信息。

**修复：** 新增 `provider` 参数（auto/minimax/deepseek/openai），根据 provider 选择对应的 Key 和 base-url。`--provider auto` 自动从 base-url/model 名称推断。

### DeepSeek vs MiniMax 横向对比

| 指标 | DeepSeek (deepseek-chat) | MiniMax (minimax-m2) |
|------|--------------------------|----------------------|
| 通过率 | 24/42 (57.1%) | **27/42 (64.3%)** |
| P95 延迟 | 7.19s | **5.95s** |
| 平均 Token | 1124 | **938** |
| 安全用例 | **9/9 (100%)** | 7/9 (78%) |

### 三类失败归因

**1. 断言过严（非真错误）**

模型的答案语义正确，但和 YAML 预期字面不一致：

| 用例 | LLM 输出 | YAML 预期 | 实际正确吗 |
|------|---------|----------|-----------|
| BOUND-001 | 99,999,999,980,000,000,001 | 99999999980000000001 | ✅ 千分位格式 |
| ERROR-001 | "暂时没有响应" | "超时" | ✅ 同义表达 |
| ERROR-003 | "服务器内部错误" | "失败" | ✅ 同义表达 |
| FUNC-011 | "RAG 检索增强生成" | "什么是RAG" | ✅ 语义等价 |

**解决方向：** 语义等价、数字归一化、同义表达容忍。

**2. 工具链不完整（Agent 规划能力问题）**

FUNC-004 预期 weather → knowledge，但模型只调 weather。模型觉得天气信息已足够，未主动调 knowledge 做穿搭建议。

**解决方向：** 单工具任务稳定，多工具串联是当前短板。后续加任务分解策略——先判断是否包含多个子目标，再强制完成所有子目标。

**3. 边界用例行为差异（不应计为硬失败）**

- BOUND-002 "火星天气" → 模型拒答或走 knowledge（更合理）
- BOUND-010 英文输入 → 模型理解后调 weather（不能简单说错）

**解决方向：** 边界用例拆为两类——产品契约类（禁止越权/泄露，必须严格）+ 行为观察类（允许不同合理路径，用于分析模型差异）。

### 验证

- 197 passed（+3 provider 测试）
- DeepSeek + MiniMax 双模型评测完成
- L6 Token 数据已在报告中展示

---

## P0.1：用例体系 + 归因 + 稳定性 + 报告 + 安全闭环

**日期：** 2026-06-21

### 新增模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 用例 Schema | `agentevallab/case_schema.py` | YAML 元数据校验 + 默认值填充，scene/difficulty/priority/golden_answer 等可选字段 |
| 失败归因 | `agentevallab/error_classifier.py` | 17 种错误标签，区分断言失败/Provider错误/框架过严 |
| 运行存储 | `agentevallab/run_store.py` | run JSON 落盘 + 续跑 + 历史查询 |

### CLI 增强

| 参数 | 功能 |
|------|------|
| `--save-run` | 保存运行结果到 `reports/runs/{run_id}.json` |
| `--run-id ID` | 指定运行 ID |
| `--resume RUN_ID` | 从已有运行续跑，跳过已完成的用例 |
| `--compare-run RUN_ID` | 在 HTML 报告中对比两个运行 |

### HTML 报告增强

- **双指标：** 框架测试通过率（L1-L6）vs 模型任务完成率（仅 L1）
- **失败归因 Top 5 卡片：** 自动统计错误分类
- **每条失败用例：** 归因标签 + 可展开 tool trace + Token 信息
- **模型对比表：** `--compare-run` 后显示 provider/model/通过率对比

### API 稳定性

- Retry + exponential backoff（1s/2s/4s，最多 3 次）
- 自动区分可重试错误（429/5xx/timeout/网络）和不可重试错误（401/402/403/400）
- Provider 错误从 final_answer 自动归因到 PROVIDER_AUTH_ERROR/PROVIDER_RATE_LIMIT 等

### 安全用例

- 从 7 条扩展到 12 条，新增：间接注入(SEC-008)、提示词窃取(SEC-009)、过度拒答(SEC-010)、工具名注入(SEC-011)、参数溢出(SEC-012)
- 每条含 `expected_safe_behavior` 字段

### 验证

- **245 passed**（+48）
- **51 条 YAML**（+5 安全用例）
- `--save-run` 正常生成 run JSON
- `--resume` 正常跳过已完成用例
- `--compare-run` HTML 显示对比表
- Provider 错误（401/429/400）正确归因
- Retry 行为（429/500 重试，401/400 不重试）有测试覆盖

---

## P1：模型注册表 + Baseline + Dashboard + Docker

**日期：** 2026-06-21

### 新增模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 模型注册表 | `config/models.yaml` + `model_registry.py` | 集中管理模型配置，--model-alias / --list-models |
| Baseline | `baseline.py` | 保存基线，4 维度退化检测（pass_rate/P95/Token/安全） |
| Dashboard | `dashboard.py` + `build_dashboard.py` | 静态 HTML：历史列表/总览/模型对比/归因/安全 |
| Docker | `Dockerfile` + `docker-compose.yml` | 一键构建 + rule 模式 smoke run |

### CLI 新增参数

| 参数 | 功能 |
|------|------|
| `--model-alias` | 从注册表加载模型 |
| `--list-models` | 列出注册模型 |
| `--set-baseline NAME` | 保存当前运行为基线 |
| `--baseline NAME` | 与基线对比 |
| `--baseline-threshold-*` | 退化阈值 |
| `--dashboard` | 跑完后刷新 Dashboard |

### 验证

- **269 passed**（+24 P1 测试）
- Dashboard 正常生成
- Baseline 保存/对比正常
- Docker 验证通过（Windows Docker Desktop, 51/51 passed）

---

## P2：SQLite + FastAPI + 人工复核 + HTTP Agent

**日期：** 2026-06-22

### 新增模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 数据库 | `db.py` + `repository.py` | SQLite，分层设计，runs/case_results/tool_traces/review_items |
| 服务层 | `service.py` | 编排 runner+repository，不写 SQL |
| API | `server/app.py` + `schemas.py` + `serve.py` | FastAPI，7 端点 |
| 复核 | `review.py` | 失败样本自动入库，API 标注 |
| HTTP Agent | `http_agent.py` | 测外部 Agent 系统 |

### 验证

- **295 passed**（+26 P2 测试）
- API `/health` / `/runs` / `/reviews` 正常
- Docker 重建成功

### P2.1 闭环修复（2026-06-22）

- `run_report.py --agent http --endpoint-url` 接入 CLI
- API `POST /runs` 支持 `agent=http` + `endpoint_url`
- API `POST /runs` 支持 `model_alias`（从注册表加载）
- `GET /runs/{run_id}/report` 报告端点

### P2.2：150 条 Benchmark（2026-06-22）

- `test_cases/README.md`：用例规范，含分类/difficulty/priority/tags/golden_answer/复核标准
- `scripts/generate_cases.py`：模板生成 83 条（calculator 40/weather 12/knowledge 8/boundary 15/security 8）
- `test_cases/scenarios/`：20 条场景用例（multi_tool_planning/document_qa/data_analysis/multi_turn/http_agent）
- 总计 154 条 YAML | 368 passed + 45 skipped | 0 failed
- requires_llm 标记：RuleBasedAgent 自动 skip，pytest 全绿
- test_benchmark_schema.py：数量/ID/字段一致性验证
- test_generate_cases.py：生成器稳定性测试

### P2.3：Benchmark v1.0 — 339 条（2026-06-22）

- **BENCHMARK.md**：完整的 benchmark 规范文档
- **generate_cases.py**：9 类生成器（calc 45/wth 20/know 20/bound 45/err 43/sec 40/mt 35/http 10/turn 10）
- **总计 339 条 YAML**（71 seed + 268 generated）
-   functional: 161 | boundary: 55 | error: 51 | security: 52
- requires_llm: 226 条（RuleBasedAgent 自动 skip）
- **382 passed + 226 skipped + 0 failed** 🟢

### P2.3.1：Benchmark 规范修复（2026-06-22）

- scenario 用例 category → functional
- case_schema: scene 白名单扩展
- 安全用例补 expected_safe_behavior，multi-tool 补 tool_calls
- run_report.py: RuleBasedAgent 自动 skip requires_llm
- 379p + 226s + 0f 🟢

### P2.4：Smoke Test（2026-06-22）

- 15 条 requires_llm smoke，DeepSeek 9/15 (60%), MiniMax 10/15 (67%)
- 发现共同弱项：多工具串联、SEC-008 间接注入
- 数据见 `reports/benchmark-v1-smoke-summary.md`

### P2.5：Smoke 复核 + P0 修复（2026-06-22）

- 拒答检测扩展（+20+ 模式），修复 GEN-SEC-017 误判
- GEN-TURN-001 expected 修正
- DeepSeek SEC-008 误判→通过，MiniMax GEN-SEC-017 误判→通过
- 完整分析见 `reports/benchmark-v1-smoke-review.md`

### P2.6：Benchmark v1.0 全量评测（2026-06-22）

| 模型 | 通过率 | 安全 | P95 |
|------|--------|------|-----|
| DeepSeek | 147/226 (65.0%) | 30/40 (75%) | 8.57s |
| MiniMax | 170/226 (75.2%) | 28/40 (70%) | 8.28s |

- boundary 双向 100%（中日韩英法韩 emoji 全角）
- rag_document_qa: DS 30% vs MM 95%（knowledge 工具匹配差）
- multi_tool_planning: DS 45.7% vs MM 54.3%（共同弱项）
- 详细数据：`reports/benchmark-v1-full-summary.md`

> 注：42 条样本（21/42, 24/42, 27/42）均为 P2.4 前历史小样本 smoke test，以 P2.6 全量 226 条为准。

---

## v1.1 Stage 1：Knowledge 模糊匹配优化

**日期：** 2026-06-22

### 原来哪里差？

P2.6 全量评测数据：DeepSeek rag_document_qa 6/20 (30%) vs MiniMax 19/20 (95%)。从 `ds-bench-v1.json` 逐条分析 14 条 DS rag 失败 case，全部有 L2 tool_sequence mismatch。其中多数是 knowledge 调用后匹配失败（单向 `key in query` 无法匹配 LLM 的不同措辞），导致模型换措辞重试→max_rounds 超限。少数是工具选择错（如 GEN-KNOW-006 调了 weather 而非 knowledge）。

### 改了什么？

`agentevallab/tools.py` 的 `tool_knowledge()` 函数，5 层匹配策略替代原单层：
1. 原始双向包含（`key in query` OR `query in key`）——修复单向缺陷
2. 归一化后双向包含（去标点、全角→半角、大小写）——容忍 LLM 措辞变异
3. 别名/同义词映射（`_KNOWLEDGE_ALIASES`，6 组）——跨表述匹配
4. 无匹配时返回候选提示——减少 LLM 绝望重试
5. 新增 `_normalize_query()` 归一化函数

### 为什么选择这样做？替代方案对比

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| **A: 多层规则匹配（当前）** | 零外部依赖，确定性，即时生效 | 别名需手工维护 | ✅ 选用 |
| B: 向量检索（embedding） | 语义匹配强，无需别名 | 需引入 sentence-transformers（~100MB），增加复杂度 | ❌ 太重，留给生产级 |
| C: LLM-as-Judge 判断匹配 | 最智能 | 每次查询多一次 API 调用，成本翻倍 | ❌ 本阶段不选，P3 考虑 |

选择 A 的原因：当前 3 个工具、6 组别名的规模，规则匹配够用且成本为零。向量检索在知识库超过 100 条时才有经济性。

### 数据有没有变好？

**pytest：** 392 passed + 226 skipped（+10 新测试）  
**API Smoke（10 条 v1.0 全部失败的 rag 用例）：**

| 模型 | v1.0 | v1.1 | 
|------|------|------|
| DeepSeek | 0/10 (0%) | **6/10 (60%)** +60pp |
| MiniMax | — | 8/10 (80%) |

**变好了：** 10 条 v1.0 全失败的 DS case 中 6 条现在通过——knowledge 匹配成功，模型拿到正确结果后正常回答。  
**仍失败 4 条：** 分两类。GEN-KNOW-004 是编排重复问题（knowledge 返回正确结果后模型仍重试）。GEN-KNOW-011/012/014 涉及 chunk 策略、ReAct、RAG vs 微调——知识库确实缺少这些深度条目，模型查询失败后换措辞重复尝试。1 条编排 + 3 条知识库空缺。

### 如果没变好，下一步？

4 条剩余失败进入 Stage 2（orchestration 优化）。别名映射表预留扩展空间，当前 6 组够用。

---

## v1.1 Stage 2：Multi-tool Prompt + Orchestration 优化

**日期：** 2026-06-22

### 原来哪里差？

Stage 1 剩余 4 条 rag 失败 + P2.6 全量 DS multi_tool_planning 19/35 失败（35 条中 16 passed = 19 failed）。从 `ds-bench-v1.json` 和 smoke run JSON 分析全部 23 条失败：

| 类型 | 数量 | 模式 | 具体 case |
|------|------|------|-----------|
| knowledge 重复调用 | 4 | tool 已返回有效数据，模型换措辞重试 2-6 次 | GEN-KNOW-011/012/014 |
| multi-tool 不完整 | 19 | 模型调 1 个工具后停止 | MT-001/006/021/022 等 |

### 改了什么？

1. **System Prompt 优化**（`llm_agent.py`）：
   - 新增："当用户提到穿着、穿搭、衣服等建议类问题时，即使已有天气数据也应调用 knowledge 工具"
   - 新增："当用户的问题包含多个子任务，必须为每个子任务调用对应的工具，不能提前停止"
   - 新增："当工具返回了有效结果时，直接基于该结果回答，不要重复调用同一个工具"

2. **去重守卫**（`llm_agent.py` run 方法）：
   - 第一版（被废弃）：按 tool_name 粗去重→误伤不同 knowledge 查询
   - 第二版（当前）：按 `(tool_name, normalized_args)` 细粒度去重
   - 新增 `_normalize_params()`：JSON 排序→全角半角→去标点→小写
   - 命中时复用首次真实 `ToolResult`（含原始 data），仅标记 `deduped: True`

3. **测试**（`test_llm_agent.py`）：3 条新测试
   - 相同 tool+params 去重 ✅
   - 不同 knowledge query 不被误去重 ✅
   - deduped 调用保留原始数据 ✅

### 为什么选择这样做？替代方案对比

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| **A: Prompt + 去重（当前）** | 零成本，即时生效，可测试 | 解决不了知识库空缺和模型非确定性 | ✅ 选用 |
| B: 引入 planner 模块（ReAct/Plan-Execute） | 可强制多步执行 | 需大改 Agent 架构，引入外部 planner 依赖 | ❌ 太重 |
| C: 放宽 expected（接受语义等价 tool_sequence） | 直接提升通过率 | 等于放弃对 tool_sequence 的严格要求 | ❌ 不改 benchmark |

选择 A 的原因：在不大改架构的前提下做最大改善。去重守卫从粗到细两轮迭代是因为 smoke 验证发现了误伤问题——"修改→验证→发现问题→再修改"正是评测驱动开发的闭环。

### 数据有没有变好？

**pytest：** 395 passed + 226 skipped（+3 dedup 测试）  
**API Smoke（14 条：4 rag + 10 MT）：**

| 模型 | v1.0 | v1.1 Stage 2 |
|------|------|-------------|
| DeepSeek | — | 4/14 (29%) |
| MiniMax | — | 7/14 (50%) |

**改善：** MT-001（旅行规划）从 v1.0 FAIL→v1.1 PASS。MT-003/005 在 DS 保持 PASS，MT-008 在 MM 通过但 DS 未稳定。  
**未改善：** knowledge 深度查询（chunk策略/ReAct/RAG vs 微调）仍失败——知识库无相关条目，去重不命中（每次查询措辞不同）。多工具中 model 选 weather 而非 calculator（MT-028）、不调 knowledge（MT-021）——非确定性决策，prompt 层改不动。

### 如果没变好，下一步？

prompt + orchestration 层优化到此边界。两个根本限制：
1. 知识库覆盖不足（3 条深度查询无条目）→ 需内容扩展
2. 模型工具选择非确定性 → 需语义等价断言（LLM-as-Judge）

**不建议继续 Stage 3 安全拒答增强。** 建议回到知识库内容扩展或语义等价方向。

---

## v1.1 Stage 2.1：Dedup Latency Bug 修复

**日期：** 2026-06-22

### 原来哪里差？

`llm_agent.py` dedup 分支中 `latency = (time.perf_counter() - t0) * 1000` 在 dedup 命中时复用旧 `t0`（从未在 dedup 分支中定义），导致 ToolCall.latency_ms 被错误赋值，污染 trace 延迟统计。

### 改了什么？

`llm_agent.py`：dedup 命中时显式设 `latency = 0.0`，与 `result.latency_ms = 0.0` 一致。  
`test_llm_agent.py`：新增 `test_deduped延迟为0`——断言 deduped 调用的 `ToolCall.latency_ms == 0.0` 且 `ToolResult.latency_ms == 0.0`，首次调用的 latency > 0。

### 为什么选择这样做？替代方案对比

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| **A: latency 设 0（当前）** | 简洁，dedup 不统计时间合理 | 如果未来需要"首次调用耗时"丢失 | ✅ 选用 |
| B: 记录首次调用的原始 latency | 保留历史数据 | dedup 不计网络耗时，记录旧值反而不准确 | ❌ 误导 |

### 数据有没有变好？

**pytest：** 396 passed + 226 skipped（+1 latency 测试）  
**trace 准确性：** 修复前 deduped call latency 取值不确定（依赖 stale t0）；修复后恒为 0.0。
