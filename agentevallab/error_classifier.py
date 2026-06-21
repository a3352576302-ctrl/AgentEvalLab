"""
agentevallab/error_classifier.py — 失败归因分类器

将 CaseResult 中的失败自动归类为结构化标签，区分：
- 断言类失败（模型行为不符合预期）
- Provider 类失败（API 调用错误）
- 框架类失败（断言规则过严）

使用方式：
    from agentevallab.error_classifier import classify_error
    labels = classify_error(case_result)
"""
from __future__ import annotations

from typing import Any

from agentevallab.runner import CaseResult

# ============================================================
# 错误标签定义
# ============================================================

# 断言层 → 归因标签映射
_ASSERTION_TO_TAXONOMY: dict[str, str] = {
    "最终答案包含检查": "FINAL_ANSWER_MISMATCH",
    "最终答案包含检查(OR)": "FINAL_ANSWER_MISMATCH",
    "工具序列检查": "TOOL_SEQUENCE_MISMATCH",
    "参数检查": "TOOL_PARAM_MISMATCH",
    "轮次检查": "MAX_ROUNDS_EXCEEDED",
    "安全-禁止内容检查": "SAFETY_BLOCK_FAILED",
    "安全-禁止工具检查": "SAFETY_BLOCK_FAILED",
    "安全-敏感模式检查": "SENSITIVE_INFO_LEAK",
    "Token成本检查": "TOKEN_BUDGET_EXCEEDED",
    "延迟检查": "LATENCY_EXCEEDED",
}

# Provider 错误特征词 → 标签
_PROVIDER_ERROR_PATTERNS: list[tuple[str, str]] = [
    ("401", "PROVIDER_AUTH_ERROR"),
    ("403", "PROVIDER_AUTH_ERROR"),
    ("402", "PROVIDER_AUTH_ERROR"),
    ("429", "PROVIDER_RATE_LIMIT"),
    ("rate limit", "PROVIDER_RATE_LIMIT"),
    ("timeout", "PROVIDER_TIMEOUT"),
    ("timed out", "PROVIDER_TIMEOUT"),
    ("Connection refused", "PROVIDER_NETWORK_ERROR"),
    ("Connection error", "PROVIDER_NETWORK_ERROR"),
    ("Network unreachable", "PROVIDER_NETWORK_ERROR"),
    ("400", "PROVIDER_BAD_REQUEST"),
    ("bad_request", "PROVIDER_BAD_REQUEST"),
    ("500", "PROVIDER_BAD_REQUEST"),
    ("server error", "PROVIDER_BAD_REQUEST"),
]


def _detect_over_refusal(report: Any) -> bool:
    """检测过度拒答：安全断言通过 + 但 L1 结果断言失败（答案缺少关键信息）。

    即：Agent 拒绝了正常请求，安全上没问题但功能上不完整。
    """
    if report is None:
        return False
    results = getattr(report, "results", [])
    l1_failed = any(
        r.name.startswith("最终答案") and not r.passed for r in results
    )
    l5_all_passed = all(
        r.name.startswith("安全-") and r.passed for r in results
        if r.name.startswith("安全-")
    )
    return l1_failed and l5_all_passed


def _detect_assertion_too_strict(report: Any, traj: Any) -> bool:
    """检测断言过严：L1 或 L3 失败且至少一层通过。

    即：部分断言通过、部分不通过，可能是措辞差异而非真错误。
    """
    if report is None:
        return False
    results = getattr(report, "results", [])
    if not results:
        return False
    some_passed = any(r.passed for r in results)
    some_failed = any(not r.passed for r in results)
    return some_passed and some_failed


def classify_error(case_result: CaseResult) -> list[str]:
    """对一条 CaseResult 进行失败归因分类。

    参数：
        case_result — 单条用例的执行结果

    返回：
        归因标签列表，如 ["TOOL_SEQUENCE_MISMATCH", "TOOL_PARAM_MISMATCH"]
        如果用例通过，返回空列表
    """
    labels: list[str] = []

    # 通过 → 无归因
    if case_result.passed:
        return labels

    # 1. 检查 provider 错误（同时检查 error 字段和 final_answer）
    error_text = case_result.error or ""
    if not error_text and case_result.trajectory:
        fa = case_result.trajectory.final_answer
        if "LLM 调用失败" in fa or "API Key" in fa:
            error_text = fa

    if error_text:
        error_lower = error_text.lower()
        # 检查 provider 错误
        for pattern, label in _PROVIDER_ERROR_PATTERNS:
            if pattern.lower() in error_lower:
                labels.append(label)
                break
        else:
            if "llm 调用失败" in error_lower or "api key" in error_lower:
                if "401" in error_lower or "402" in error_lower or "403" in error_lower:
                    labels.append("PROVIDER_AUTH_ERROR")
                elif "429" in error_lower:
                    labels.append("PROVIDER_RATE_LIMIT")
                elif "timeout" in error_lower:
                    labels.append("PROVIDER_TIMEOUT")
                elif "400" in error_lower:
                    labels.append("PROVIDER_BAD_REQUEST")
                else:
                    labels.append("PROVIDER_NETWORK_ERROR")
            else:
                labels.append("UNKNOWN_ERROR")
        return labels

    # 2. 断言失败 → 遍历 assertion report
    report = case_result.report
    if report is None:
        labels.append("UNKNOWN_ERROR")
        return labels

    has_assertion_label = False
    for result in report.results:
        if not result.passed:
            label = _ASSERTION_TO_TAXONOMY.get(result.name)
            if label and label not in labels:
                labels.append(label)
                has_assertion_label = True

    if not has_assertion_label:
        labels.append("UNKNOWN_ERROR")
        return labels

    # 3. 检测特殊模式

    # 工具完全未调用（Agent 没有调用任何工具）
    if case_result.trajectory and case_result.trajectory.total_rounds == 0:
        if "FINAL_ANSWER_MISMATCH" in labels:
            labels.append("TOOL_NOT_CALLED")

    # 过度拒答
    if _detect_over_refusal(report):
        labels.append("OVER_REFUSAL")

    # 断言过严（部分通过 + 部分失败）
    if _detect_assertion_too_strict(report, case_result.trajectory):
        labels.append("ASSERTION_TOO_STRICT")

    return labels


def classify_results(results: list[CaseResult]) -> dict[str, int]:
    """对一批结果进行归因统计。

    返回：
        {label: count}，按数量降序排列
    """
    counter: dict[str, int] = {}
    for r in results:
        if not r.passed:
            for label in classify_error(r):
                counter[label] = counter.get(label, 0) + 1
    return dict(sorted(counter.items(), key=lambda x: x[1], reverse=True))


def get_taxonomy_description(label: str) -> str:
    """返回归因标签的中文说明。"""
    descriptions = {
        "FINAL_ANSWER_MISMATCH": "最终答案与预期不符",
        "TOOL_NOT_CALLED": "应调用工具但未调用",
        "TOOL_SEQUENCE_MISMATCH": "工具调用顺序与预期不一致",
        "TOOL_PARAM_MISMATCH": "工具参数与预期不匹配",
        "MAX_ROUNDS_EXCEEDED": "工具调用轮次超限",
        "SAFETY_BLOCK_FAILED": "安全拦截失败（泄露或未拒绝）",
        "SENSITIVE_INFO_LEAK": "敏感信息（如密钥）泄露",
        "TOKEN_BUDGET_EXCEEDED": "Token 消耗超预算",
        "LATENCY_EXCEEDED": "延迟超限",
        "OVER_REFUSAL": "过度拒答（正常问题被拒绝）",
        "ASSERTION_TOO_STRICT": "断言可能过严（语义对但字面不匹配）",
        "PROVIDER_AUTH_ERROR": "API 认证/鉴权错误",
        "PROVIDER_RATE_LIMIT": "API 速率限制",
        "PROVIDER_TIMEOUT": "API 调用超时",
        "PROVIDER_BAD_REQUEST": "API 请求格式错误",
        "PROVIDER_NETWORK_ERROR": "网络连接错误",
        "UNKNOWN_ERROR": "未分类错误",
    }
    return descriptions.get(label, label)
