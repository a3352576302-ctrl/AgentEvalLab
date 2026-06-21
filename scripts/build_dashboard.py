#!/usr/bin/env python
"""
scripts/build_dashboard.py — 从 reports/runs 生成静态 Dashboard

用法：
    python scripts/build_dashboard.py
    python scripts/build_dashboard.py --runs-dir reports/runs --output reports/dashboard.html
"""
import sys
import os
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from agentevallab.dashboard import build_dashboard


def main():
    parser = argparse.ArgumentParser(description="生成 AgentEvalLab Dashboard")
    parser.add_argument(
        "--runs-dir", default=os.path.join(PROJECT_ROOT, "reports"),
        help="runs 父目录 (默认: reports/)"
    )
    parser.add_argument(
        "--output", default=os.path.join(PROJECT_ROOT, "reports", "dashboard.html"),
        help="输出 HTML 路径 (默认: reports/dashboard.html)"
    )
    args = parser.parse_args()

    html = build_dashboard(runs_dir=args.runs_dir)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard 已生成: {args.output}")


if __name__ == "__main__":
    main()
