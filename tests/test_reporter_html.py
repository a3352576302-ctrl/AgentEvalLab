"""
tests/test_reporter_html.py — HTML 报告测试
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
    build_html_report,
)


def _make_result(case_id, passed, latency=1.0, category="functional"):
    """快速创建 CaseResult"""
    traj = AgentTrajectory(user_input="测试输入")
    traj.add_tool_call(ToolCall(
        tool_name="calculator",
        params={"expression": "1+1"},
        result=ToolResult(success=True, data={"result": 2}, latency_ms=latency),
    ))
    traj.set_final_answer("1+1 = 2")

    report = AssertionReport()
    report.results.append(AssertionResult(level="L1", name="结果断言", passed=passed))
    if not passed:
        report.results.append(AssertionResult(
            level="L2", name="工具断言", passed=False, reason="工具序列不匹配"
        ))

    return CaseResult(
        case_id=case_id,
        case_name=f"测试用例{case_id}",
        category=category,
        passed=passed,
        trajectory=traj,
        report=report,
    )


class TestHTMLReport:
    """HTML 报告生成测试"""

    def test_生成有效HTML(self):
        """生成的报告应是合法 HTML 文档"""
        results = [_make_result("CASE-001", True)]
        html = build_html_report(results)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_包含通过率信息(self):
        """HTML 中应包含通过率"""
        results = [
            _make_result("C-001", True),
            _make_result("C-002", True),
            _make_result("C-003", False),
        ]
        html = build_html_report(results)
        assert "66.7%" in html or "67" in html

    def test_包含延迟统计(self):
        """HTML 中应包含 P50/P95/P99 延迟"""
        results = [
            _make_result(f"C-{i}", True, float(i + 1)) for i in range(10)
        ]
        html = build_html_report(results)
        # P50 约 5.5ms, P95 约 9.5ms
        assert "P50" in html
        assert "P95" in html
        assert "P99" in html

    def test_包含失败详情(self):
        """失败的用例应在 HTML 中展示失败原因"""
        results = [
            _make_result("CASE-001", False),
        ]
        html = build_html_report(results)
        assert "CASE-001" in html
        assert "工具序列不匹配" in html

    def test_空结果生成空报告(self):
        """空结果不应崩溃"""
        html = build_html_report([])
        assert "<!DOCTYPE html>" in html
        assert "0" in html  # 0 条用例

    def test_包含分类统计(self):
        """HTML 应包含按分类的通过率"""
        r1 = _make_result("F-001", True, category="functional")
        r2 = _make_result("S-001", False, category="security")
        html = build_html_report([r1, r2])
        assert "functional" in html.lower() or "功能" in html
        assert "security" in html.lower() or "安全" in html

    def test_安全用例全部通过时显示绿色提示(self):
        """安全用例通过时应有正向提示"""
        results = [_make_result("SEC-001", True, category="security")]
        html = build_html_report(results)
        # 应该包含"全部通过"或类似正面描述
        assert "100" in html  # 通过率

    def test_可写入文件(self):
        """HTML 报告应能写入到文件"""
        import tempfile
        results = [_make_result("CASE-001", True)]
        html = build_html_report(results, title="AgentEvalLab 测试报告")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            tmp_path = f.name

        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "AgentEvalLab 测试报告" in content
        finally:
            os.unlink(tmp_path)


class TestSummaryLatencyStats:
    """P50/P99 延迟统计"""

    def test_P50中位数计算(self):
        """P50 应是中位数"""
        results = [
            _make_result(f"C-{i}", True, float(i + 1)) for i in range(5)
        ]
        # latencies: [1, 2, 3, 4, 5]
        summary = generate_summary(results)
        assert summary["p50_latency_ms"] == 3.0  # 中位数

    def test_P99计算(self):
        """P99 延迟验证"""
        results = [
            _make_result(f"C-{i}", True, float(i + 1)) for i in range(100)
        ]
        summary = generate_summary(results)
        # 100 个值，P99 索引 = ceil(100*0.99)-1 = 98
        assert summary["p99_latency_ms"] == pytest.approx(99.0, rel=0.1)

    def test_单条记录时P50_P95_P99相等(self):
        """只有一条记录时，P50=P95=P99"""
        results = [_make_result("C-1", True, 5.0)]
        summary = generate_summary(results)
        assert summary["p50_latency_ms"] == 5.0
        assert summary["p95_latency_ms"] == 5.0
        assert summary["p99_latency_ms"] == 5.0
