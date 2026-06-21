"""
agentevallab/runner.py — YAML 测试用例加载与执行

本模块是 AgentEvalLab 的执行引擎，负责：

1. load_yaml_case(path)   — 从 YAML 文件加载单条测试用例
2. run_case(case, agent)  — 执行 Agent → 运行断言 → 返回 CaseResult
3. run_all(cases, agent)  — 批量执行，返回 CaseResult 列表

整个流程：
    YAML 文件 → dict → Agent.run() → AssertionReport → CaseResult
"""
from __future__ import annotations

import os
import glob
from dataclasses import dataclass, field
from typing import Any

import yaml

from agentevallab.agent import AgentProtocol
from agentevallab.trajectory import AgentTrajectory
from agentevallab.assertions import assert_trajectory, AssertionReport
from agentevallab.fault_injector import fault_context
from agentevallab.case_schema import validate_case


# ============================================================
# 数据结构
# ============================================================

@dataclass
class CaseResult:
    """单条测试用例的执行结果。

    case_id     — 用例 ID（如 FUNC-001）
    case_name   — 用例名称（如 "计算器-乘法"）
    category    — 分类（functional / boundary / error / security）
    passed      — 是否全部断言通过
    trajectory  — Agent 完整执行轨迹
    report      — 断言报告
    error       — 非断言异常（如 YAML 格式错误）
    """
    case_id: str
    case_name: str
    category: str
    passed: bool
    trajectory: AgentTrajectory | None = None
    report: AssertionReport | None = None
    error: str | None = None


# ============================================================
# YAML 加载
# ============================================================

def load_yaml_case(filepath: str) -> dict[str, Any]:
    """从 YAML 文件加载单条测试用例。

    参数：
        filepath — YAML 文件的绝对路径

    返回：
        包含 id / name / category / input / expected / assertions 的字典

    异常：
        FileNotFoundError — 文件不存在
        yaml.YAMLError    — YAML 格式错误
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)

    # schema 校验 + 默认值填充（兼容旧 YAML）
    schema_result = validate_case(raw_data)

    if schema_result.errors:
        raise ValueError(
            f"YAML 文件 {filepath} 校验失败: {'; '.join(schema_result.errors)}"
        )

    # 警告输出到 stderr（不阻止加载）
    if schema_result.warnings:
        import sys
        for warning in schema_result.warnings:
            print(f"[case_schema] WARNING [{os.path.basename(filepath)}]: {warning}",
                  file=sys.stderr)

    return schema_result.data


# ============================================================
# 单条用例执行
# ============================================================

def run_case(case: dict[str, Any], agent: AgentProtocol) -> CaseResult:
    """执行一条测试用例。

    流程：
    1. 取出 input，调用 agent.run(input)
    2. 对返回的轨迹运行 assert_trajectory()
    3. 封装为 CaseResult 返回

    参数：
        case  — 从 YAML 加载的用例字典
        agent — AgentProtocol 实例

    返回：
        CaseResult，包含轨迹和断言报告
    """
    case_id = case["id"]
    case_name = case.get("name", "")
    category = case.get("category", "unknown")

    fault_cfg = case.get("fault")
    try:
        # 第 1 步：如果有故障配置，在上下文管理器中执行
        if fault_cfg:
            with fault_context(
                fault_cfg["tool"],
                fault_cfg["type"],
                **{k: v for k, v in fault_cfg.items() if k not in ("tool", "type")},
            ):
                trajectory = agent.run(case["input"])
        else:
            trajectory = agent.run(case["input"])

        # 第 2 步：运行断言
        expected = case.get("expected", {})
        switches = case.get("assertions", {})
        report = assert_trajectory(trajectory, expected, switches)

        return CaseResult(
            case_id=case_id,
            case_name=case_name,
            category=category,
            passed=report.all_passed,
            trajectory=trajectory,
            report=report,
        )

    except Exception as e:
        # 非断言错误（如 Agent 崩溃）
        return CaseResult(
            case_id=case_id,
            case_name=case_name,
            category=category,
            passed=False,
            error=f"用例执行异常: {e}",
        )


# ============================================================
# 批量执行
# ============================================================

def run_case_multi(
    case: dict[str, Any],
    agent: AgentProtocol,
    repeat: int = 3,
) -> list[CaseResult]:
    """对同一条用例重复运行多次，返回每次的结果列表。

    用于评估 Agent 的稳定性（同一输入多次运行的输出一致性）。
    """
    results = []
    for run_id in range(1, repeat + 1):
        result = run_case(case, agent)
        # 标记轮次
        result.case_id = f"{case['id']}-R{run_id}"
        results.append(result)
    return results


def run_all(cases: list[dict[str, Any]], agent: AgentProtocol) -> list[CaseResult]:
    """批量执行多条用例，返回结果列表。"""
    return [run_case(case, agent) for case in cases]


def load_and_run_all(
    case_dir: str,
    agent: AgentProtocol,
    pattern: str = "**/*.yaml",
) -> list[CaseResult]:
    """从目录中加载所有 YAML 用例并执行。

    参数：
        case_dir — 测试用例根目录（如 test_cases/）
        agent    — AgentProtocol 实例
        pattern  — glob 匹配模式

    返回：
        CaseResult 列表
    """
    search_path = os.path.join(case_dir, pattern)
    yaml_files = sorted(glob.glob(search_path, recursive=True))

    results = []
    for filepath in yaml_files:
        try:
            case = load_yaml_case(filepath)
        except Exception as e:
            # YAML 加载失败也记录为一条结果
            filename = os.path.basename(filepath)
            results.append(CaseResult(
                case_id=filename,
                case_name="加载失败",
                category="error",
                passed=False,
                error=f"加载 YAML 失败: {e}",
            ))
            continue
        results.append(run_case(case, agent))

    return results
