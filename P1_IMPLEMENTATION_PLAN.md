# P1 实施计划

> 创建：2026-06-21 | 基线：245 passed | 原则：增强不重写

---

## 一、当前 P0 能力

| 能力 | 状态 |
|------|------|
| YAML 用例 51 条 | ✅ |
| L1-L6 断言 | ✅ |
| 17 种失败归因 | ✅ |
| 双模型（DeepSeek + MiniMax） | ✅ |
| Retry + provider 错误分类 | ✅ |
| --save-run / --resume / --compare-run | ✅ |
| HTML 报告（归因 + trace + 对比） | ✅ |
| pytest 245 passed | ✅ |

---

## 二、P1 做什么

| 目标 | 说明 |
|------|------|
| 模型注册表 | YAML 管理模型配置，`--list-models` |
| baseline 回归 | 保存基线，自动检测退化 |
| 最小 Dashboard | 静态 HTML，展示历史运行全貌 |
| Docker | 一键跑通 rule 模式 |

---

## 三、不做什么

- ❌ FastAPI / 数据库 / 登录
- ❌ React/Vue 前端
- ❌ 任务队列 / 多人协作
- ❌ 重写 P0 内核
- ❌ 新重型依赖

---

## 四、新增文件清单

```
config/
├── models.yaml                   # 模型注册表

agentevallab/
├── model_registry.py             # 读取模型表
├── baseline.py                   # baseline 保存/加载/退化判断
├── dashboard.py                  # 生成静态 dashboard.html

scripts/
├── build_dashboard.py            # CLI：从 runs 生成 dashboard

reports/
├── baselines/.gitkeep            # baseline 存储目录
├── dashboard.html                # 生成的 dashboard

tests/
├── test_model_registry.py
├── test_baseline.py
├── test_dashboard.py

Dockerfile
docker-compose.yml
```

## 五、修改文件清单

```
scripts/run_report.py     # +--model-alias, --list-models, --set-baseline,
                           #  --baseline, --dashboard
agentevallab/llm_agent.py  # +模型注册表集成（可选）
README.md                  # +P1 使用说明
DESIGN.md                  # +P1 架构
IMPL_NOTES.md              # +P1 记录
```

---

## 六、分步实施

### Step 1：模型注册表

**config/models.yaml** — 集中管理所有模型配置：
```yaml
models:
  deepseek-chat:
    provider: deepseek
    model: deepseek-chat
    base_url_env: DEEPSEEK_BASE_URL
    api_key_env: DEEPSEEK_API_KEY
    default_base_url: https://api.deepseek.com/v1
    supports_tool_calling: true
    context_window: 64000
    input_price_per_1m: null
    output_price_per_1m: null
    tags: [reasoning, tool_calling]
```

**agentevallab/model_registry.py** — `load_models()` 读 YAML，`get_model(alias)` 查配置。

**CLI 新增：**
- `--model-alias deepseek-chat`：从注册表加载完整配置（覆盖 --provider/--model）
- `--list-models`：打印所有注册模型
- 旧 `--provider` / `--model` 继续兼容

**验证：** test_model_registry.py + 旧命令仍可用

---

### Step 2：Baseline 回归

**agentevallab/baseline.py：**
- `save_baseline(name, run_data)` → `reports/baselines/{name}.json`
- `load_baseline(name)` → dict
- `compare_baseline(current, baseline, thresholds)` → status + details
- 退化判断维度：通过率、task_rate、安全通过率、P95延迟、Token、失败归因数

**CLI 新增：**
- `--set-baseline NAME`：将当前 run 设为基线
- `--baseline NAME`：与基线对比
- `--baseline-threshold-pass-rate 5`：通过率下降 >5% → REGRESSION
- `--baseline-threshold-p95 20`：P95上升 >20% → PERF_REGRESSION
- `--baseline-threshold-token 20`：Token上升 >20% → COST_REGRESSION

**验证：** test_baseline.py + 与已有 run JSON 对比

---

### Step 3：最小 Dashboard

**agentevallab/dashboard.py** — 纯 Python 生成静态 HTML：
- 读取 `reports/runs/` 所有 run JSON
- 生成历史运行列表表格
- 总览卡片（最新 run 的通过率/延迟/Token）
- 模型对比表（按 provider+model 分组，取最新 run）
- 失败归因 Top N（汇总所有 run）
- 安全用例统计
- baseline 状态区块

**scripts/build_dashboard.py：**
```bash
python scripts/build_dashboard.py
python scripts/build_dashboard.py --runs-dir reports/runs --output reports/dashboard.html
```

**run_report.py 新增：** `--dashboard` 参数（跑完后自动刷新 dashboard）

**验证：** test_dashboard.py + 生成 dashboard.html 可打开

---

### Step 4：Docker

**Dockerfile：**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "scripts/run_report.py", "--html-only", "--save-run", "--run-id", "docker-demo"]
```

**docker-compose.yml：**
```yaml
services:
  agentevallab:
    build: .
    volumes:
      - ./reports:/app/reports
    env_file:
      - .env
```

**验证：** `docker build -t agentevallab .` + `docker run --rm agentevallab`

---

### Step 5：文档

- README：P1 使用说明 + Docker 命令
- DESIGN：新增 P1 架构段
- IMPL_NOTES：P1 实施记录
- WORK_LOG：完整过程

---

## 七、风险

| 风险 | 缓解 |
|------|------|
| 模型注册表与旧 --provider 冲突 | --model-alias 优先级最高，旧参数 fallback |
| Dashboard 读大量 run JSON 变慢 | 只读元数据（跳过 results 详情） |
| Docker 镜像过大 | python:3.11-slim，只装 requirements |
| Baseline 对比维度太多 | 先做核心 3 维度（通过率/延迟/安全） |

## 八、验证标准

```bash
pytest tests/ -q                                    # ≥ 245 passed
python scripts/run_report.py --list-models           # 列出模型
python scripts/run_report.py --html-only --save-run --run-id p1-smoke
python scripts/run_report.py --set-baseline p1-base --run-id p1-smoke
python scripts/build_dashboard.py                    # 生成 dashboard.html
docker build -t agentevallab .
docker run --rm agentevallab                         # rule 模式通过
```
