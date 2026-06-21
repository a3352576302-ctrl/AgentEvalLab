"""
agentevallab/reporter.py — 报告生成器

本模块负责将测试结果汇总为可读报告。

v0.1：控制台摘要报告
v0.3：HTML 报告（待实现）
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from agentevallab.runner import CaseResult
from agentevallab.error_classifier import classify_error, classify_results, get_taxonomy_description


# ============================================================
# 工具函数
# ============================================================

def format_duration(ms: float) -> str:
    """格式化耗时显示。

    小于 1000ms 用 ms，大于等于用 s。
    """
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    return f"{ms:.2f}ms"


# ============================================================
# 汇总统计
# ============================================================

def generate_summary(results: list[CaseResult]) -> dict[str, Any]:
    """对一批 CaseResult 进行统计汇总。

    返回字典包含：
        total          — 总用例数
        passed         — 通过数
        failed         — 失败数
        pass_rate      — 通过率（0-100）
        avg_latency_ms — 平均延迟
        p95_latency_ms — P95 延迟
        max_latency_ms — 最大延迟
        by_category    — 按分类统计
        failures       — 失败用例列表
    """
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    # 延迟统计（只统计有轨迹的用例）
    latencies = []
    for r in results:
        if r.trajectory is not None and r.trajectory.tool_calls:
            latencies.append(r.trajectory.total_latency_ms)

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0

    # 百分位延迟
    def _percentile(sorted_data: list[float], pct: float) -> float:
        """计算第 pct 百分位（pct 为 0-100）。"""
        if not sorted_data:
            return 0.0
        idx = math.ceil(len(sorted_data) * pct / 100) - 1
        idx = max(0, min(idx, len(sorted_data) - 1))
        return sorted_data[idx]

    p50 = p95 = p99 = 0.0
    if latencies:
        sorted_lats = sorted(latencies)
        p50 = _percentile(sorted_lats, 50)
        p95 = _percentile(sorted_lats, 95)
        p99 = _percentile(sorted_lats, 99)

    # 按分类统计
    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        cat = r.category or "unknown"
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0, "failed": 0}
        by_category[cat]["total"] += 1
        if r.passed:
            by_category[cat]["passed"] += 1
        else:
            by_category[cat]["failed"] += 1

    # 失败用例
    failures = [r for r in results if not r.passed]

    # Token 统计（只统计有轨迹的用例）
    total_tokens_list = []
    for r in results:
        if r.trajectory is not None and r.trajectory.total_tokens > 0:
            total_tokens_list.append(r.trajectory.total_tokens)

    avg_tokens = sum(total_tokens_list) / len(total_tokens_list) if total_tokens_list else 0
    max_tokens = max(total_tokens_list) if total_tokens_list else 0
    p95_tokens = 0.0
    if total_tokens_list:
        sorted_tokens = sorted(total_tokens_list)
        p95_tokens = _percentile(sorted_tokens, 95)

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(pass_rate, 1),
        "avg_latency_ms": round(avg_latency, 2),
        "p50_latency_ms": round(p50, 2),
        "p95_latency_ms": round(p95, 2),
        "p99_latency_ms": round(p99, 2),
        "max_latency_ms": round(max_latency, 2),
        "avg_total_tokens": round(avg_tokens, 2),
        "p95_total_tokens": round(p95_tokens, 2),
        "max_total_tokens": round(max_tokens, 2),
        "by_category": by_category,
        "failures": failures,
    }


# ============================================================
# 报告文本生成
# ============================================================

def build_report_text(results: list[CaseResult]) -> str:
    """生成控制台报告文本。

    包含：汇总统计、分类明细、失败详情、轨迹摘要。
    """
    summary = generate_summary(results)
    lines = []

    # 标题
    lines.append("=" * 60)
    lines.append("  AgentEvalLab v0.5 — AI Agent 自动化评测报告")
    lines.append("=" * 60)
    lines.append("")

    # 汇总
    lines.append(f"  总用例数: {summary['total']}")
    lines.append(f"  通过: {summary['passed']}  |  失败: {summary['failed']}")
    lines.append(f"  通过率: {summary['pass_rate']}%")
    lines.append("")
    lines.append(f"  平均延迟: {format_duration(summary['avg_latency_ms'])}")
    lines.append(f"  P95 延迟: {format_duration(summary['p95_latency_ms'])}")
    lines.append(f"  最大延迟: {format_duration(summary['max_latency_ms'])}")
    if summary.get('avg_total_tokens', 0) > 0:
        lines.append(f"  平均 Token: {summary['avg_total_tokens']:.0f}")
        lines.append(f"  P95 Token: {summary['p95_total_tokens']:.0f}")
        lines.append(f"  最大 Token: {summary['max_total_tokens']:.0f}")
    lines.append("")

    # 分类明细
    if summary["by_category"]:
        lines.append("-" * 60)
        lines.append("  分类统计")
        lines.append("-" * 60)
        for cat, stats in summary["by_category"].items():
            cat_pass_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            lines.append(
                f"  {cat:15s}: {stats['passed']}/{stats['total']} 通过 "
                f"({cat_pass_rate:.0f}%)"
            )
        lines.append("")

    # 失败详情
    if summary["failures"]:
        lines.append("-" * 60)
        lines.append("  失败用例详情")
        lines.append("-" * 60)
        for f in summary["failures"]:
            lines.append(f"  [{f.case_id}] {f.case_name}")

            if f.error:
                # 非断言异常（Agent 崩溃等）
                lines.append(f"    异常: {f.error}")
            elif f.report:
                # 断言失败
                for r in f.report.results:
                    if not r.passed:
                        lines.append(f"    [{r.level}] {r.name}: {r.reason}")

            # 显示工具调用轨迹
            if f.trajectory and f.trajectory.tool_calls:
                tools = f.trajectory.tool_names
                lines.append(f"    轨迹: {' → '.join(tools)} "
                             f"({format_duration(f.trajectory.total_latency_ms)})")
            lines.append("")

    # 安全提示
    sec_results = [r for r in results if r.category == "security"]
    if sec_results:
        sec_passed = sum(1 for r in sec_results if r.passed)
        lines.append(f"  安全用例: {sec_passed}/{len(sec_results)} 通过")
        lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)


# ============================================================
# HTML 报告
# ============================================================

def _html_escape(text: str) -> str:
    """HTML 转义，防止 XSS。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _progress_bar(pct: float, width: int = 30) -> str:
    """生成纯 CSS 进度条的 HTML。"""
    filled = int(width * pct / 100)
    color = "#22c55e" if pct >= 80 else ("#f59e0b" if pct >= 50 else "#ef4444")
    return (
        f'<div style="background:#e5e7eb;border-radius:4px;height:20px;width:100%">'
        f'<div style="background:{color};border-radius:4px;height:100%;width:{pct:.0f}%;'
        f'text-align:center;color:#fff;font-size:12px;line-height:20px">{pct:.1f}%</div>'
        f'</div>'
    )


def build_html_report(
    results: list[CaseResult],
    title: str = "AgentEvalLab 测试报告",
    compare_run: dict | None = None,
    provider: str = "",
    model: str = "",
) -> str:
    """生成独立的 HTML 报告文件。

    包含：
        - 汇总仪表盘（通过率、延迟、Token、分类）
        - 模型任务完成率（仅 L1 结果层）
        - 失败归因 Top N
        - 失败用例详情（断言原因 + 归因标签 + trace）
        - 可选：模型对比（compare_run）
        - 无外部依赖，所有 CSS 内联

    参数：
        results      — CaseResult 列表
        title        — 报告标题
        compare_run  — 对比运行数据（load_run 返回的 dict）
        provider     — LLM provider 名称
        model        — 模型名称
    """
    summary = generate_summary(results)
    attribution = classify_results(results)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 模型任务完成率（仅 L1）
    l1_total = len([r for r in results if r.report and any(
        a.name.startswith("最终答案") for a in r.report.results)])
    l1_passed = len([r for r in results if r.report and any(
        a.name.startswith("最终答案") and a.passed for a in r.report.results)])
    if l1_total == 0:
        l1_total = summary["total"]
        l1_passed = summary["passed"]
    task_rate = (l1_passed / l1_total * 100) if l1_total > 0 else 0

    # 通过率颜色
    rate = summary["pass_rate"]
    rate_color = "#22c55e" if rate >= 80 else ("#f59e0b" if rate >= 50 else "#ef4444")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_html_escape(title)}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; background:#f3f4f6; color:#1f2937; padding:20px; }}
.container {{ max-width:960px; margin:0 auto; }}
.card {{ background:#fff; border-radius:8px; padding:20px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
h1 {{ font-size:24px; color:#1e3a5f; margin-bottom:4px; }}
h2 {{ font-size:18px; color:#374151; margin-bottom:12px; border-bottom:2px solid #e5e7eb; padding-bottom:8px; }}
.subtitle {{ color:#6b7280; font-size:13px; margin-bottom:16px; }}
.stats {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:16px; }}
.stat {{ flex:1; min-width:120px; text-align:center; padding:16px; background:#f9fafb; border-radius:6px; }}
.stat-num {{ font-size:28px; font-weight:bold; color:#1e3a5f; }}
.stat-label {{ font-size:12px; color:#6b7280; margin-top:4px; }}
.metric-row {{ display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; }}
.metric {{ font-size:13px; color:#4b5563; background:#f3f4f6; padding:4px 10px; border-radius:4px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ padding:8px 12px; text-align:left; border-bottom:1px solid #e5e7eb; }}
th {{ background:#f9fafb; font-weight:600; color:#374151; }}
tr:hover {{ background:#f9fafb; }}
.pass {{ color:#16a34a; font-weight:bold; }}
.fail {{ color:#dc2626; font-weight:bold; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; margin:2px; }}
.tag-pass {{ background:#dcfce7; color:#166534; }}
.tag-fail {{ background:#fef2f2; color:#991b1b; }}
.tag-warn {{ background:#fef3c7; color:#92400e; }}
.footer {{ text-align:center; color:#9ca3af; font-size:12px; margin-top:24px; }}
</style>
</head>
<body>
<div class="container">
<h1>{_html_escape(title)}</h1>
<p class="subtitle">生成时间：{now} ｜ AgentEvalLab v0.5</p>

<!-- 汇总 -->
<div class="card">
<h2>📊 测试汇总</h2>
<div class="stats">
<div class="stat"><div class="stat-num" style="color:{rate_color}">{rate}%</div><div class="stat-label">通过率</div></div>
<div class="stat"><div class="stat-num">{summary['total']}</div><div class="stat-label">总用例</div></div>
<div class="stat"><div class="stat-num" style="color:#16a34a">{summary['passed']}</div><div class="stat-label">通过</div></div>
<div class="stat"><div class="stat-num" style="color:#dc2626">{summary['failed']}</div><div class="stat-label">失败</div></div>
</div>
{_progress_bar(rate)}
<div class="metric-row" style="margin-top:12px">
<span class="metric">⏱ P50: {format_duration(summary['p50_latency_ms'])}</span>
<span class="metric">⏱ P95: {format_duration(summary['p95_latency_ms'])}</span>
<span class="metric">⏱ P99: {format_duration(summary['p99_latency_ms'])}</span>
<span class="metric">📈 平均: {format_duration(summary['avg_latency_ms'])}</span>
<span class="metric">🔺 最大: {format_duration(summary['max_latency_ms'])}</span>
</div>"""

    # Token 指标
    if summary.get('avg_total_tokens', 0) > 0:
        html += f"""<div class="metric-row" style="margin-top:8px">
<span class="metric">🪙 平均 Token: {summary['avg_total_tokens']:.0f}</span>
<span class="metric">🪙 P95 Token: {summary['p95_total_tokens']:.0f}</span>
<span class="metric">🪙 最大 Token: {summary['max_total_tokens']:.0f}</span>
</div>"""

    html += """
</div>
</div>
"""

    # 模型信息 + 任务完成率
    if provider or model:
        html += '<div class="card"><h2>🤖 模型信息</h2>'
        html += f'<p style="font-size:14px">Provider: <strong>{_html_escape(provider)}</strong>'
        if model:
            html += f' ｜ Model: <strong>{_html_escape(model)}</strong>'
        html += '</p>'
        html += '<div class="stats" style="margin-top:12px">'
        html += (f'<div class="stat"><div class="stat-num" style="color:#1e3a5f">'
                 f'{summary["pass_rate"]}%</div>'
                 f'<div class="stat-label">框架测试通过率（L1-L6）</div></div>')
        html += (f'<div class="stat"><div class="stat-num" style="color:#7c3aed">'
                 f'{task_rate:.1f}%</div>'
                 f'<div class="stat-label">模型任务完成率（仅L1）</div></div>')
        html += '</div>'
        html += ('<p style="font-size:12px;color:#6b7280;margin-top:8px">'
                 '框架测试通过率 = 全部断言通过的比例。模型任务完成率 = 仅看最终答案是否包含预期内容。'
                 '两者差异越大，说明过程性错误越多（工具用错/参数传错/多轮兜圈）。</p>')
        html += '</div>'

    # 失败归因
    if attribution:
        html += '<div class="card"><h2>🔍 失败归因 Top 5</h2><table>'
        html += '<tr><th>归因类型</th><th>说明</th><th>次数</th></tr>'
        for label, count in list(attribution.items())[:5]:
            desc = get_taxonomy_description(label)
            html += (f'<tr><td><span class="tag tag-fail">{_html_escape(label)}</span></td>'
                     f'<td>{_html_escape(desc)}</td>'
                     f'<td style="font-weight:bold">{count}</td></tr>')
        html += '</table></div>'

    # 分类统计
    if summary["by_category"]:
        html += '<div class="card"><h2>📂 分类统计</h2><table>'
        html += '<tr><th>分类</th><th>用例数</th><th>通过</th><th>失败</th><th>通过率</th></tr>'
        for cat, stats in summary["by_category"].items():
            cat_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            cls = "pass" if cat_rate >= 80 else ("fail" if cat_rate < 50 else "warn")
            html += (
                f'<tr><td>{_html_escape(cat)}</td>'
                f'<td>{stats["total"]}</td>'
                f'<td class="pass">{stats["passed"]}</td>'
                f'<td class="fail">{stats["failed"]}</td>'
                f'<td class="{cls}">{cat_rate:.0f}%</td></tr>'
            )
        html += '</table></div>'

    # 失败详情
    if summary["failures"]:
        html += '<div class="card"><h2>❌ 失败用例详情</h2>'
        for f in summary["failures"]:
            # 归因标签
            labels = classify_error(f)
            html += f'<div style="margin-bottom:12px;padding:12px;background:#fef2f2;border-radius:6px">'
            html += f'<strong>[{_html_escape(f.case_id)}] {_html_escape(f.case_name)}</strong>'
            html += f' <span class="tag tag-fail">{_html_escape(f.category)}</span>'
            if labels:
                label_tags = " ".join(
                    f'<span class="tag tag-warn">{_html_escape(l)}</span>'
                    for l in labels
                )
                html += f' <span style="margin-left:4px">{label_tags}</span>'

            if f.error:
                html += f'<p style="margin-top:8px;color:#dc2626">⚠ 异常: {_html_escape(f.error[:300])}</p>'
            elif f.report:
                for r in f.report.results:
                    if not r.passed:
                        html += (
                            f'<p style="margin-top:4px;font-size:13px;color:#991b1b">'
                            f'[{_html_escape(r.level)}] {_html_escape(r.name)}: '
                            f'{_html_escape(r.reason[:200])}</p>'
                        )

            # 完整工具调用 trace
            if f.trajectory and f.trajectory.tool_calls:
                html += ('<details style="margin-top:8px;font-size:12px">'
                         '<summary style="cursor:pointer;color:#6b7280">'
                         f'🔧 工具调用 Trace ({len(f.trajectory.tool_calls)} 次, '
                         f'{format_duration(f.trajectory.total_latency_ms)})</summary>')
                for idx, tc in enumerate(f.trajectory.tool_calls):
                    status = "✅" if tc.result.success else "❌"
                    params_str = str(tc.params)[:150]
                    html += (
                        f'<div style="margin:4px 0;padding:6px;background:#fff;'
                        f'border-radius:4px;font-family:monospace;font-size:11px">'
                        f'{status} <strong>{_html_escape(tc.tool_name)}</strong>'
                        f'({format_duration(tc.latency_ms or 0)}) '
                        f'<span style="color:#6b7280">{_html_escape(params_str)}</span>'
                        f'</div>'
                    )
                # Token 信息
                if f.trajectory.total_tokens > 0:
                    html += (
                        f'<div style="margin-top:4px;font-size:11px;color:#9ca3af">'
                        f'Token: {f.trajectory.total_tokens} '
                        f'(prompt={f.trajectory.prompt_tokens}, '
                        f'completion={f.trajectory.completion_tokens})'
                        f'</div>'
                    )
                html += '</details>'

            html += '</div>'
        html += '</div>'

    # 安全用例
    sec_results = [r for r in results if r.category == "security"]
    if sec_results:
        sec_passed = sum(1 for r in sec_results if r.passed)
        sec_color = "#22c55e" if sec_passed == len(sec_results) else "#ef4444"
        html += (
            f'<div class="card">'
            f'<h2>🔒 安全评测</h2>'
            f'<p>安全用例通过率：'
            f'<span style="font-size:20px;font-weight:bold;color:{sec_color}">'
            f'{sec_passed}/{len(sec_results)}</span></p>'
            f'</div>'
        )

    html += '<div class="footer">AgentEvalLab v0.5 — AI Agent 自动化测试与评测平台</div>'
    html += '</div></body></html>'

    return html


# ============================================================
# 稳定性指标（多轮运行）
# ============================================================

def compute_stability(
    multi_results: dict[str, list[CaseResult]],
) -> dict[str, Any]:
    """对多轮运行结果计算稳定性指标。

    参数：
        multi_results — {case_id: [run1, run2, run3]} 格式

    返回：
        pass_at_k       — 每个用例的通过率（k 次中通过次数）
        tool_consistency — 工具序列一致性（所有轮次的 tool_names 是否相同）
        avg_pass_rate    — 多轮平均通过率
    """
    if not multi_results:
        return {
            "avg_pass_rate": 0.0,
            "tool_consistency": 0.0,
            "details": [],
        }

    details = []
    total_pass = 0
    total_runs = 0
    consistent_count = 0

    for case_id, runs in multi_results.items():
        k = len(runs)
        passes = sum(1 for r in runs if r.passed)
        total_pass += passes
        total_runs += k

        # 工具序列一致性：所有轮次的 tool_names 是否完全相同
        tool_seqs = [tuple(r.trajectory.tool_names) if r.trajectory else ()
                     for r in runs]
        all_same = len(set(tool_seqs)) == 1

        if all_same:
            consistent_count += 1

        details.append({
            "case_id": case_id,
            "runs": k,
            "passed": passes,
            "pass_rate": passes / k * 100 if k > 0 else 0,
            "tool_consistent": all_same,
            "tool_sequences": [list(s) for s in tool_seqs],
        })

    avg_pass = total_pass / total_runs * 100 if total_runs > 0 else 0.0
    consistency = consistent_count / len(details) * 100 if details else 0.0

    return {
        "avg_pass_rate": round(avg_pass, 1),
        "tool_consistency": round(consistency, 1),
        "details": details,
    }


def print_report(results: list[CaseResult]) -> None:
    """直接打印报告到控制台。"""
    print(build_report_text(results))
