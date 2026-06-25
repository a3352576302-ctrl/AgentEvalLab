# AgentEvalLab

**AI Agent 自动化测试与评测平台**

[![Regression Test](https://github.com/a3352576302-ctrl/AgentEvalLab/actions/workflows/regression.yml/badge.svg)](https://github.com/a3352576302-ctrl/AgentEvalLab/actions/workflows/regression.yml)

AgentEvalLab 是一套面向 AI Agent 的自动化评测框架。通过记录 Agent 的工具调用、参数、返回结果和最终答案，从**最终结果、工具选择、参数传递、调用顺序、异常恢复、安全合规**六个维度评估 Agent 行为——不只判断"答没答对"，而是检查"过程对不对"。

---

## 📊 Benchmark 评测结果

| 指标 | 数值 |
|------|------|
| Benchmark 规模 | 339 条 YAML（226 LLM-only + 113 RuleBaseline） |
| pytest 全量 | 420 passed + 226 skipped 🟢 |
| **DeepSeek LLM-only 全量** | **169/226 (74.8%)** · P95 7.82s · $0.13/run |
| **MiniMax LLM-only 全量** | **168/226 (74.3%)** · P95 8.51s · $0.35/run |
| DeepSeek 安全防御 | 34/40 (85%) |
| 详细报告 | [reports/benchmark-v1.1-full-summary.md](reports/benchmark-v1.1-full-summary.md) |

> 评测覆盖工具调用、RAG/知识问答、多工具规划、Prompt 注入、安全拒答、异常降级等场景。同一批 Benchmark、同一套断言、两个模型——跑出完全不同的行为画像。

---

## ✨ 项目亮点

- 构建 **339 条 YAML Benchmark**，其中 226 条用于真实 LLM 评测，覆盖工具调用、多工具规划、RAG/知识问答、安全对抗和异常降级
- 设计 **L1-L6 多层断言体系**，同时评估结果正确性、工具调用路径、参数精度、安全风险和 Token 成本
- 接入 **DeepSeek 与 MiniMax** 完成双模型横向评测，同一批 Benchmark 跑出不同行为画像
- 支持 **HTML 报告、17 种失败归因、完整工具调用 trace、baseline 回归检测、中断续跑和静态 Dashboard**
- 通过 **GitHub Actions 持续集成**、**Docker 一键复现**和 **FastAPI 服务化接口**，框架自身测试覆盖率达 420 passed + 226 skipped

---

## 🎯 核心能力

### 多层断言体系（L1-L6）

| 层级 | 检查内容 |
|------|---------|
| L1 结果断言 | 最终答案是否包含预期信息（支持 AND/OR 语义） |
| L2 工具断言 | 调用的工具名称和顺序是否匹配 |
| L3 参数断言 | 传给工具的参数是否正确（含模糊匹配和归一化） |
| L4 轮次断言 | 工具调用轮次是否在限制内 |
| L5 安全断言 | 是否泄露敏感信息、被 Prompt 注入、调用禁用工具 |
| L6 Token 成本 | 总 Token 消耗是否在预算内 |

**关键设计：最终答案正确不等于 Agent 行为正确。** 工具选错、参数传错、调用顺序错——即使答案蒙对了，L2-L4 也会标记失败。

### 评测维度

- **功能正确性**：单工具调用、多工具串联、计算推理
- **边界鲁棒性**：空输入、超长输入、多语言、特殊字符
- **异常降级**：工具超时、HTTP 500、脏数据、权限拒绝——6 种故障注入
- **安全对抗**：Prompt 注入、间接注入、越狱攻击、敏感信息泄露——12 条安全用例
- **稳定性**：同一条用例重复运行，检查通过率和工具序列一致性
- **成本效率**：Token 消耗估算和月成本投影

---

## 🏗️ 技术架构

```
YAML 测试用例（339 条）
         ↓
  Runner（加载 → 执行 → 多模型调用）
         ↓                      ↓
  AgentProtocol             Assertions
         ↓                      ↓
  RuleBasedAgent            L1 结果断言
  LLMAgent (DeepSeek/MiniMax) L2 工具断言
  HTTPAgent (外部服务)       L3 参数断言
         ↓                   L4 轮次断言
  AgentTrajectory            L5 安全断言
  (完整 tool_calls trace)    L6 Token 成本
         ↓
  Reporter → 控制台 / HTML / Dashboard / JUnit XML
```

**Agent 执行循环：** Think → Act → Observe 闭环，支持 Function Calling、retry + exponential backoff、重复调用去重。

---

## 🚀 快速开始

### 环境

- Python 3.10+
- pytest + PyYAML

### 安装与运行

```bash
pip install -r requirements.txt
pytest tests/ -v                          # 全量测试
pytest tests/ -k "FUNC"                   # 按分类筛选
```

### LLM 评测

```bash
# 1. 配置 API Key
cp .env.example .env    # 填入 DeepSeek / MiniMax / OpenAI Key

# 2. 运行真模型评测（226 条 LLM-only）
python scripts/run_report.py --agent llm --provider deepseek --model deepseek-chat \
  --only-requires-llm --save-run --run-id ds-bench

# 3. 双模型对比
python scripts/run_report.py --agent llm --provider minimax --model minimax-m2 \
  --only-requires-llm --save-run --run-id mm-bench --compare-run ds-bench
```

### 报告与存储

```bash
python scripts/run_report.py --html-only --save-run           # HTML 报告 + run JSON
python scripts/run_report.py --resume ds-bench --save-run     # 中断后续跑
python scripts/build_dashboard.py                             # 历史 Dashboard
```

### API 服务

```bash
python scripts/serve.py                      # 启动 FastAPI
curl http://127.0.0.1:8000/health            # 健康检查
curl -X POST http://127.0.0.1:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"agent":"rule","case_ids":["FUNC-001"]}'  # 提交评测
```

### Docker

```bash
docker build -t agentevallab .
docker run --rm agentevallab                        # Rule 模式 smoke
docker run --rm -v ./reports:/app/reports agentevallab  # 报告落盘
```

---

## 📦 平台能力

| 能力 | 说明 |
|------|------|
| **失败归因** | 17 种分类标签：工具未调用/选错/顺序错/参数错/安全拦截失败/Provider 错误/断言过严 |
| **HTML 报告** | 含归因 Top-N、完整 tool trace、语义复核标签、模型对比表 |
| **Dashboard** | 静态 HTML：历史运行列表、总览卡片、模型对比、安全统计 |
| **Baseline 回归** | 保存运行基线，自动对比通过率/延迟/Token/安全变化，检测退化 |
| **中断续跑** | 评测中断后从已完成用例继续，合并新旧结果 |
| **模型注册表** | 集中管理模型配置（provider/base_url/价格/能力标签） |
| **语义复核** | 规则版——区分"真失败"和"工具路径不同但任务完成" |
| **Benchmark 生成器** | 模板化批量生成用例，ID 稳定，可重复生成 |
| **成本统计** | Token → 金额转换，月成本投影 |
| **工具调用统计** | 成功率、失败率、重复调用率、max_rounds 超限 |

---

## 🛠 技术栈

Python · pytest · PyYAML · FastAPI · SQLite · Docker · GitHub Actions · JUnit XML · HTML/CSS（内联） · OpenAI-compatible API

---

## 📂 项目结构

```
AgentEvalLab/
├── agentevallab/           # 核心包（Agent/runner/assertions/reporter 等）
├── scripts/                # CLI（run_report / build_dashboard / serve / generate_cases）
├── server/                 # FastAPI（app / schemas）
├── test_cases/             # Benchmark（339 条 YAML：手写 + 生成 + 场景）
├── tests/                  # pytest（420 passed + 226 skipped）
├── reports/                # 报告输出（HTML / run JSON / Dashboard / Baselines）
├── config/                 # 模型注册表
├── Dockerfile / docker-compose.yml
└── docs/                   # 设计文档 / 实现笔记
```

---

## ⚠️ 已知限制

- **工具数量有限**（3 个）——当前聚焦评测框架设计，生产可扩展
- **知识库为静态字典**（非向量检索）——保证可复现评测
- **断言引擎基于规则匹配**——大规模场景可升级语义等价判断
- **多工具串联仍是共同弱项**——System Prompt 层优化已达当前边界
- **HTTPAgent 处于接口验证阶段**——需真实外部 Agent 服务完成闭环评测

---

## 作者

东北大学 软件学院 信息安全专业 2026 届
