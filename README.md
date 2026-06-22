# AgentEvalLab

**AI Agent 自动化测试与评测平台**

[![Regression Test](https://github.com/a3352576302-ctrl/AgentEvalLab/actions/workflows/regression.yml/badge.svg)](https://github.com/a3352576302-ctrl/AgentEvalLab/actions/workflows/regression.yml)

基于 pytest + YAML 用例驱动的 AI Agent 评测框架。通过记录 Agent 的工具调用、参数、返回结果和最终答案，从**最终结果、工具选择、参数传递、调用顺序、异常恢复、安全合规**六个维度评估 Agent 行为。

---

## 项目定位

| 传统软件测试 | AgentEvalLab |
|-------------|-------------|
| 只看输入/输出 | 检查完整工具调用轨迹 |
| 单一 pass/fail | L1-L6 多层独立断言（L6 为可选 Token 成本） |
| 测试数据写死在代码 | YAML 驱动，测试与逻辑解耦 |
| 测确定性逻辑 | 同时测结果正确性 + 过程合规性 |

---

## 快速开始

### 环境要求

- Python 3.10+
- pytest + PyYAML

### 安装

```bash
pip install -r requirements.txt
```

### 运行全部测试

```bash
# 单元测试 + YAML 回归测试
pytest tests/ -v
```

### 只跑回归测试

```bash
pytest tests/test_agent_regression.py -v
```

### 按分类筛选

```bash
pytest tests/ -k "FUNC"    # 只跑功能用例
pytest tests/ -k "SEC"     # 只跑安全用例
pytest tests/ -k "BOUND"   # 只跑边界用例
```

### 生成 HTML 报告

```bash
python scripts/run_report.py              # 控制台 + HTML
python scripts/run_report.py --html-only   # 仅 HTML
python scripts/run_report.py --junit       # JUnit XML
pytest tests/ --junitxml=reports/junit.xml # 直接用 pytest
# 报告输出到 reports/
```

### 运行记录、续跑与模型对比（P0.1）

```bash
# 保存本次运行的结构化结果
python scripts/run_report.py --html-only --save-run --run-id demo-run

# 从已有 run 续跑，跳过已完成用例，并合并旧结果 + 新结果
python scripts/run_report.py --html-only --resume demo-run --save-run

# 在 HTML 报告中对比另一份 run JSON
python scripts/run_report.py --html-only --compare-run demo-run
```

运行记录保存到 `reports/runs/{run_id}.json`。该目录默认不提交到 Git，用于本地保存真实模型评测结果。

### 模型注册表、Baseline 与 Dashboard（P1）

```bash
# 列出所有已注册模型
python scripts/run_report.py --list-models

# 从注册表加载模型（替代手动 --provider/--model）
python scripts/run_report.py --agent llm --model-alias deepseek-chat

# 设置 baseline 并检测退化
python scripts/run_report.py --html-only --save-run --run-id demo --set-baseline v1
python scripts/run_report.py --html-only --save-run --run-id demo2 --baseline v1

# 生成 Dashboard（历史运行全貌）
python scripts/build_dashboard.py
# 或跑完后自动刷新 Dashboard
python scripts/run_report.py --html-only --save-run --dashboard
```

### API 服务（P2）

```bash
# 启动 API 服务
python scripts/serve.py
# 打开 http://127.0.0.1:8000/health
# 提交评测：POST /runs  {"agent":"rule","case_ids":["FUNC-001"]}
```

### Docker 一键启动

```bash
docker build -t agentevallab .
docker run --rm agentevallab                           # rule 模式 smoke run
docker run --rm -v ./reports:/app/reports agentevallab  # 报告落盘
```

### LLM Agent 评测（v1.0）

```bash
# 1. 配置 API Key（支持 DeepSeek/MiniMax/OpenAI）
cp .env.example .env
# 编辑 .env 填入 API Key

# 2. 运行真实模型评测（14 条精选 × 3 轮）
python scripts/run_report.py --agent llm --provider deepseek --model deepseek-chat --repeat 3 \
  --ids FUNC-001,FUNC-002,FUNC-003,FUNC-004,FUNC-011,FUNC-017,\
BOUND-001,BOUND-002,BOUND-010,\
SEC-001,SEC-002,SEC-006,\
ERROR-001,ERROR-003 \
  --save-run --run-id ds-20260621
```

> **DeepSeek 实测 (2026-06-19):** 24/42 (57.1%), P95=7.19s, 安全 9/9
> **MiniMax M2 实测 (2026-06-19):** 27/42 (64.3%), P95=5.95s, 安全 7/9

如需横向对比 MiniMax：

```bash
python scripts/run_report.py --agent llm --provider minimax --model minimax-m2 --repeat 3 \
  --ids FUNC-001,FUNC-002,FUNC-003,FUNC-004,FUNC-011,FUNC-017,\
BOUND-001,BOUND-002,BOUND-010,\
SEC-001,SEC-002,SEC-006,\
ERROR-001,ERROR-003 \
  --save-run --run-id mm-20260621 --compare-run ds-20260621
```

### CI 自动回归

每次推送或 PR 时，GitHub Actions 自动运行全部 245 条测试并上传报告。

---

## 项目结构

```
AgentEvalLab/
├── agentevallab/              # Python 包
│   ├── tools.py               # 3 个模拟工具（计算器/天气/知识库）
│   ├── trajectory.py          # 轨迹数据结构（ToolCall/AgentTrajectory）
│   ├── agent.py               # AgentProtocol + RuleBasedAgent
│   ├── llm_agent.py           # LLMAgent 适配器（OpenAI 兼容 API）
│   ├── assertions.py          # L1-L6 多层断言引擎
│   ├── runner.py              # YAML 加载 + 用例执行 + 稳定性评测
│   ├── case_schema.py         # P0.1：YAML 元数据校验 + 默认值填充
│   ├── error_classifier.py    # P0.1：17 种失败归因分类
│   ├── run_store.py           # P0.1：run JSON 落盘 + 续跑
│   ├── fault_injector.py      # 6 种故障注入（装饰器实现）
│   └── reporter.py            # 控制台 + HTML 报告 + 稳定性指标
├── scripts/
│   └── run_report.py           # 一键报告生成
├── reports/
│   ├── report.html             # 生成的 HTML 报告
│   └── runs/                   # 本地 run JSON（默认 gitignore）
├── test_cases/                # Benchmark 数据集（339 条 YAML）
│   ├── functional/            # 正常功能 21 条
│   ├── boundary/              # 边界值 10 条
│   ├── error/                 # 异常场景 8 条
│   ├── security/              # 安全对抗 12 条
│   ├── generated/             # 模板生成 83 条
│   └── scenarios/             # 场景用例 20 条
├── tests/                     # pytest 测试
│   ├── conftest.py            # 共享 fixture
│   ├── test_tools.py          # 工具测试
│   ├── test_trajectory.py     # 轨迹测试
│   ├── test_agent.py          # Agent 测试
│   ├── test_assertions.py     # 断言测试
│   ├── test_runner.py         # Runner 测试
│   ├── test_fault_injector.py # 故障注入测试
│   ├── test_reporter.py       # 报告测试
│   ├── test_agent_regression.py  # YAML 回归测试（参数化）
│   ├── test_case_schema.py    # Schema 校验测试
│   ├── test_error_classifier.py  # 归因分类测试
│   └── test_run_store.py      # 运行存储测试
├── config.yaml                # 全局配置
├── DESIGN.md                  # 设计文档
├── IMPL_NOTES.md              # 实现笔记
└── README.md
```

---

## 核心架构

```
YAML 测试用例
       ↓
   Runner（加载 → 执行 → 断言）
       ↓                    ↓
   AgentProtocol          Assertions
       ↓                    ↓
   RuleBasedAgent         L1 结果断言
   （v1.0: LLMAgent）      L2 工具断言
       ↓                   L3 参数断言
   Trajectory              L4 轮次断言
       ↓                   L5 安全断言
       ↓                   L6 Token 成本断言（可选）
   Reporter（控制台摘要）
```

Agent 执行模型：

```
用户输入 "北京今天多少度？35度穿什么合适？"
       ↓
   Think: 检测到天气意图 + 穿搭意图
       ↓
   Act: weather("北京")
       ↓
   Observe: {"temp": 35, "weather": "晴"}
       ↓
   Think: 需要查穿搭建议
       ↓
   Act: knowledge("35度穿什么")
       ↓
   Observe: "建议穿轻薄、透气的棉麻衣物..."
       ↓
   最终回答: "北京当前天气：晴，35°C...\n\n35°C 高温天气建议..."
```

---

## 多层断言体系

| 层级 | 名称 | 检查内容 | 开关 |
|------|------|---------|------|
| L1 | 结果断言 | 最终答案包含预期关键词（支持 AND/OR） | `check_final_answer` |
| L2 | 工具断言 | 调用的工具名称序列匹配 | `check_tool_sequence` |
| L3 | 参数断言 | 传给工具的参数正确（含模糊匹配） | `check_tool_params` |
| L4 | 轮次断言 | 调用轮次在限制内 | `check_max_rounds` |
| L5 | 安全断言 | 禁止内容/工具/敏感模式检测 | `check_final_answer_not_contains` 等 |
| L6 | Token 成本 | 总 Token 是否超出预算 | `check_token_cost` |

**关键设计：最终答案正确不等于 Agent 行为正确。** 如果工具选错、参数传错、调用顺序错误，L2-L4 会标记失败，避免 Agent"蒙对答案"。L5 对拒答场景智能放行，避免误判安全回复。

---

## YAML 用例示例

```yaml
id: "FUNC-004"
name: "多工具串联-天气加穿搭"
category: functional
description: "验证 Agent 能正确处理 weather + knowledge 多工具串联场景"
input: "北京今天多少度？35度穿什么衣服合适？"
expected:
  tool_sequence: ["weather", "knowledge"]
  tool_calls:
    - tool: "weather"
      params: { city: "北京" }
    - tool: "knowledge"
      params: { query: "35度穿什么" }
  final_answer_contains: ["北京"]
  max_rounds: 3
assertions:
  check_final_answer: true
  check_tool_sequence: true
  check_tool_params: true
tags: ["multi-tool", "highlight"]
```

---

## 故障注入

6 种故障类型，使用 Python 装饰器实现，与业务逻辑零耦合：

```python
@injectable("weather")
def tool_weather(city: str) -> ToolResult:
    ...

# 测试时注入故障
with fault_context("weather", "timeout", delay=3.0):
    result = tool_weather("北京")  # 返回超时错误
```

| 故障 | 效果 |
|------|------|
| timeout | 模拟工具调用超时 |
| http_500 | 模拟服务器 500 错误 |
| invalid_json | 模拟返回格式异常 |
| empty_result | 模拟返回空结果 |
| permission_denied | 模拟权限拒绝 |
| network_unreachable | 模拟网络不可达 |

---

## 技术栈

- Python 3.10+
- pytest（参数化、fixture）
- PyYAML（测试用例）
- dataclass（数据结构）
- AST 安全求值（calculator 工具）
- 装饰器模式（故障注入）
- 上下文管理器（fault_context）

---

## 已知限制

1. **双模型真实评测已完成**（2026-06-19）：DeepSeek 24/42、P95=7.19s、安全 9/9；MiniMax M2 27/42、P95=5.95s、安全 7/9。
2. **工具数量有限**（3 个），适用于演示框架设计，生产环境可扩展。
3. **知识库为静态字典**，无检索/向量化环节；匹配策略可进一步优化。
4. **多工具串联通过率偏低**（FUNC-004 0/3），LLM 在工具链完整性上有改善空间。
5. **DeepSeek + MiniMax 双模型横向对比已完成**，后续可扩展更多模型。断言引擎仍基于规则匹配，大规模场景可升级为语义等价判断。

---

## 版本路线

| 版本 | 内容 |
|------|------|
| v0.1 | 核心闭环：YAML → Agent → 轨迹 → L1-L4 断言 → pytest ✅ |
| v0.2 | 故障注入 + 用例扩展到 40-50 条 ✅ |
| v0.3 | HTML 报告 + P50/P95/P99 延迟统计 ✅ |
| v0.4 | GitHub Actions CI + JUnit XML ✅ |
| v0.5 | 安全断言(L5) + LLMAgent 适配器 + CLI 参数 + 稳定性评测 ✅ |
| v0.5.6 | Bug 修复：FC 消息顺序、安全误判、端到端延迟 | ✅ |
| v0.5.7 | 数字自动变体 + Token 成本层(L6) | ✅ |
| v1.0 | DeepSeek 真实模型评测就绪 | ✅ |
| v1.1 | 双模型横向对比 + Provider 修复 + 三类失败归因 | ✅ |
| P0.1 | 用例schema + 17种归因 + API重试/续跑/对比 + 安全12条 | ✅ |
| P1 | 模型注册表 + baseline回归 + Dashboard + Docker | ✅ |
| P2.6 | 全量评测: DS 65.0% vs MM 75.2% (226 LLM-only) | ✅ ← 当前 |
| P2.3 | Benchmark v1.0：339条 + 9类生成器 + 382p+226skip 全绿 | ✅ |
| P2.2.1 | Benchmark质量修复：全绿368+45skip + requires_llm + schema测试 | ✅ |
| P2.2 | 154条benchmark + generate_cases.py + test_cases/README规范 | ✅ |
| P2.1 | HTTPAgent接入CLI/API + model_alias打通 + 报告端点 | ✅ |
| P2 | SQLite + FastAPI + 人工复核 + HTTPAgent | ✅ |

---

## 作者

东北大学 软件学院 信息安全专业 2026 届
