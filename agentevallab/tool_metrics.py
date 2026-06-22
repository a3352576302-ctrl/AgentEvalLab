"""
agentevallab/tool_metrics.py — 工具调用统计

从 run JSON results 计算 tool-level 指标。

使用方式：
    from agentevallab.tool_metrics import compute_tool_metrics
"""
from __future__ import annotations

import json
from typing import Any


def _normalize_params(params: dict | str | None) -> str:
    """归一化参数为字符串 key，用于去重检测。"""
    if params is None:
        return "{}"
    if isinstance(params, str):
        return params
    return json.dumps(params, ensure_ascii=False, sort_keys=True)


def compute_tool_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """从 run JSON results 计算工具调用统计。

    返回：{
        "global": {...},
        "by_tool": {...},
        "cases_with_duplicates": [...],
        "max_rounds_failures": [...]
    }
    """
    all_calls: list[dict] = []
    for r in results:
        for tc in r.get("tool_calls", []):
            all_calls.append({
                "case_id": r.get("case_id", "?"),
                "tool_name": tc.get("tool_name", "unknown"),
                "success": tc.get("success", False),
                "params_key": _normalize_params(tc.get("params_json", tc.get("params", {}))),
            })

    # 全局统计
    total = len(all_calls)
    successful = sum(1 for c in all_calls if c["success"])
    failed = total - successful

    # 重复调用检测（同 case 内同 tool+params 出现 ≥2 次）
    case_tool_counts: dict[tuple[str, str, str], int] = {}
    for c in all_calls:
        key = (c["case_id"], c["tool_name"], c["params_key"])
        case_tool_counts[key] = case_tool_counts.get(key, 0) + 1

    duplicates = sum(max(0, v - 1) for v in case_tool_counts.values())
    cases_with_dup = set()
    for (cid, _, _), count in case_tool_counts.items():
        if count >= 2:
            cases_with_dup.add(cid)

    # 按工具统计
    by_tool: dict[str, dict] = {}
    for c in all_calls:
        t = c["tool_name"]
        if t not in by_tool:
            by_tool[t] = {"call_count": 0, "success_count": 0, "failure_count": 0, "duplicate_count": 0}
        by_tool[t]["call_count"] += 1
        if c["success"]:
            by_tool[t]["success_count"] += 1
        else:
            by_tool[t]["failure_count"] += 1

    # 按工具统计重复
    tool_dup: dict[str, int] = {}
    for (cid, tname, pkey), count in case_tool_counts.items():
        if count >= 2:
            tool_dup[tname] = tool_dup.get(tname, 0) + (count - 1)
    for t, dup in tool_dup.items():
        if t in by_tool:
            by_tool[t]["duplicate_count"] = dup

    # 计算比率
    for t in by_tool:
        c = by_tool[t]["call_count"]
        by_tool[t]["success_rate"] = round(by_tool[t]["success_count"] / c * 100, 1) if c > 0 else 0

    # max_rounds 失败
    max_rounds_fails = []
    for r in results:
        failed_assertions = [a for a in r.get("assertions", []) if not a.get("passed", True)]
        if any("轮次" in a.get("name", "") for a in failed_assertions):
            max_rounds_fails.append({
                "case_id": r.get("case_id"),
                "tool_count": len(r.get("tool_calls", [])),
            })

    return {
        "global": {
            "total_tool_calls": total,
            "successful": successful,
            "failed": failed,
            "success_rate": round(successful / total * 100, 1) if total > 0 else 0,
            "duplicate_calls": duplicates,
            "duplicate_rate": round(duplicates / total * 100, 1) if total > 0 else 0,
            "cases_with_duplicates": len(cases_with_dup),
            "max_rounds_failures": len(max_rounds_fails),
        },
        "by_tool": by_tool,
        "cases_with_duplicate_ids": sorted(cases_with_dup),
        "max_rounds_failure_ids": [f["case_id"] for f in max_rounds_fails],
    }
