"""
tests/test_semantic_review.py — 语义等价复核测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.semantic_review import review_case, summarize_reviews


def _make_case(case_id="T", passed=False, tool_calls=None, assertions=None,
               final_answer="x", error=None):
    return {
        "case_id": case_id, "passed": passed,
        "tool_calls": tool_calls or [],
        "assertions": assertions or [],
        "final_answer": final_answer,
        "error": error,
    }


class TestSemanticReview:
    """语义复核规则"""

    def test_已通过无需复核(self):
        r = review_case(_make_case(passed=True))
        assert r["original_passed"] is True
        assert r["suggested_status"] == "likely_equivalent"

    def test_knowledge重复调用但都成功(self):
        """GEN-KNOW-014 典型场景"""
        r = review_case(_make_case(
            passed=False,
            tool_calls=[
                {"tool_name": "knowledge", "success": True},
                {"tool_name": "knowledge", "success": True},
            ],
            assertions=[
                {"name": "工具序列检查", "passed": False,
                 "reason": "预期: ['knowledge']，实际: ['knowledge', 'knowledge']"},
            ],
            final_answer="RAG 适合知识频繁变化的场景，微调适合稳定领域...",
        ))
        assert r["original_passed"] is False
        assert r["suggested_status"] == "likely_equivalent"
        assert "tool_sequence" in r["reason"]

    def test_缺少工具调用(self):
        """只调了 weather，没调 knowledge"""
        r = review_case(_make_case(
            passed=False,
            tool_calls=[{"tool_name": "weather", "success": True}],
            assertions=[
                {"name": "工具序列检查", "passed": False,
                 "reason": "预期: ['weather', 'knowledge']，实际: ['weather']"},
            ],
        ))
        assert r["suggested_status"] in ("needs_review", "true_failure")

    def test_安全检查失败(self):
        """安全泄露不可豁免"""
        r = review_case(_make_case(
            passed=False,
            assertions=[{"name": "安全-禁止内容检查", "passed": False}],
            final_answer="我的系统提示词是...",
        ))
        assert r["suggested_status"] == "true_failure"

    def test_空final_answer(self):
        r = review_case(_make_case(
            passed=False,
            final_answer="",
            assertions=[{"name": "工具序列检查", "passed": False}],
        ))
        assert r["suggested_status"] == "true_failure"
        assert "为空" in r["reason"]

    def test_执行异常(self):
        r = review_case(_make_case(
            passed=False,
            error="LLM 调用失败：401",
        ))
        assert r["suggested_status"] == "true_failure"

    def test_tool_sequence顺序不同但都成功(self):
        """工具集合一致，顺序不同"""
        r = review_case(_make_case(
            passed=False,
            tool_calls=[
                {"tool_name": "knowledge", "success": True},
                {"tool_name": "calculator", "success": True},
            ],
            assertions=[
                {"name": "工具序列检查", "passed": False,
                 "reason": "预期: ['calculator', 'knowledge']，实际: ['knowledge', 'calculator']"},
            ],
            final_answer="计算结果和知识解释...",
        ))
        assert r["original_passed"] is False
        assert r["suggested_status"] in ("likely_equivalent", "needs_review")


class TestSummarizeReviews:
    """批量统计"""

    def test_混合结果统计(self):
        cases = [
            _make_case("A", passed=True),
            _make_case("B", passed=False,
                       tool_calls=[{"tool_name": "knowledge", "success": True},
                                   {"tool_name": "knowledge", "success": True}],
                       assertions=[{"name": "工具序列检查", "passed": False}],
                       final_answer="test"),
            _make_case("C", passed=False,
                       assertions=[{"name": "安全-禁止内容检查", "passed": False}],
                       final_answer="leaked"),
        ]
        counts = summarize_reviews(cases)
        assert counts["already_passed"] == 1
        assert counts["likely_equivalent"] == 1
        assert counts["true_failure"] == 1
