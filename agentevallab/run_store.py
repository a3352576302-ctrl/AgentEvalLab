"""
agentevallab/run_store.py — 运行结果持久化 + 续跑

每次运行保存为 reports/runs/{run_id}.json，支持：
- 中断后从已有结果续跑
- 历史运行列表查询

使用方式：
    from agentevallab.run_store import save_run, load_run, list_runs
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from agentevallab.runner import CaseResult


# ============================================================
# 数据结构
# ============================================================

@dataclass
class RunRecord:
    """一次评测运行的完整记录。"""
    run_id: str
    created_at: str
    provider: str = ""
    model: str = ""
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    results: list[dict] = field(default_factory=list)

    @classmethod
    def from_case_results(
        cls,
        results: list[CaseResult],
        provider: str = "",
        model: str = "",
        run_id: str | None = None,
    ) -> "RunRecord":
        """从 CaseResult 列表构建 RunRecord。"""
        passed = sum(1 for r in results if r.passed)
        return cls(
            run_id=run_id or _generate_run_id(),
            created_at=datetime.now().isoformat(timespec="seconds"),
            provider=provider,
            model=model,
            total_cases=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=[_case_to_dict(r) for r in results],
        )


def _case_to_dict(r: CaseResult) -> dict:
    """CaseResult → 可序列化字典。"""
    d = {
        "case_id": r.case_id,
        "case_name": r.case_name,
        "category": r.category,
        "passed": r.passed,
    }
    if r.error:
        d["error"] = r.error
    if r.trajectory:
        d["tool_calls"] = [c.to_dict() for c in r.trajectory.tool_calls]
        d["final_answer"] = r.trajectory.final_answer[:500]  # 截断长文本
        d["total_latency_ms"] = r.trajectory.total_latency_ms
        d["total_tokens"] = r.trajectory.total_tokens
    if r.report:
        d["assertions"] = [
            {"level": a.level, "name": a.name, "passed": a.passed, "reason": a.reason}
            for a in r.report.results
            if not a.passed  # 只保存失败的断言（减少文件体积）
        ]
    return d


# ============================================================
# 存储操作
# ============================================================

def _get_runs_dir(reports_dir: str = "reports") -> str:
    """获取 runs 子目录路径。"""
    runs_dir = os.path.join(reports_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    return runs_dir


def _generate_run_id() -> str:
    """生成唯一运行 ID。"""
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def save_run(
    record: RunRecord,
    reports_dir: str = "reports",
) -> str:
    """保存运行记录到 JSON 文件。

    返回：文件路径
    """
    runs_dir = _get_runs_dir(reports_dir)
    filepath = os.path.join(runs_dir, f"{record.run_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(_run_to_dict(record), f, ensure_ascii=False, indent=2)
    return filepath


def _run_to_dict(record: RunRecord) -> dict:
    """RunRecord → 可序列化字典。"""
    return {
        "run_id": record.run_id,
        "created_at": record.created_at,
        "provider": record.provider,
        "model": record.model,
        "total_cases": record.total_cases,
        "passed": record.passed,
        "failed": record.failed,
        "pass_rate": round(record.passed / record.total_cases * 100, 1)
        if record.total_cases > 0 else 0,
        "results": record.results,
    }


def load_run(run_id: str, reports_dir: str = "reports") -> dict | None:
    """加载一次历史运行的 JSON 数据。

    返回：dict，不存在则返回 None
    """
    runs_dir = _get_runs_dir(reports_dir)
    filepath = os.path.join(runs_dir, f"{run_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_runs(reports_dir: str = "reports") -> list[dict]:
    """列出所有历史运行（仅元数据，不含详情）。"""
    runs_dir = _get_runs_dir(reports_dir)
    if not os.path.exists(runs_dir):
        return []
    runs = []
    for filename in sorted(os.listdir(runs_dir), reverse=True):
        if filename.endswith(".json"):
            filepath = os.path.join(runs_dir, filename)
            try:
                data = load_run(filename.replace(".json", ""), reports_dir)
                if data:
                    runs.append({
                        "run_id": data["run_id"],
                        "created_at": data["created_at"],
                        "provider": data.get("provider", ""),
                        "model": data.get("model", ""),
                        "pass_rate": data["pass_rate"],
                        "total_cases": data["total_cases"],
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return runs


def get_completed_case_ids(run_id: str, reports_dir: str = "reports") -> set[str]:
    """获取某个运行中已完成（不再重跑）的用例 ID 集合。

    用于续跑——跳过已有结果的用例。
    """
    data = load_run(run_id, reports_dir)
    if data is None:
        return set()
    return {r["case_id"] for r in data.get("results", []) if r.get("case_id")}
