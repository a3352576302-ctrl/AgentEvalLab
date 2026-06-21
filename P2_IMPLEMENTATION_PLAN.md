# P2 实施计划

> 创建：2026-06-22 | 基线：269 passed + Docker 51/51 | 原则：增不替旧

---

## 一、当前 P1 能力

| 能力 | 状态 |
|------|------|
| CLI 全功能 | ✅ |
| Docker 一键跑 | ✅ |
| Dashboard 静态 HTML | ✅ |
| Baseline 回归 | ✅ |
| 模型注册表 | ✅ |

---

## 二、P2 做什么

| 目标 | 最小可交付 |
|------|-----------|
| SQLite 存储 | 替代 run JSON，存 runs/case_results/tool_traces |
| FastAPI 后端 | `/runs` CRUD + `/health` |
| 人工复核 | 失败样本入库 → API 标注 → 修正断言 |
| HTTP Agent | 调外部 Agent 服务，纳入统一评测 |

---

## 三、不做什么

- ❌ PostgreSQL/MySQL（SQLite 够用）
- ❌ Celery/Redis/消息队列（同步执行即可）
- ❌ 登录/权限
- ❌ 前端 UI
- ❌ 微服务拆分
- ❌ 云部署

---

## 四、新增文件

```
agentevallab/
├── db.py              # SQLite 建表 + 连接管理
├── repository.py      # 数据存取层（CRUD）
├── service.py         # 业务逻辑层
├── review.py          # 人工复核逻辑
├── http_agent.py      # HTTP Agent 适配器

server/
├── app.py             # FastAPI 主程序
├── schemas.py         # Pydantic 请求/响应模型

scripts/
├── serve.py           # uvicorn 启动脚本

tests/
├── test_db.py
├── test_repository.py
├── test_service.py
├── test_service_api.py
├── test_review.py
├── test_http_agent.py

data/
├── .gitkeep

requirements.txt       # +fastapi +uvicorn
```

## 五、修改文件

```
scripts/run_report.py  # +--storage db（可选），service 集成
Dockerfile             # +serve 能力
docker-compose.yml     # +ports 映射
README.md / DESIGN.md / IMPL_NOTES.md / WORK_LOG.md
```

---

## 六、分步实施

### Step 1：SQLite 数据库层

**强制分层：**
```
server/app.py → service.py → repository.py → db.py → SQLite
         API层         业务层        数据访问层    连接层
```

- API 层不允许直接写 SQL
- service.py 不允许直接写 SQL
- 所有数据库读写集中在 repository.py
- db.py 只负责连接、初始化 schema、事务辅助函数

**db.py**：`get_connection()` / `init_db()` / `transaction()` / schema 建表。

**repository.py** 至少提供：
- `init_storage()` / `save_run_record()` / `get_run()` / `list_runs()`
- `save_case_result()` / `list_case_results()`
- `save_tool_trace()` / `list_tool_traces()`
- `create_review_item()` / `list_review_items()` / `update_review_item()`

**表结构：** runs, case_results, tool_traces, review_items（见上方详细定义）。

**安全：** 所有 SQL 参数使用占位符，JSON 字段使用 json.dumps/loads。

---

### Step 2：服务层

**service.py**：`submit_run()` 调用现有 runner + 写入 db。同步执行，status 在内存中流转。

---

### Step 3：FastAPI

端口 `8000`，路由：
- `GET /health`
- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/results`
- `GET /reviews`
- `POST /reviews/{review_id}`

---

### Step 4：人工复核

失败样本自动进入 `review_items`。API 标注后，可标记为 `assertion_too_strict` / `semantic_equivalent` 等。不改变原始 CaseResult，只增加 review 记录。

---

### Step 5：HTTP Agent

实现 AgentProtocol，调外部 HTTP API。支持两种返回格式。Mock 测试覆盖。

---

### Step 6：Docker + 文档

Docker 支持 `python scripts/serve.py`。README 加 API 启动说明。

---

## 七、验证

```bash
pytest tests/ -q                                        # ≥ 269
python scripts/serve.py & curl localhost:8000/health    # {"status":"ok"}
curl -X POST localhost:8000/runs -H "Content-Type: application/json" \
  -d '{"agent":"rule","case_ids":["FUNC-001"]}'          # 返回 run_id
docker build -t agentevallab . && docker run --rm agentevallab  # 51/51
```
