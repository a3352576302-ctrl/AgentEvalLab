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
from agentevallab.runner import CaseResult, load_and_run_all, run_case, run_case_multi, load_yaml_case
from agentevallab.reporter import (
    print_report,
    build_html_report,
    compute_stability,
    generate_summary,
    format_duration,
)
from agentevallab.run_store import (
    RunRecord,
    save_run,
    load_run,
    get_completed_case_ids,
    _generate_run_id,
)
from agentevallab.model_registry import load_registry, get_model
from agentevallab.baseline import save_baseline as save_baseline_data, compare_baseline
from agentevallab.dashboard import build_dashboard
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
        "--model-alias", type=str, default=None,
        help="从 config/models.yaml 注册表加载模型配置"
    )
    parser.add_argument(
        "--list-models", action="store_true",
        help="列出 config/models.yaml 中所有已注册模型"
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "minimax", "deepseek", "openai"],
        default="auto",
        help="LLM 供应商，用于选择对应 API Key/base-url (默认: auto)"
    )
    parser.add_argument(
        "--base-url", type=str, default=None,
        help="API 端点 URL (如 https://api.deepseek.com/v1)"
    )
    parser.add_argument(
        "--save-run", action="store_true",
        help="保存运行结果到 reports/runs/{run_id}.json"
    )
    parser.add_argument(
        "--run-id", type=str, default=None,
        help="指定 run_id（默认自动生成）"
    )
    parser.add_argument(
        "--resume", type=str, default=None, metavar="RUN_ID",
        help="从已有运行续跑，跳过已完成的用例"
    )
    parser.add_argument(
        "--compare-run", type=str, default=None, metavar="RUN_ID",
        help="在报告中对比另一个运行的结果"
    )
    parser.add_argument(
        "--set-baseline", type=str, default=None, metavar="NAME",
        help="将当前运行保存为 baseline"
    )
    parser.add_argument(
        "--baseline", type=str, default=None, metavar="NAME",
        help="与指定 baseline 对比，检测退化"
    )
    parser.add_argument(
        "--baseline-threshold-pass-rate", type=float, default=5,
        help="通过率退化阈值，百分比（默认 5）"
    )
    parser.add_argument(
        "--baseline-threshold-p95", type=float, default=20,
        help="P95延迟退化阈值，百分比（默认 20）"
    )
    parser.add_argument(
        "--baseline-threshold-token", type=float, default=20,
        help="Token退化阈值，百分比（默认 20）"
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="跑完后自动刷新 reports/dashboard.html"
    )
    args = parser.parse_args()

    # --list-models：打印注册表并退出
    if args.list_models:
        registry = load_registry()
        if not registry.list_aliases():
            print("未找到已注册的模型。请检查 config/models.yaml")
        else:
            print(f"{'别名':<20} {'Provider':<12} {'Model':<20} {'ToolCall':<10}")
            print("-" * 65)
            for alias in registry.list_aliases():
                cfg = registry.get(alias)
                print(f"{alias:<20} {cfg.provider:<12} {cfg.model:<20} "
                      f"{'yes' if cfg.supports_tool_calling else 'no':<10}")
        return

    # --model-alias：从注册表加载完整配置
    if args.model_alias:
        cfg = get_model(args.model_alias)
        if cfg is None:
            print(f"错误: 未找到模型别名 '{args.model_alias}'。"
                  f"可用: {load_registry().list_aliases()}")
            return
        # 注册表配置优先级高于命令行默认值
        if not args.provider or args.provider == "auto":
            args.provider = cfg.provider
        if not args.model:
            args.model = cfg.model
        if not args.base_url:
            args.base_url = cfg.default_base_url or None
        print(f"[model_registry] 已加载: {cfg.alias} "
              f"(provider={cfg.provider}, model={cfg.model})")

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
        kwargs["provider"] = args.provider
        agent = LLMAgent(**kwargs)
        agent_label = f"LLMAgent ({agent.provider}/{args.model or agent.model})"
    else:
        agent = RuleBasedAgent()
        agent_label = "RuleBasedAgent"

    print(f"Agent: {agent_label}")
    if args.repeat > 1:
        print(f"重复次数: {args.repeat} (稳定性评测模式)")

    # 续跑：获取已完成用例
    completed_ids: set = set()
    run_id = args.run_id or _generate_run_id()
    if args.resume:
        run_id = args.resume
        completed_ids = get_completed_case_ids(run_id, REPORT_DIR)
        if completed_ids:
            print(f"续跑模式: 已有 {len(completed_ids)} 条完成用例，将跳过")

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

    # resume 过滤
    if completed_ids:
        cases = [c for c in cases if c["id"] not in completed_ids]
        if not cases:
            print("所有用例已在之前的运行中完成。")
            return
        print(f"续跑跳过 {len(completed_ids)} 条，剩余: {len(cases)} 条")

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

    # 续跑：合并旧结果 + 新结果
    old_case_ids: set = set()
    if args.resume and completed_ids:
        old_case_ids = completed_ids - {r.case_id for r in results_for_report}
        # 从旧 run JSON 中加载已完成的 case（用于报告展示，不是 CaseResult 对象）
        old_run_data = load_run(run_id, reports_dir=REPORT_DIR)

    # 控制台报告
    if not args.html_only:
        print_report(results_for_report)
        if args.repeat > 1:
            _print_stability_details(stability)

    # 保存 run JSON — 续跑时合并旧结果
    if args.save_run:
        provider_name = args.provider if args.agent == "llm" else "rule"
        model_name = args.model or ""
        # 合并旧结果 + 新结果
        all_case_results = list(results_for_report)
        if args.resume and old_case_ids:
            if old_run_data:
                old_count = len(old_run_data.get("results", []))
                print(f"续跑合并: {old_count} 条旧结果 + {len(results_for_report)} 条新结果")
                # 旧结果的 case_id 不在新结果中 → 保留为占位 summary
                for old_r in old_run_data.get("results", []):
                    if old_r.get("case_id") not in {
                        r.case_id for r in results_for_report
                    }:
                        # 用简化的 CaseResult 表示旧结果
                        all_case_results.append(CaseResult(
                            case_id=old_r.get("case_id", ""),
                            case_name=old_r.get("case_name", ""),
                            category=old_r.get("category", "unknown"),
                            passed=old_r.get("passed", True),
                        ))

        record = RunRecord.from_case_results(
            all_case_results,
            provider=provider_name,
            model=model_name,
            run_id=run_id,
        )
        run_path = save_run(record, reports_dir=REPORT_DIR)
        print(f"运行记录已保存: {run_path}")

    # 设为 baseline
    if args.set_baseline:
        # 用刚保存的 run JSON
        current_data = load_run(run_id, reports_dir=REPORT_DIR)
        if current_data:
            bp = save_baseline_data(args.set_baseline, current_data)
            print(f"Baseline 已保存: {bp}")
        else:
            print("错误: 无法保存 baseline，请先使用 --save-run")

    # 与 baseline 对比
    baseline_result = None
    if args.baseline:
        current_data = load_run(run_id, reports_dir=REPORT_DIR)
        if current_data:
            baseline_result = compare_baseline(
                current_data,
                args.baseline,
                thresholds={
                    "pass_rate": args.baseline_threshold_pass_rate,
                    "p95_latency": args.baseline_threshold_p95,
                    "token": args.baseline_threshold_token,
                },
            )
            print(f"\nBaseline 对比 [{args.baseline}]: {baseline_result.status}")
            for d in baseline_result.details:
                print(f"  {d}")

    # 加载对比 run
    compare_data = None
    if args.compare_run:
        compare_data = load_run(args.compare_run, reports_dir=REPORT_DIR)
        if compare_data:
            print(f"已加载对比运行: {args.compare_run}")
        else:
            print(f"警告: 未找到对比运行 {args.compare_run}")

    # HTML 报告
    if not args.console:
        os.makedirs(REPORT_DIR, exist_ok=True)
        html_path = os.path.join(REPORT_DIR, "report.html")
        provider_name = args.provider if args.agent == "llm" else "rule"
        model_name = args.model or ""
        html = build_html_report(
            results_for_report,
            title=title,
            compare_run=compare_data,
            provider=provider_name,
            model=model_name,
        )
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nHTML 报告已生成: {html_path}")

    # Dashboard 刷新
    if args.dashboard:
        dash_html = build_dashboard(runs_dir=REPORT_DIR)
        dash_path = os.path.join(REPORT_DIR, "dashboard.html")
        with open(dash_path, "w", encoding="utf-8") as f:
            f.write(dash_html)
        print(f"Dashboard 已刷新: {dash_path}")


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
