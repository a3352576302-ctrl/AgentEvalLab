"""
agentevallab/db.py — SQLite 连接管理 + Schema 初始化

本模块只负责：
- 创建/获取数据库连接
- 初始化表结构
- 提供事务上下文管理器

所有 SQL 操作在 repository.py 中执行。
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "agentevallab.db"
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT DEFAULT '',
    model TEXT DEFAULT '',
    status TEXT DEFAULT 'completed',
    total_cases INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    pass_rate REAL DEFAULT 0.0,
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS case_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_name TEXT DEFAULT '',
    category TEXT DEFAULT '',
    passed INTEGER DEFAULT 0,
    error TEXT,
    final_answer TEXT DEFAULT '',
    total_latency_ms REAL DEFAULT 0.0,
    total_tokens INTEGER DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS tool_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    step_index INTEGER DEFAULT 0,
    tool_name TEXT DEFAULT '',
    params_json TEXT DEFAULT '{}',
    result_json TEXT DEFAULT '{}',
    success INTEGER DEFAULT 0,
    latency_ms REAL DEFAULT 0.0,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    reason TEXT DEFAULT '',
    auto_failure_taxonomy TEXT DEFAULT '[]',
    reviewer_decision TEXT,
    reviewer_note TEXT,
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """获取数据库连接并初始化 schema。

    参数：
        db_path — 数据库文件路径，默认 data/agentevallab.db
    """
    path = db_path or DEFAULT_DB_PATH
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """执行建表语句（幂等）。"""
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection):
    """事务上下文管理器，自动 commit/rollback。"""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
