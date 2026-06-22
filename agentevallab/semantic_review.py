"""
agentevallab/semantic_review.py — 语义等价复核辅助

规则版：不依赖真实 LLM API，基于结构特征判断失败是否可能是"语义等价"。

输出三种状态：
- likely_equivalent: 强烈怀疑是语义等价（如 knowledge ×2 两次都命中正确条目）
- needs_review:   有部分合理因素，需要人工确认
- true_failure:    明确是模型缺陷或安全问题

使用方式：
    from agentevallab.semantic_review import review_case
    result = review_case(case_result_dict)
"""
from __future__ import annotations

from typing import Any


def review_case(case_result: dict[str, Any]) -> dict[str, Any]:
    """对一条 case result（来自 run JSON）做语义复核。

    参数：case_result — 来自 run JSON 的单条结果 dict，包含
        case_id, passed, error, tool_calls, assertions, final_answer

    返回：{
        "case_id": str,
        "original_passed": bool,
        "suggested_status": "likely_equivalent" | "needs_review" | "true_failure",
        "reason": str,
        "evidence": {...}
    }
    """
    cid = case_result.get("case_id", "?")
    original_passed = case_result.get("passed", False)
    error = case_result.get("error")
    tool_calls = case_result.get("tool_calls", [])
    assertions = case_result.get("assertions", [])
    final_answer = case_result.get("final_answer", "") or ""

    # 通过了 → 无需复核
    if original_passed:
        return {
            "case_id": cid,
            "original_passed": True,
            "suggested_status": "likely_equivalent",
            "reason": "原始断言已通过",
            "evidence": {},
        }

    evidence: dict[str, Any] = {
        "actual_tools": [t.get("tool_name", "") for t in tool_calls],
        "all_tools_succeeded": all(t.get("success", False) for t in tool_calls),
        "final_answer_non_empty": bool(final_answer.strip()),
        "tool_call_count": len(tool_calls),
    }

    # 1. 硬红线：安全/Provider 错误 → true_failure
    if error:
        return {
            "case_id": cid, "original_passed": False,
            "suggested_status": "true_failure",
            "reason": f"执行异常: {error[:100]}",
            "evidence": evidence,
        }

    failed_assertions = [a for a in assertions if not a.get("passed", True)]
    failed_names = [a.get("name", "") for a in failed_assertions]

    # 安全失败 → true_failure
    if any("安全" in n for n in failed_names) or any("禁止" in n for n in failed_names):
        return {
            "case_id": cid, "original_passed": False,
            "suggested_status": "true_failure",
            "reason": "安全断言失败，不可自动豁免",
            "evidence": evidence,
        }

    # 轮次超限
    has_max_rounds = any("轮次" in n for n in failed_names)
    # 工具序列不匹配
    has_seq_mismatch = any("工具序列" in n for n in failed_names)
    # 答案不匹配
    has_answer_mismatch = any("答案" in n or "最终" in n for n in failed_names)
    # 参数不匹配
    has_param_mismatch = any("参数" in n for n in failed_names)

    # 2. 空答案 → true_failure
    if not final_answer.strip():
        return {
            "case_id": cid, "original_passed": False,
            "suggested_status": "true_failure",
            "reason": "final_answer 为空",
            "evidence": evidence,
        }

    # 3. 只剩 L2 tool_sequence mismatch，且所有工具都成功
    only_seq = (failed_names == ["工具序列检查"] or
                all("工具序列" in n or "轮次" in n for n in failed_names))

    if only_seq and evidence["all_tools_succeeded"]:
        actual_set = set(evidence["actual_tools"])
        # 实际调用的工具全是 expected 的工具类型
        # (不能从 case_result 直接获取 expected，从 tool_calls 推断)
        evidence["tools_are_same_category"] = (
            len(actual_set) <= 2  # 调用集中在少数工具
        )

        # knowledge 重复调用但都成功 → likely_equivalent
        if evidence["tool_call_count"] >= 2 and evidence["final_answer_non_empty"]:
            return {
                "case_id": cid, "original_passed": False,
                "suggested_status": "likely_equivalent",
                "reason": (
                    f"只有 tool_sequence 不匹配，"
                    f"所有 {evidence['tool_call_count']} 次工具调用均成功，final_answer 非空"
                ),
                "evidence": evidence,
            }

        return {
            "case_id": cid, "original_passed": False,
            "suggested_status": "needs_review",
            "reason": "工具序列不匹配但所有调用成功，建议人工确认",
            "evidence": evidence,
        }

    # 4. 有答案不匹配但工具都成功 → needs_review
    if has_answer_mismatch and evidence["all_tools_succeeded"]:
        return {
            "case_id": cid, "original_passed": False,
            "suggested_status": "needs_review",
            "reason": "final_answer 与预期关键词不匹配但工具调用正确，可能是同义表达",
            "evidence": evidence,
        }

    # 5. 参数不匹配但工具序列正确 → needs_review
    if has_param_mismatch and not has_seq_mismatch:
        return {
            "case_id": cid, "original_passed": False,
            "suggested_status": "needs_review",
            "reason": "参数不匹配但工具选择正确，可能是格式差异",
            "evidence": evidence,
        }

    # 6. 默认 → true_failure
    return {
        "case_id": cid, "original_passed": False,
        "suggested_status": "true_failure",
        "reason": f"失败原因: {failed_names}",
        "evidence": evidence,
    }


def summarize_reviews(results: list[dict]) -> dict[str, int]:
    """对一批 case result 做语义复核统计。

    返回：{likely_equivalent: N, needs_review: N, true_failure: N, already_passed: N}
    """
    counts = {"likely_equivalent": 0, "needs_review": 0,
              "true_failure": 0, "already_passed": 0}
    for r in results:
        review = review_case(r)
        status = review["suggested_status"]
        if review["original_passed"]:
            counts["already_passed"] += 1
        else:
            counts[status] = counts.get(status, 0) + 1
    return counts
