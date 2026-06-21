"""
agentevallab/repository.py — 数据访问层

所有数据库读写集中在本模块。
上层 service / API 不直接写 SQL。

使用方式：
    from agentevallab.repository import init_storage, save_run_record, get_run
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from agentevallab.db import get_connection


def init_storage(db_path: str | None = None) -> None:
    """初始化数据库存储（幂等）。"""
    get_connection(db_path).close()


# ============================================================
# Runs
# ============================================================

def save_run_record(
    run_record,
    db_path: str | None = None,
) -> None:
    """保存 RunRecord 到数据库。

    参数：
        run_record — RunRecord 实例（来自 agentevallab.run_store）
    """
    conn = get_connection(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """INSERT OR REPLACE INTO runs
           (run_id, provider, model, status, total_cases, passed, failed,
            pass_rate, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_record.run_id,
            getattr(run_record, "provider", ""),
            getattr(run_record, "model", ""),
            "completed",
            run_record.total_cases,
            run_record.passed,
            run_record.failed,
            round(run_record.passed / run_record.total_cases * 100, 1)
            if run_record.total_cases > 0 else 0,
            getattr(run_record, "created_at", now),
            now,
        ),
    )
    conn.commit()
    conn.close()


def get_run(run_id: str, db_path: str | None = None) -> dict | None:
    """获取单次运行记录。"""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_runs_db(limit: int = 50, db_path: str | None = None) -> list[dict]:
    """列出最近运行记录。"""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# Case Results
# ============================================================

def save_case_result(
    run_id: str,
    case_result,
    db_path: str | None = None,
) -> None:
    """保存单条用例执行结果。"""
    conn = get_connection(db_path)
    final_answer = ""
    total_latency = 0.0
    total_tokens = 0
    if case_result.trajectory:
        final_answer = case_result.trajectory.final_answer[:2000]
        total_latency = case_result.trajectory.total_latency_ms
        total_tokens = case_result.trajectory.total_tokens
    error_text = case_result.error[:500] if case_result.error else None

    conn.execute(
        """INSERT INTO case_results
           (run_id, case_id, case_name, category, passed, error,
            final_answer, total_latency_ms, total_tokens)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id,
            case_result.case_id,
            case_result.case_name,
            case_result.category,
            1 if case_result.passed else 0,
            error_text,
            final_answer,
            total_latency,
            total_tokens,
        ),
    )
    conn.commit()
    conn.close()


def list_case_results(run_id: str, db_path: str | None = None) -> list[dict]:
    """列出某次运行的所有用例结果。"""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM case_results WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# Tool Traces
# ============================================================

def save_tool_trace(
    run_id: str,
    case_id: str,
    trajectory,
    db_path: str | None = None,
) -> None:
    """保存工具调用轨迹。"""
    if trajectory is None or not trajectory.tool_calls:
        return
    conn = get_connection(db_path)
    for idx, tc in enumerate(trajectory.tool_calls):
        conn.execute(
            """INSERT INTO tool_traces
               (run_id, case_id, step_index, tool_name, params_json,
                result_json, success, latency_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                case_id,
                idx,
                tc.tool_name,
                json.dumps(tc.params, ensure_ascii=False),
                json.dumps(tc.result.data if tc.result else {}, ensure_ascii=False),
                1 if (tc.result and tc.result.success) else 0,
                tc.latency_ms or 0,
            ),
        )
    conn.commit()
    conn.close()


def list_tool_traces(
    run_id: str,
    case_id: str,
    db_path: str | None = None,
) -> list[dict]:
    """列出某个用例的工具调用轨迹。"""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM tool_traces
           WHERE run_id = ? AND case_id = ? ORDER BY step_index""",
        (run_id, case_id),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["params_json"] = json.loads(d.get("params_json", "{}"))
        d["result_json"] = json.loads(d.get("result_json", "{}"))
        result.append(d)
    return result


# ============================================================
# Review Items
# ============================================================

def create_review_item(
    run_id: str,
    case_id: str,
    reason: str = "",
    auto_failure_taxonomy: list[str] | None = None,
    db_path: str | None = None,
) -> int:
    """为失败用例创建人工复核条目。"""
    conn = get_connection(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    taxonomy_json = json.dumps(auto_failure_taxonomy or [], ensure_ascii=False)
    cursor = conn.execute(
        """INSERT INTO review_items
           (run_id, case_id, status, reason, auto_failure_taxonomy, created_at, updated_at)
           VALUES (?, ?, 'pending', ?, ?, ?, ?)""",
        (run_id, case_id, reason, taxonomy_json, now, now),
    )
    conn.commit()
    review_id = cursor.lastrowid
    conn.close()
    return review_id


def list_review_items(
    status: str | None = None,
    db_path: str | None = None,
) -> list[dict]:
    """列出复核条目。"""
    conn = get_connection(db_path)
    if status:
        rows = conn.execute(
            "SELECT * FROM review_items WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM review_items ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["auto_failure_taxonomy"] = json.loads(d.get("auto_failure_taxonomy", "[]"))
        result.append(d)
    return result


def update_review_item(
    review_id: int,
    decision: str,
    note: str = "",
    db_path: str | None = None,
) -> None:
    """更新复核条目状态。"""
    conn = get_connection(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """UPDATE review_items
           SET reviewer_decision = ?, reviewer_note = ?, status = 'reviewed', updated_at = ?
           WHERE id = ?""",
        (decision, note, now, review_id),
    )
    conn.commit()
    conn.close()
