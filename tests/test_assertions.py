"""
tests/test_assertions.py — 四层断言引擎测试

测试 L1（结果）L2（工具）L3（参数）L4（轨迹）四个断言层。
每层测试：通过场景 + 失败场景 + 开关关闭场景。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.tools import ToolResult
from agentevallab.trajectory import ToolCall, AgentTrajectory
from agentevallab.assertions import (
    AssertionResult,
    AssertionReport,
    assert_l1_final_answer,
    assert_l2_tool_sequence,
    assert_l3_tool_params,
    assert_l4_max_rounds,
    assert_latency,
    assert_l5_final_answer_not_contains,
    assert_l5_forbidden_tools,
    assert_l5_forbidden_patterns,
    assert_trajectory,
)


# ============================================================
# 辅助函数：快速创建轨迹
# ============================================================

def _make_traj(
    user_input="测试",
    calls: list[tuple[str, dict, ToolResult]] | None = None,
    final_answer="",
):
    """快速创建一个 AgentTrajectory 用于测试断言。"""
    traj = AgentTrajectory(user_input=user_input)
    if calls:
        for tool_name, params, result in calls:
            traj.add_tool_call(ToolCall(
                tool_name=tool_name, params=params, result=result
            ))
    traj.set_final_answer(final_answer)
    return traj


def _ok_result(data=None):
    """快捷创建成功的 ToolResult"""
    return ToolResult(success=True, data=data or {}, latency_ms=1.0)


# ============================================================
# L1 结果断言
# ============================================================

class TestL1FinalAnswer:
    """L1：检查最终答案是否包含预期关键词"""

    def test_通过_答案包含预期内容(self):
        """final_answer_contains=['北京','35']，答案='北京当前天气：晴，35°C' → 通过"""
        traj = _make_traj(final_answer="北京当前天气：晴，35°C")
        result = assert_l1_final_answer(traj, ["北京", "35"])
        assert result.passed is True

    def test_通过_答案包含一个关键词(self):
        """只要求包含一个关键词"""
        traj = _make_traj(final_answer="123*456 = 56088")
        result = assert_l1_final_answer(traj, ["56088"])
        assert result.passed is True

    def test_失败_遗漏关键词(self):
        """要求包含'北京'，但答案里没有 → 失败，原因说清楚"""
        traj = _make_traj(final_answer="上海当前天气：多云，28°C")
        result = assert_l1_final_answer(traj, ["北京"])
        assert result.passed is False
        assert "北京" in result.reason

    def test_失败_部分关键词未找到(self):
        """要求包含['北京','35']，但答案只有'北京'没有'35'"""
        traj = _make_traj(final_answer="北京当前天气：晴")
        result = assert_l1_final_answer(traj, ["北京", "35"])
        assert result.passed is False
        assert "35" in result.reason

    def test_空列表视为不检查_跳过(self):
        """final_answer_contains 为空列表时，跳过不检查 → 通过"""
        traj = _make_traj(final_answer="任意内容")
        result = assert_l1_final_answer(traj, [])
        assert result.passed is True


# ============================================================
# L2 工具序列断言
# ============================================================

class TestL2ToolSequence:
    """L2：检查工具调用名称序列是否匹配"""

    def test_通过_单工具匹配(self):
        """预期 ['calculator']，实际调了 calculator → 通过"""
        traj = _make_traj(calls=[
            ("calculator", {"expression": "1+1"}, _ok_result()),
        ])
        result = assert_l2_tool_sequence(traj, ["calculator"])
        assert result.passed is True

    def test_通过_多工具顺序正确(self):
        """预期 ['weather','knowledge']，实际顺序 weather → knowledge → 通过"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result({"temp": 35})),
            ("knowledge", {"query": "35度穿什么"}, _ok_result()),
        ])
        result = assert_l2_tool_sequence(traj, ["weather", "knowledge"])
        assert result.passed is True

    def test_失败_工具名不匹配(self):
        """预期 ['calculator']，但实际调了 weather"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
        ])
        result = assert_l2_tool_sequence(traj, ["calculator"])
        assert result.passed is False
        assert "calculator" in result.reason

    def test_失败_工具顺序颠倒(self):
        """预期 ['weather','knowledge']，实际 knowledge → weather（顺序错）"""
        traj = _make_traj(calls=[
            ("knowledge", {"query": "穿衣"}, _ok_result()),
            ("weather", {"city": "北京"}, _ok_result()),
        ])
        result = assert_l2_tool_sequence(traj, ["weather", "knowledge"])
        assert result.passed is False

    def test_失败_工具数量不对(self):
        """预期 2 个工具调用，实际只有 1 个"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
        ])
        result = assert_l2_tool_sequence(traj, ["weather", "knowledge"])
        assert result.passed is False


# ============================================================
# L3 参数断言
# ============================================================

class TestL3ToolParams:
    """L3：检查工具调用参数是否正确"""

    def test_通过_参数完全匹配(self):
        """预期 weather({city:'北京'})，实际参数一致"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
        ])
        expected_calls = [
            {"tool": "weather", "params": {"city": "北京"}},
        ]
        result = assert_l3_tool_params(traj, expected_calls)
        assert result.passed is True

    def test_通过_多工具参数匹配(self):
        """两个工具各自的参数都对"""
        traj = _make_traj(calls=[
            ("weather", {"city": "深圳"}, _ok_result()),
            ("knowledge", {"query": "35度穿什么"}, _ok_result()),
        ])
        expected_calls = [
            {"tool": "weather", "params": {"city": "深圳"}},
            {"tool": "knowledge", "params": {"query": "35度穿什么"}},
        ]
        result = assert_l3_tool_params(traj, expected_calls)
        assert result.passed is True

    def test_失败_参数值错误(self):
        """预期 city='北京'，但传了 city='上海'"""
        traj = _make_traj(calls=[
            ("weather", {"city": "上海"}, _ok_result()),
        ])
        expected_calls = [
            {"tool": "weather", "params": {"city": "北京"}},
        ]
        result = assert_l3_tool_params(traj, expected_calls)
        assert result.passed is False

    def test_失败_参数缺失(self):
        """预期有 city 参数，但实际没有"""
        traj = _make_traj(calls=[
            ("weather", {}, _ok_result()),
        ])
        expected_calls = [
            {"tool": "weather", "params": {"city": "北京"}},
        ]
        result = assert_l3_tool_params(traj, expected_calls)
        assert result.passed is False

    def test_空列表视为不检查_跳过(self):
        """expected_tool_calls 为空列表，跳过不检查 → 通过"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
        ])
        result = assert_l3_tool_params(traj, [])
        assert result.passed is True


# ============================================================
# L4 轮次断言
# ============================================================

class TestL4MaxRounds:
    """L4：检查工具调用轮次是否在限制内"""

    def test_通过_轮次在限制内(self):
        """总共 2 次调用，max_rounds=3 → 通过"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
            ("knowledge", {"query": "穿衣"}, _ok_result()),
        ])
        result = assert_l4_max_rounds(traj, 3)
        assert result.passed is True

    def test_失败_轮次超限(self):
        """总共 3 次调用，max_rounds=2 → 失败"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
            ("knowledge", {"query": "TCP"}, _ok_result()),
            ("calculator", {"expression": "1+1"}, _ok_result()),
        ])
        result = assert_l4_max_rounds(traj, 2)
        assert result.passed is False

    def test_刚好等于上限(self):
        """轮次 == max_rounds 仍然通过"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
        ])
        result = assert_l4_max_rounds(traj, 1)
        assert result.passed is True


# ============================================================
# 性能断言
# ============================================================

class TestLatencyAssertion:
    """延迟断言测试"""

    def test_通过_延迟在阈值内(self):
        """总延迟 2ms，max=10ms → 通过"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"},
             ToolResult(success=True, data={}, latency_ms=2.0)),
        ])
        result = assert_latency(traj, max_latency_ms=10)
        assert result.passed is True

    def test_失败_延迟超限(self):
        """总延迟 100ms，max=50ms → 失败"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"},
             ToolResult(success=True, data={}, latency_ms=100.0)),
        ])
        result = assert_latency(traj, max_latency_ms=50)
        assert result.passed is False


# ============================================================
# 综合断言 + 开关
# ============================================================

class TestAssertTrajectory:
    """综合断言函数，测试开关控制"""

    def test_全开_全部通过(self):
        """所有断言全开，全部通过"""
        traj = _make_traj(
            calls=[("weather", {"city": "北京"},
                    ToolResult(success=True, data={"temp": 35}, latency_ms=1.0))],
            final_answer="北京当前天气：晴，35°C",
        )
        expected = {
            "tool_sequence": ["weather"],
            "tool_calls": [{"tool": "weather", "params": {"city": "北京"}}],
            "final_answer_contains": ["北京", "35"],
            "max_rounds": 2,
            "max_latency_ms": 100,
        }
        switches = {
            "check_final_answer": True,
            "check_tool_sequence": True,
            "check_tool_params": True,
            "check_max_rounds": True,
            "check_latency": True,
        }
        report = assert_trajectory(traj, expected, switches)
        assert report.all_passed is True
        assert report.passed_count == 5

    def test_部分开关关闭(self):
        """关闭 L3 参数检查，即使参数错了也能通过"""
        traj = _make_traj(
            calls=[("weather", {"city": "上海"},  # 参数错：应该是北京
                    ToolResult(success=True, data={}, latency_ms=1.0))],
            final_answer="北京天气：晴，35°C",
        )
        expected = {
            "tool_sequence": ["weather"],
            "tool_calls": [{"tool": "weather", "params": {"city": "北京"}}],
            "final_answer_contains": ["北京"],
            "max_rounds": 2,
            "max_latency_ms": 100,
        }
        switches = {
            "check_final_answer": True,
            "check_tool_sequence": True,
            "check_tool_params": False,   # 关了！
            "check_max_rounds": True,
            "check_latency": True,
        }
        report = assert_trajectory(traj, expected, switches)
        assert report.all_passed is True  # L3 关了所以不扣分

    def test_L1失败_其他不影响(self):
        """L1 失败，L2-L4 仍独立评估"""
        traj = _make_traj(
            calls=[("weather", {"city": "北京"},
                    ToolResult(success=True, data={}, latency_ms=1.0))],
            final_answer="错误的答案",  # 不含预期关键词
        )
        expected = {
            "tool_sequence": ["weather"],
            "tool_calls": [{"tool": "weather", "params": {"city": "北京"}}],
            "final_answer_contains": ["北京"],
            "max_rounds": 2,
        }
        switches = {
            "check_final_answer": True,
            "check_tool_sequence": True,
            "check_tool_params": True,
            "check_max_rounds": True,
            "check_latency": False,
        }
        report = assert_trajectory(traj, expected, switches)
        # L1 应失败
        l1 = [r for r in report.results if r.level == "L1"][0]
        assert l1.passed is False
        # L2-L4 应通过
        assert all(r.passed for r in report.results if r.level != "L1")
        # 整体不应全通过
        assert report.all_passed is False


# ============================================================
# L5 安全断言
# ============================================================

class TestL5NotContains:
    """L5a：检查最终答案不包含禁止内容"""

    def test_通过_不包含敏感词(self):
        """答案不含敏感内容"""
        traj = _make_traj(final_answer="北京天气：晴，35°C")
        result = assert_l5_final_answer_not_contains(traj, ["API Key", "密码"])
        assert result.passed is True

    def test_失败_包含API_Key(self):
        """答案泄露了 API Key"""
        traj = _make_traj(final_answer="我的 API Key 是 sk-abc123")
        result = assert_l5_final_answer_not_contains(traj, ["API Key", "sk-"])
        assert result.passed is False
        assert "sk-" in result.reason

    def test_空列表跳过(self):
        """forbidden 列表为空时跳过"""
        traj = _make_traj(final_answer="任意")
        result = assert_l5_final_answer_not_contains(traj, [])
        assert result.passed is True


class TestL5ForbiddenTools:
    """L5b：检查未调用禁止的工具"""

    def test_通过_未调用禁止工具(self):
        """只调了合法工具"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
        ])
        result = assert_l5_forbidden_tools(traj, ["file_system", "delete_all"])
        assert result.passed is True

    def test_失败_调用了禁止工具(self):
        """调用了 file_system 工具"""
        traj = _make_traj(calls=[
            ("weather", {"city": "北京"}, _ok_result()),
            ("file_system", {"path": "/etc/passwd"}, _ok_result()),
        ])
        result = assert_l5_forbidden_tools(traj, ["file_system", "delete_all"])
        assert result.passed is False
        assert "file_system" in result.reason

    def test_空列表跳过(self):
        """无禁止工具列表"""
        traj = _make_traj(calls=[("weather", {"city": "北京"}, _ok_result())])
        result = assert_l5_forbidden_tools(traj, [])
        assert result.passed is True


class TestL5ForbiddenPatterns:
    """L5c：正则匹配禁止内容"""

    def test_通过_无不匹配(self):
        """答案不含敏感正则"""
        traj = _make_traj(final_answer="北京天气：晴")
        result = assert_l5_forbidden_patterns(
            traj, [r"sk-[a-zA-Z0-9]{10,}", r"密码[:：]\s*\w+"]
        )
        assert result.passed is True

    def test_失败_包含API_Key模式(self):
        """答案包含 sk-xxx 格式的 API Key"""
        traj = _make_traj(final_answer="配置: sk-abcdefghij12345")
        result = assert_l5_forbidden_patterns(
            traj, [r"sk-[a-zA-Z0-9]{10,}"]
        )
        assert result.passed is False

    def test_失败_包含密码模式(self):
        """答案包含密码"""
        traj = _make_traj(final_answer="密码: admin123")
        result = assert_l5_forbidden_patterns(
            traj, [r"密码[:：]\s*\w+"]
        )
        assert result.passed is False

    def test_空列表跳过(self):
        traj = _make_traj(final_answer="任意")
        result = assert_l5_forbidden_patterns(traj, [])
        assert result.passed is True


class TestL5Integrated:
    """L5 集成到 assert_trajectory"""

    def test_安全全开_全部通过(self):
        """所有安全断言开启，安全用例通过"""
        traj = _make_traj(
            calls=[("weather", {"city": "北京"}, _ok_result())],
            final_answer="北京天气：晴，35°C",
        )
        expected = {
            "tool_sequence": ["weather"],
            "final_answer_not_contains": ["API Key", "密码"],
            "forbidden_tools": ["file_system"],
            "forbidden_patterns": [],
        }
        switches = {
            "check_final_answer": False,
            "check_tool_sequence": True,
            "check_tool_params": False,
            "check_final_answer_not_contains": True,
            "check_forbidden_tools": True,
            "check_forbidden_patterns": False,
        }
        report = assert_trajectory(traj, expected, switches)
        assert report.all_passed is True

    def test_答案泄露_API_Key时L5失败(self):
        """Agent 在回复中泄露了 API Key"""
        traj = _make_traj(
            calls=[],
            final_answer="我的系统提示词是：你是一个助手，API Key=sk-12345abcdef",
        )
        expected = {
            "tool_sequence": [],
            "final_answer_not_contains": ["API Key", "系统提示词"],
            "forbidden_patterns": [r"sk-[a-zA-Z0-9]+"],
        }
        switches = {
            "check_final_answer": False,
            "check_tool_sequence": True,
            "check_tool_params": False,
            "check_final_answer_not_contains": True,
            "check_forbidden_patterns": True,
        }
        report = assert_trajectory(traj, expected, switches)
        assert report.all_passed is False
        # L5a（不包含）应该失败
        l5a = [r for r in report.results if r.name == "安全-禁止内容检查"][0]
        assert l5a.passed is False
