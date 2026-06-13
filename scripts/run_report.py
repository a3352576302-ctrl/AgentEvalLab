#!/usr/bin/env python
"""
scripts/run_report.py — 一键运行全部测试并生成报告

用法：
    python scripts/run_report.py                               # 控制台 + HTML（规则 Agent）
    python scripts/run_report.py --agent llm                    # 使用 LLMAgent
    python scripts/run_report.py --agent llm --repeat 3        # LLMAgent 稳定性评测（重复3次）
    python scripts/run_report.py --ids FUNC-001,FUNC-002       # 只跑指定用例
    python scripts/run_report.py --agent llm --ids FUNC-001 --repeat 3
    python scripts/run_report.py --html-only                   # 仅 HTML
    python scripts/run_report.py --console                     # 仅控制台
    python scripts/run_report.py --junit                       # JUnit XML（通过 pytest）

v1.0 真实模型评测命令：
    python scripts/run_report.py --agent llm --repeat 3 --ids FUNC-001,FUNC-002,FUNC-003,FUNC-004,FUNC-011,FUNC-017,BOUND-001,BOUND-002,BOUND-010,SEC-001,SEC-002,SEC-006,ERROR-001,ERROR-003
"""
import sys
import os
import argparse

# 修复 Windows GBK 终端 Unicode 输出问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 将项目根目录加入搜索路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# 尝试加载 .env 文件（如果 python-dotenv 可用）
try:
    from dotenv import load_dotenv
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 未安装，静默跳过

from agentevallab.agent import RuleBasedAgent
from agentevallab.llm_agent import LLMAgent
from agentevallab.runner import load_and_run_all, run_case, run_case_multi, load_yaml_case
from agentevallab.reporter import (
    print_report,
    build_html_report,
    compute_stability,
    generate_summary,
    format_duration,
)
import glob

# 路径配置
CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


def main():
    parser = argparse.ArgumentParser(
        description="AgentEvalLab — AI Agent 自动化测试报告生成器"
    )
    parser.add_argument(
        "--agent", choices=["rule", "llm"], default="rule",
        help="选择 Agent 类型: rule=RuleBasedAgent, llm=LLMAgent (默认: rule)"
    )
    parser.add_argument(
        "--repeat", type=int, default=1, metavar="N",
        help="每条用例重复运行 N 次，用于稳定性评测 (默认: 1)"
    )
    parser.add_argument(
        "--html-only", action="store_true",
        help="仅生成 HTML 报告"
    )
    parser.add_argument(
        "--console", action="store_true",
        help="仅输出控制台报告"
    )
    parser.add_argument(
        "--junit", action="store_true",
        help="通过 pytest 生成 JUnit XML 报告"
    )
    parser.add_argument(
        "--case-dir", default=CASE_DIR,
        help=f"测试用例目录 (默认: {CASE_DIR})"
    )
    parser.add_argument(
        "--ids", type=str, default="",
        help="只运行指定 ID 的用例，逗号分隔 (如 FUNC-001,FUNC-002)"
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="LLM 模型名称 (如 deepseek-chat, minimax-m2, gpt-4o)"
    )
    parser.add_argument(
        "--base-url", type=str, default=None,
        help="API 端点 URL (如 https://api.deepseek.com/v1)"
    )
    args = parser.parse_args()

    # JUnit 模式：直接走 pytest
    if args.junit:
        os.makedirs(REPORT_DIR, exist_ok=True)
        junit_path = os.path.join(REPORT_DIR, "junit.xml")
        print("正在运行 pytest --junitxml...")
        import subprocess
        subprocess.run([
            sys.executable, "-m", "pytest", "tests/",
            f"--junitxml={junit_path}",
            "-q",
        ], cwd=PROJECT_ROOT)
        print(f"\nJUnit 报告已生成: {junit_path}")
        return

    # 创建 Agent
    if args.agent == "llm":
        kwargs = {}
        if args.model:
            kwargs["model"] = args.model
        if args.base_url:
            kwargs["base_url"] = args.base_url
        agent = LLMAgent(**kwargs)
        agent_label = f"LLMAgent ({args.model or agent.model})"
    else:
        agent = RuleBasedAgent()
        agent_label = "RuleBasedAgent"

    print(f"Agent: {agent_label}")
    if args.repeat > 1:
        print(f"重复次数: {args.repeat} (稳定性评测模式)")

    # 加载所有 YAML 用例
    search_path = os.path.join(args.case_dir, "**/*.yaml")
    yaml_files = sorted(glob.glob(search_path, recursive=True))
    cases = []
    for filepath in yaml_files:
        try:
            cases.append(load_yaml_case(filepath))
        except Exception as e:
            filename = os.path.basename(filepath)
            print(f"⚠ 跳过 {filename}: {e}")

    if not cases:
        print("未找到任何 YAML 测试用例。")
        return

    # --ids 筛选
    if args.ids:
        id_set = set(s.strip() for s in args.ids.split(",") if s.strip())
        cases = [c for c in cases if c["id"] in id_set]
        if not cases:
            print(f"未找到匹配的用例 ID: {args.ids}")
            return
        print(f"筛选后: {len(cases)} 条用例 (IDs: {sorted(id_set)})")

    print(f"加载了 {len(cases)} 条用例")

    # 执行测试
    if args.repeat > 1:
        # 稳定性评测模式：每条用例重复执行
        multi_results: dict[str, list] = {}
        all_results = []
        for i, case in enumerate(cases):
            case_id = case["id"]
            results = run_case_multi(case, agent, repeat=args.repeat)
            multi_results[case_id] = results
            all_results.extend(results)
            passes = sum(1 for r in results if r.passed)
            print(f"  [{i+1}/{len(cases)}] {case_id}: {passes}/{args.repeat} 通过")

        print(f"\n完成：{sum(1 for r in all_results if r.passed)}/{len(all_results)} 通过\n")

        # 稳定性报告
        stability = compute_stability(multi_results)
        print(f"稳定性指标：")
        print(f"  多轮平均通过率: {stability['avg_pass_rate']}%")
        print(f"  工具序列一致性: {stability['tool_consistency']}%")
        print()

        results_for_report = all_results
        title = f"AgentEvalLab v0.5 稳定性评测报告 ({agent_label}, {args.repeat}轮)"
    else:
        results_for_report = []
        for i, case in enumerate(cases):
            result = run_case(case, agent)
            results_for_report.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{i+1}/{len(cases)}] {status} {result.case_id}: {result.case_name}")

        passed = sum(1 for r in results_for_report if r.passed)
        print(f"\n完成：{passed}/{len(results_for_report)} 通过\n")
        title = f"AgentEvalLab v0.5 测试报告 ({agent_label})"

    # 控制台报告
    if not args.html_only:
        print_report(results_for_report)
        if args.repeat > 1:
            _print_stability_details(stability)

    # HTML 报告
    if not args.console:
        os.makedirs(REPORT_DIR, exist_ok=True)
        html_path = os.path.join(REPORT_DIR, "report.html")
        html = build_html_report(results_for_report, title=title)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nHTML 报告已生成: {html_path}")


def _print_stability_details(stability: dict) -> None:
    """打印稳定性评测明细。"""
    print("-" * 60)
    print("  稳定性评测明细")
    print("-" * 60)
    for detail in stability.get("details", []):
        consistency = "YES" if detail["tool_consistent"] else "NO"
        print(
            f"  {detail['case_id']:20s}: {detail['passed']}/{detail['runs']} 通过 "
            f"({detail['pass_rate']:.0f}%) 工具一致:{consistency}"
        )
    print()


if __name__ == "__main__":
    main()
