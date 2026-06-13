"""
tests/test_reporter.py — 报告生成器测试

测试控制台摘要报告的生成逻辑。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.tools import ToolResult
from agentevallab.trajectory import ToolCall, AgentTrajectory
from agentevallab.assertions import AssertionResult, AssertionReport
from agentevallab.runner import CaseResult
from agentevallab.reporter import (
    generate_summary,
    format_duration,
    build_report_text,
)


class TestFormatDuration:
    """时间格式化"""

    def test_毫秒级(self):
        assert format_duration(0.5) == "0.50ms"

    def test_秒级(self):
        assert format_duration(1500) == "1.50s"

    def test_零耗时(self):
        assert format_duration(0) == "0.00ms"


class TestGenerateSummary:
    """汇总统计"""

    def _make_result(self, case_id, passed, latency=1.0):
        """快速创建 CaseResult"""
        traj = AgentTrajectory(user_input="测试输入")
        traj.add_tool_call(ToolCall(
            tool_name="calculator",
            params={"x": "1"},
            result=ToolResult(success=True, data={}, latency_ms=latency),
        ))
        traj.set_final_answer("测试答案")

        report = AssertionReport()
        report.results.append(AssertionResult(level="L1", name="结果", passed=passed))
        if not passed:
            report.results.append(AssertionResult(
                level="L2", name="工具", passed=False, reason="测试失败原因"
            ))

        return CaseResult(
            case_id=case_id,
            case_name=f"用例{case_id}",
            category="functional",
            passed=passed,
            trajectory=traj,
            report=report,
        )

    def test_全部通过(self):
        """全部通过时，通过率 100%"""
        results = [
            self._make_result("CASE-001", True, 1.0),
            self._make_result("CASE-002", True, 2.0),
            self._make_result("CASE-003", True, 3.0),
        ]
        summary = generate_summary(results)
        assert summary["total"] == 3
        assert summary["passed"] == 3
        assert summary["failed"] == 0
        assert summary["pass_rate"] == 100.0
        assert summary["p95_latency_ms"] == pytest.approx(3.0, rel=0.1)

    def test_部分失败(self):
        """混合结果"""
        results = [
            self._make_result("CASE-001", True, 1.0),
            self._make_result("CASE-002", False, 2.0),
            self._make_result("CASE-003", True, 3.0),
            self._make_result("CASE-004", False, 4.0),
        ]
        summary = generate_summary(results)
        assert summary["total"] == 4
        assert summary["passed"] == 2
        assert summary["failed"] == 2
        assert summary["pass_rate"] == 50.0

    def test_空结果集(self):
        """空结果集不崩溃"""
        summary = generate_summary([])
        assert summary["total"] == 0
        assert summary["pass_rate"] == 0.0

    def test_按分类统计(self):
        """不同分类分别统计"""
        r1 = self._make_result("F-001", True)
        r1.category = "functional"
        r2 = self._make_result("S-001", False)
        r2.category = "security"
        summary = generate_summary([r1, r2])
        assert summary["by_category"]["functional"]["total"] == 1
        assert summary["by_category"]["functional"]["passed"] == 1
        assert summary["by_category"]["security"]["total"] == 1
        assert summary["by_category"]["security"]["passed"] == 0

    def test_P95延迟计算(self):
        """P95 延迟应取第 95 百分位"""
        results = [self._make_result(f"C-{i}", True, float(i + 1)) for i in range(20)]
        summary = generate_summary(results)
        # 20 个结果，P95 索引为 ceil(20*0.95)-1 = 18
        # 从 0 开始的索引 18 对应的值是 19.0
        assert summary["p95_latency_ms"] == pytest.approx(19.0, rel=0.1)

    def test_异常用例不计入延迟统计(self):
        """有 error（非断言异常）的用例不影响延迟统计"""
        results = [
            self._make_result("CASE-001", True, 1.0),
            CaseResult(
                case_id="CASE-ERR",
                case_name="异常用例",
                category="error",
                passed=False,
                error="用例执行异常",
            ),
        ]
        summary = generate_summary(results)
        assert summary["total"] == 2
        assert summary["passed"] == 1
        # 异常用例不应纳入延迟计算
        assert summary["avg_latency_ms"] == pytest.approx(1.0, rel=0.1)


class TestBuildReportText:
    """生成报告文本"""

    def test_生成报告包含必要信息(self):
        """报告文本应包含：标题、总数、通过率、失败详情"""
        traj = AgentTrajectory(user_input="测试输入")
        traj.add_tool_call(ToolCall(
            tool_name="weather",
            params={"city": "北京"},
            result=ToolResult(success=True, data={}, latency_ms=1.5),
        ))
        traj.set_final_answer("北京天气：晴")

        report = AssertionReport()
        report.results.append(AssertionResult(level="L1", name="结果", passed=False, reason="缺少关键词"))

        result = CaseResult(
            case_id="CASE-001",
            case_name="失败用例",
            category="functional",
            passed=False,
            trajectory=traj,
            report=report,
        )

        text = build_report_text([result])
        assert "AgentEvalLab" in text
        assert "CASE-001" in text
        assert "缺少关键词" in text
        assert "weather" in text
