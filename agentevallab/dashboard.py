"""
agentevallab/dashboard.py — 静态 HTML Dashboard 生成器

从 reports/runs/ 中读取所有 run JSON，生成静态 Dashboard 页面。

使用方式：
    from agentevallab.dashboard import build_dashboard
    html = build_dashboard(runs_dir="reports/runs")
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from agentevallab.run_store import list_runs, load_run


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_dashboard(
    runs_dir: str = "reports",
    baselines_dir: str | None = None,
) -> str:
    """生成完整的 Dashboard HTML。

    参数：
        runs_dir — runs 父目录（通常为 reports/）
        baselines_dir — baselines 目录

    返回：完整 HTML 字符串
    """
    runs_meta = list_runs(runs_dir)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 加载 run 详情并收集统计数据
    all_runs = []
    for r in runs_meta:
        data = load_run(r["run_id"], runs_dir)
        if data:
            all_runs.append(data)

    # 统计信息
    total_runs = len(all_runs)
    latest = all_runs[0] if all_runs else None

    # 模型对比（按 provider+model 分组，取最新）
    model_groups: dict[tuple[str, str], dict] = {}
    for data in all_runs:
        key = (data.get("provider", ""), data.get("model", ""))
        if key not in model_groups:
            model_groups[key] = data

    # 失败归因汇总（取最近 10 个 run）
    attribution_counts: dict[str, int] = {}
    for data in all_runs[:10]:
        for r in data.get("results", []):
            if not r.get("passed"):
                for label in r.get("failure_taxonomy", []):
                    attribution_counts[label] = attribution_counts.get(label, 0) + 1
    top_attributions = sorted(attribution_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    # 安全统计
    sec_total = sec_passed = 0
    if latest:
        for r in latest.get("results", []):
            if r.get("category") == "security":
                sec_total += 1
                if r.get("passed"):
                    sec_passed += 1

    # ============================================================
    # HTML
    # ============================================================
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentEvalLab Dashboard</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; background:#f3f4f6; color:#1f2937; padding:20px; }}
.container {{ max-width:1100px; margin:0 auto; }}
h1 {{ font-size:22px; color:#1e3a5f; margin-bottom:4px; }}
.subtitle {{ color:#6b7280; font-size:13px; margin-bottom:20px; }}
.grid {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:16px; }}
.card {{ background:#fff; border-radius:8px; padding:16px; margin-bottom:14px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
.card h2 {{ font-size:16px; color:#374151; margin-bottom:10px; border-bottom:2px solid #e5e7eb; padding-bottom:6px; }}
.stat-box {{ flex:1; min-width:150px; text-align:center; padding:14px; background:#f9fafb; border-radius:6px; }}
.stat-num {{ font-size:26px; font-weight:bold; color:#1e3a5f; }}
.stat-label {{ font-size:11px; color:#6b7280; margin-top:4px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ padding:8px 10px; text-align:left; border-bottom:1px solid #e5e7eb; }}
th {{ background:#f9fafb; font-weight:600; color:#374151; }}
tr:hover {{ background:#f9fafb; }}
.pass {{ color:#16a34a; font-weight:bold; }}
.fail {{ color:#dc2626; font-weight:bold; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; margin:2px; }}
.tag-pass {{ background:#dcfce7; color:#166534; }}
.tag-fail {{ background:#fef2f2; color:#991b1b; }}
.tag-warn {{ background:#fef3c7; color:#92400e; }}
.footer {{ text-align:center; color:#9ca3af; font-size:12px; margin-top:20px; }}
.ok {{ color:#16a34a; }}
.regression {{ color:#dc2626; }}
</style>
</head>
<body>
<div class="container">
<h1>🤖 AgentEvalLab Dashboard</h1>
<p class="subtitle">生成时间：{now} ｜ 历史运行：{total_runs} 次</p>
"""

    # ---- 总览卡片 ----
    if latest:
        rate = latest.get("pass_rate", 0)
        rate_color = "#22c55e" if rate >= 80 else ("#f59e0b" if rate >= 50 else "#ef4444")
        html += f"""<div class="grid">
<div class="stat-box"><div class="stat-num" style="color:{rate_color}">{rate}%</div><div class="stat-label">最新通过率</div></div>
<div class="stat-box"><div class="stat-num">{latest.get("total_cases", "?")}</div><div class="stat-label">总用例</div></div>
<div class="stat-box"><div class="stat-num" style="color:#16a34a">{latest.get("passed", "?")}</div><div class="stat-label">通过</div></div>
<div class="stat-box"><div class="stat-num" style="color:#dc2626">{latest.get("failed", "?")}</div><div class="stat-label">失败</div></div>
</div>"""

    # ---- 历史运行列表 ----
    if runs_meta:
        html += '<div class="card"><h2>📜 历史运行</h2><table>'
        html += '<tr><th>Run ID</th><th>时间</th><th>Provider</th><th>Model</th><th>用例</th><th>通过率</th></tr>'
        for r in runs_meta[:20]:
            rate = r.get("pass_rate", 0)
            rc = "pass" if rate >= 80 else ("fail" if rate < 50 else "fail")
            html += (f'<tr><td>{_html_escape(r["run_id"])}</td>'
                     f'<td>{_html_escape(r.get("created_at", ""))}</td>'
                     f'<td>{_html_escape(r.get("provider", "") or "-")}</td>'
                     f'<td>{_html_escape(r.get("model", "") or "-")}</td>'
                     f'<td>{r.get("total_cases", "?")}</td>'
                     f'<td class="{rc}">{rate}{"%" if isinstance(rate, (int, float)) else ""}</td></tr>')
        html += '</table></div>'

    # ---- 模型对比 ----
    if len(model_groups) > 1:
        html += '<div class="card"><h2>📊 模型对比</h2><table>'
        html += '<tr><th>Provider</th><th>Model</th><th>通过率</th><th>用例数</th><th>通过</th><th>失败</th></tr>'
        for (prov, mod), data in sorted(model_groups.items()):
            rate = data.get("pass_rate", 0)
            rc = "pass" if rate >= 80 else ("fail" if rate < 50 else "fail")
            html += (f'<tr><td>{_html_escape(prov or "-")}</td>'
                     f'<td>{_html_escape(mod or "-")}</td>'
                     f'<td class="{rc}">{rate}%</td>'
                     f'<td>{data.get("total_cases", "?")}</td>'
                     f'<td class="pass">{data.get("passed", "?")}</td>'
                     f'<td class="fail">{data.get("failed", "?")}</td></tr>')
        html += '</table></div>'

    # ---- 失败归因 Top N ----
    if top_attributions:
        html += '<div class="card"><h2>🔍 失败归因 Top 8（近 10 次运行）</h2><table>'
        html += '<tr><th>归因</th><th>次数</th></tr>'
        for label, count in top_attributions:
            html += (f'<tr><td><span class="tag tag-fail">{_html_escape(label)}</span></td>'
                     f'<td style="font-weight:bold">{count}</td></tr>')
        html += '</table></div>'

    # ---- 安全统计 ----
    if sec_total > 0:
        sec_rate = sec_passed / sec_total * 100
        sc = "pass" if sec_rate == 100 else "fail"
        html += (f'<div class="card"><h2>🔒 安全用例（最新运行）</h2>'
                 f'<p>通过率：<span class="{sc}" style="font-size:18px;font-weight:bold">'
                 f'{sec_passed}/{sec_total} ({sec_rate:.0f}%)</span></p></div>')

    html += '<div class="footer">AgentEvalLab P1 Dashboard</div>'
    html += '</div></body></html>'
    return html
