"""
agentevallab/baseline.py — baseline 回归检测

保存历史运行结果为基线，对比当前运行检测退化。

使用方式：
    from agentevallab.baseline import save_baseline, compare_baseline
    save_baseline("v1", run_data)
    result = compare_baseline(current_data, "v1", thresholds={...})
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

DEFAULT_BASELINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "reports", "baselines"
)


@dataclass
class BaselineResult:
    """baseline 对比结果。"""
    baseline_name: str
    status: str = "OK"  # OK / REGRESSION / PERF_REGRESSION / COST_REGRESSION / SAFETY_REGRESSION
    details: list[str] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return self.status == "OK"


def _baseline_path(name: str, baselines_dir: str | None = None) -> str:
    d = baselines_dir or DEFAULT_BASELINE_DIR
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{name}.json")


def save_baseline(
    name: str,
    run_data: dict[str, Any],
    baselines_dir: str | None = None,
) -> str:
    """将一次运行的数据保存为 baseline。

    参数：
        name — baseline 名称
        run_data — run JSON 数据（load_run 返回的 dict）
        baselines_dir — 存储目录

    返回：文件路径
    """
    filepath = _baseline_path(name, baselines_dir)
    payload = {
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_data.get("run_id", ""),
        "data": run_data,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filepath


def load_baseline(name: str, baselines_dir: str | None = None) -> dict | None:
    """加载 baseline。

    返回：baseline dict，不存在则返回 None
    """
    filepath = _baseline_path(name, baselines_dir)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_baselines(baselines_dir: str | None = None) -> list[str]:
    """列出所有 baseline 名称。"""
    d = baselines_dir or DEFAULT_BASELINE_DIR
    if not os.path.exists(d):
        return []
    return sorted([
        f.replace(".json", "")
        for f in os.listdir(d)
        if f.endswith(".json")
    ])


def _get_category_pass_rate(data: dict, category: str) -> float:
    """从 run data 中提取某分类的通过率。"""
    results = data.get("results", [])
    cat_results = [r for r in results if r.get("category") == category]
    if not cat_results:
        return 100.0
    passed = sum(1 for r in cat_results if r.get("passed"))
    return passed / len(cat_results) * 100


def compare_baseline(
    current_data: dict[str, Any],
    baseline_name: str,
    thresholds: dict[str, float] | None = None,
    baselines_dir: str | None = None,
) -> BaselineResult:
    """将当前运行与 baseline 对比，检测退化。

    参数：
        current_data  — 当前运行的 run JSON 数据
        baseline_name — baseline 名称
        thresholds    — 退化阈值字典：
            pass_rate:      通过率下降百分比（默认 5）
            p95_latency:    P95 延迟上升百分比（默认 20）
            token:          Token 上升百分比（默认 20）
            security:       安全通过率下降百分比（默认 0，即任何下降都告警）
        baselines_dir  — baseline 目录

    返回：
        BaselineResult
    """
    t = thresholds or {}
    pass_threshold = t.get("pass_rate", 5)
    p95_threshold = t.get("p95_latency", 20)
    token_threshold = t.get("token", 20)
    security_threshold = t.get("security", 0)

    baseline = load_baseline(baseline_name, baselines_dir)
    if baseline is None:
        return BaselineResult(
            baseline_name=baseline_name,
            status="OK",
            details=[f"baseline '{baseline_name}' 不存在，跳过对比"],
        )

    b_data = baseline.get("data", {})
    result = BaselineResult(baseline_name=baseline_name)

    cur_rate = current_data.get("pass_rate", 0)
    base_rate = b_data.get("pass_rate", 0)
    cur_security = _get_category_pass_rate(current_data, "security")
    base_security = _get_category_pass_rate(b_data, "security")

    # 综合指标对比（从 results 中提取）
    cur_latencies = [
        r.get("total_latency_ms", 0)
        for r in current_data.get("results", [])
        if r.get("total_latency_ms")
    ]
    base_latencies = [
        r.get("total_latency_ms", 0)
        for r in b_data.get("results", [])
        if r.get("total_latency_ms")
    ]

    # 1. 通过率
    rate_drop = base_rate - cur_rate
    if rate_drop > pass_threshold:
        result.status = "REGRESSION"
        result.details.append(
            f"通过率下降 {rate_drop:.1f}%（基线 {base_rate}% → 当前 {cur_rate}%，阈值 {pass_threshold}%）"
        )

    # 2. P95 延迟
    if cur_latencies and base_latencies:
        cur_p95 = _p95(cur_latencies)
        base_p95 = _p95(base_latencies)
        if base_p95 > 0:
            p95_rise = (cur_p95 - base_p95) / base_p95 * 100
            if p95_rise > p95_threshold:
                if result.status == "OK":
                    result.status = "PERF_REGRESSION"
                result.details.append(
                    f"P95 延迟上升 {p95_rise:.1f}%（基线 {base_p95:.0f}ms → 当前 {cur_p95:.0f}ms，阈值 {p95_threshold}%）"
                )

    # 3. Token
    cur_tokens = [r.get("total_tokens", 0) for r in current_data.get("results", [])]
    base_tokens = [r.get("total_tokens", 0) for r in b_data.get("results", [])]
    cur_avg_tok = sum(cur_tokens) / len(cur_tokens) if cur_tokens else 0
    base_avg_tok = sum(base_tokens) / len(base_tokens) if base_tokens else 0
    if base_avg_tok > 0:
        tok_rise = (cur_avg_tok - base_avg_tok) / base_avg_tok * 100
        if tok_rise > token_threshold:
            if result.status == "OK":
                result.status = "COST_REGRESSION"
            result.details.append(
                f"Token 上升 {tok_rise:.1f}%（基线 {base_avg_tok:.0f} → 当前 {cur_avg_tok:.0f}，阈值 {token_threshold}%）"
            )

    # 4. 安全通过率
    if base_security > 0:
        sec_drop = base_security - cur_security
        if sec_drop > security_threshold:
            if result.status == "OK":
                result.status = "SAFETY_REGRESSION"
            result.details.append(
                f"安全通过率下降 {sec_drop:.1f}%（基线 {base_security:.0f}% → 当前 {cur_security:.0f}%）"
            )

    if not result.details:
        result.details.append(
            f"所有指标在阈值内（通过率 {cur_rate}% vs 基线 {base_rate}%）"
        )

    return result


def _p95(sorted_or_list: list[float]) -> float:
    """计算 P95。"""
    if not sorted_or_list:
        return 0.0
    s = sorted(sorted_or_list)
    idx = max(0, int(len(s) * 0.95) - 1)
    return s[idx]
