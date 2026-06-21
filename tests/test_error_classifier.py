"""
tests/test_error_classifier.py — 失败归因分类器测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.runner import CaseResult
from agentevallab.error_classifier import (
    classify_error,
    classify_results,
    get_taxonomy_description,
)
from agentevallab.assertions import AssertionResult, AssertionReport
from agentevallab.trajectory import AgentTrajectory, ToolCall, ToolResult


def _make_report(passed_results: list[tuple[str, str]] | None = None,
                 failed_results: list[tuple[str, str, str]] | None = None):
    """快速构建 AssertionReport。"""
    results = []
    for level, name in (passed_results or []):
        results.append(AssertionResult(level=level, name=name, passed=True))
    for level, name, reason in (failed_results or []):
        results.append(AssertionResult(level=level, name=name, passed=False, reason=reason))
    return AssertionReport(results=results)


def _make_traj(tool_names: list[str] | None = None):
    """快速构建 Trajectory。"""
    traj = AgentTrajectory(user_input="test")
    for name in (tool_names or []):
        traj.add_tool_call(ToolCall(
            tool_name=name, params={},
            result=ToolResult(success=True, data={}),
        ))
    return traj


class TestPassingCase:
    """通过的用例不应有归因"""

    def test_通过返回空列表(self):
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=True,
        )
        assert classify_error(r) == []


class TestToolErrors:
    """工具相关错误"""

    def test_工具序列不匹配(self):
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            report=_make_report(failed_results=[
                ("L2", "工具序列检查", "预期: [weather], 实际: [knowledge]"),
            ]),
        )
        labels = classify_error(r)
        assert "TOOL_SEQUENCE_MISMATCH" in labels

    def test_参数不匹配(self):
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            report=_make_report(failed_results=[
                ("L3", "参数检查", "参数 'city' 不匹配"),
            ]),
        )
        labels = classify_error(r)
        assert "TOOL_PARAM_MISMATCH" in labels

    def test_答案和工具都错(self):
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            report=_make_report(failed_results=[
                ("L1", "最终答案包含检查", "缺少关键词"),
                ("L2", "工具序列检查", "序列不匹配"),
            ]),
            trajectory=_make_traj(["weather"]),
        )
        labels = classify_error(r)
        assert "FINAL_ANSWER_MISMATCH" in labels
        assert "TOOL_SEQUENCE_MISMATCH" in labels

    def test_工具未调用(self):
        """L1失败 + 0次工具调用 → TOOL_NOT_CALLED"""
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            report=_make_report(failed_results=[
                ("L1", "最终答案包含检查", "缺少关键词"),
            ]),
            trajectory=_make_traj([]),  # 0 次调用
        )
        labels = classify_error(r)
        assert "TOOL_NOT_CALLED" in labels


class TestSecurityErrors:
    """安全相关错误"""

    def test_安全拦截失败(self):
        r = CaseResult(
            case_id="T", case_name="t", category="security", passed=False,
            report=_make_report(failed_results=[
                ("L5", "安全-禁止内容检查", "包含禁止内容: [API Key]"),
            ]),
        )
        labels = classify_error(r)
        assert "SAFETY_BLOCK_FAILED" in labels

    def test_敏感信息泄露(self):
        r = CaseResult(
            case_id="T", case_name="t", category="security", passed=False,
            report=_make_report(failed_results=[
                ("L5", "安全-敏感模式检查", "匹配到禁止模式"),
            ]),
        )
        labels = classify_error(r)
        assert "SENSITIVE_INFO_LEAK" in labels


class TestOverRefusal:
    """过度拒答检测"""

    def test_过度拒答(self):
        """安全全过 + L1答案失败 → 过度拒答"""
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            report=_make_report(
                passed_results=[
                    ("L5", "安全-禁止内容检查"),
                ],
                failed_results=[
                    ("L1", "最终答案包含检查", "缺少关键词: [北京]"),
                ],
            ),
        )
        labels = classify_error(r)
        assert "OVER_REFUSAL" in labels


class TestAssertionTooStrict:
    """断言过严检测"""

    def test_部分通过部分失败(self):
        """部分断言通过 + 部分不通过 → 可能过严"""
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            report=_make_report(
                passed_results=[("L1", "最终答案包含检查(OR)")],
                failed_results=[("L3", "参数检查", "参数不匹配")],
            ),
        )
        labels = classify_error(r)
        assert "ASSERTION_TOO_STRICT" in labels


class TestProviderErrors:
    """Provider 错误"""

    def test_API认证错误(self):
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            error="LLM 调用失败：Error code: 401",
        )
        labels = classify_error(r)
        assert "PROVIDER_AUTH_ERROR" in labels

    def test_限流错误(self):
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            error="LLM 调用失败：rate limit exceeded",
        )
        labels = classify_error(r)
        assert "PROVIDER_RATE_LIMIT" in labels

    def test_超时错误(self):
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            error="Connection timed out",
        )
        labels = classify_error(r)
        assert "PROVIDER_TIMEOUT" in labels

    def test_网络错误(self):
        r = CaseResult(
            case_id="T", case_name="t", category="functional", passed=False,
            error="Network unreachable",
        )
        labels = classify_error(r)
        assert "PROVIDER_NETWORK_ERROR" in labels


class TestBatchClassification:
    """批量分类统计"""

    def test_批量分类(self):
        results = [
            CaseResult("A", "a", "functional", passed=True),
            CaseResult("B", "b", "functional", passed=False,
                       report=_make_report(failed_results=[
                           ("L2", "工具序列检查", "不匹配"),
                       ])),
            CaseResult("C", "c", "functional", passed=False,
                       report=_make_report(failed_results=[
                           ("L2", "工具序列检查", "不匹配"),
                           ("L3", "参数检查", "参数错"),
                       ])),
        ]
        counts = classify_results(results)
        assert counts["TOOL_SEQUENCE_MISMATCH"] == 2
        assert counts["TOOL_PARAM_MISMATCH"] == 1


class TestDescriptions:
    """标签说明"""

    def test_已知标签有说明(self):
        desc = get_taxonomy_description("TOOL_SEQUENCE_MISMATCH")
        assert len(desc) > 0

    def test_未知标签返回自身(self):
        assert get_taxonomy_description("BOGUS") == "BOGUS"
