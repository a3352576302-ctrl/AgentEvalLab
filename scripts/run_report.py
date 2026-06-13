#!/usr/bin/env python
"""
scripts/run_report.py — 一键运行全部测试并生成报告

用法：
    python scripts/run_report.py              # 控制台 + HTML
    python scripts/run_report.py --html-only   # 仅 HTML
    python scripts/run_report.py --console     # 仅控制台
"""
import sys
import os
import subprocess

# 将项目根目录加入搜索路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from agentevallab.agent import RuleBasedAgent
from agentevallab.runner import load_and_run_all
from agentevallab.reporter import (
    print_report,
    build_html_report,
)

# 路径配置
CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


def main():
    html_only = "--html-only" in sys.argv
    console_only = "--console" in sys.argv
    junit = "--junit" in sys.argv

    # 如果只需要 JUnit，直接用 pytest
    if junit:
        os.makedirs(REPORT_DIR, exist_ok=True)
        junit_path = os.path.join(REPORT_DIR, "junit.xml")
        print("正在运行 pytest --junitxml...")
        subprocess.run([
            sys.executable, "-m", "pytest", "tests/",
            f"--junitxml={junit_path}",
            "-q",
        ], cwd=PROJECT_ROOT)
        print(f"\nJUnit 报告已生成: {junit_path}")
        return

    # 否则用 Python Runner 执行 YAML 用例
    print("正在执行测试用例...")
    agent = RuleBasedAgent()
    results = load_and_run_all(CASE_DIR, agent)

    passed = sum(1 for r in results if r.passed)
    print(f"完成：{passed}/{len(results)} 通过\n")

    # 控制台报告
    if not html_only:
        print_report(results)

    # HTML 报告
    if not console_only:
        os.makedirs(REPORT_DIR, exist_ok=True)
        html_path = os.path.join(REPORT_DIR, "report.html")
        html = build_html_report(results, title="AgentEvalLab v0.4 测试报告")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nHTML 报告已生成: {html_path}")


if __name__ == "__main__":
    main()
