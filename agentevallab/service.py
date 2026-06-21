"""
agentevallab/service.py — 业务逻辑层

本层不写 SQL。编排 repository + runner + reporter。

使用方式：
    from agentevallab.service import submit_run, get_run_status
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from agentevallab.agent import RuleBasedAgent
from agentevallab.llm_agent import LLMAgent
from agentevallab.runner import CaseResult, load_yaml_case, run_case, run_case_multi
from agentevallab.run_store import RunRecord, _generate_run_id
from agentevallab.repository import (
    save_run_record,
    get_run,
    list_runs_db,
    save_case_result,
    save_tool_trace,
    create_review_item,
    list_review_items,
)

CASE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "test_cases"
)


def submit_run(
    agent_type: str = "rule",
    case_ids: list[str] | None = None,
    provider: str = "auto",
    model: str = "",
    model_alias: str | None = None,
    endpoint_url: str | None = None,
    repeat: int = 1,
    db_path: str | None = None,
) -> dict[str, Any]:
    """提交并同步执行一次评测运行。

    参数：
        agent_type — "rule" 或 "llm"
        case_ids   — 用例 ID 列表，为空则跑全部
        provider   — LLM provider
        model      — 模型名
        repeat     — 重复次数
        db_path    — 数据库路径

    返回：
        {"run_id": ..., "status": "completed"}
    """
    run_id = _generate_run_id()

    # 处理 model_alias
    if model_alias and not model:
        from agentevallab.model_registry import get_model
        cfg = get_model(model_alias)
        if cfg:
            provider = cfg.provider
            model = cfg.model

    # 创建 Agent
    if agent_type == "http":
        if not endpoint_url:
            raise ValueError("HTTP Agent 需要 --endpoint-url")
        from agentevallab.http_agent import HTTPAgent
        agent = HTTPAgent(endpoint_url)
    elif agent_type == "llm":
        agent = LLMAgent(provider=provider, model=model)
    else:
        agent = RuleBasedAgent()

    # 加载用例
    search_path = os.path.join(CASE_DIR, "**/*.yaml")
    import glob
    yaml_files = sorted(glob.glob(search_path, recursive=True))
    cases = []
    for fp in yaml_files:
        try:
            c = load_yaml_case(fp)
            if case_ids is None or c["id"] in case_ids:
                cases.append(c)
        except Exception:
            continue

    # 执行
    all_results: list[CaseResult] = []
    for case in cases:
        if repeat > 1:
            batch = run_case_multi(case, agent, repeat=repeat)
            all_results.extend(batch)
        else:
            all_results.append(run_case(case, agent))

    # 保存到数据库
    record = RunRecord.from_case_results(
        all_results,
        provider=provider if agent_type == "llm" else "rule",
        model=model,
        run_id=run_id,
    )
    save_run_record(record, db_path)

    for cr in all_results:
        save_case_result(run_id, cr, db_path)
        if cr.trajectory:
            save_tool_trace(run_id, cr.case_id, cr.trajectory, db_path)
        # 失败用例 → 创建复核条目
        if not cr.passed:
            from agentevallab.error_classifier import classify_error
            taxonomy = classify_error(cr)
            reason = cr.error or (
                cr.report and
                "; ".join(r.reason[:100] for r in cr.report.results if not r.passed)
            ) or ""
            create_review_item(run_id, cr.case_id, reason=reason or "",
                               auto_failure_taxonomy=taxonomy, db_path=db_path)

    return {
        "run_id": run_id,
        "status": "completed",
        "total_cases": record.total_cases,
        "passed": record.passed,
        "failed": record.failed,
    }


def get_run_status(run_id: str, db_path: str | None = None) -> dict | None:
    """查询运行状态。"""
    return get_run(run_id, db_path)


def get_run_results(run_id: str, db_path: str | None = None) -> dict:
    """获取运行详情（含 case_results + tool_traces）。"""
    from agentevallab.repository import list_case_results, list_tool_traces

    run = get_run(run_id, db_path)
    if not run:
        return {"error": "run not found"}

    cases = list_case_results(run_id, db_path)
    enriched = []
    for c in cases:
        c["tool_traces"] = list_tool_traces(run_id, c["case_id"], db_path)
        enriched.append(c)

    return {
        "run": run,
        "case_results": enriched,
    }


def list_runs_service(limit: int = 50, db_path: str | None = None) -> list[dict]:
    """列出所有运行。"""
    return list_runs_db(limit, db_path)


def get_reviews_service(
    status: str | None = None,
    db_path: str | None = None,
) -> list[dict]:
    """获取复核列表。"""
    return list_review_items(status, db_path)


def update_review_service(
    review_id: int,
    decision: str,
    note: str = "",
    db_path: str | None = None,
) -> None:
    """更新复核状态。"""
    from agentevallab.repository import update_review_item
    update_review_item(review_id, decision, note, db_path)
