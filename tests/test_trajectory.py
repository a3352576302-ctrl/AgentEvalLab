"""
tests/test_trajectory.py — 轨迹数据结构测试

测试 ToolCall 和 AgentTrajectory 的创建、记录和查询功能。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.tools import ToolResult
from agentevallab.trajectory import ToolCall, AgentTrajectory


class TestToolCall:
    """ToolCall — 单次工具调用记录"""

    def test_创建成功的工具调用记录(self):
        """正常工具调用：记录工具名、参数、返回结果和耗时"""
        call = ToolCall(
            tool_name="calculator",
            params={"expression": "123*456"},
            result=ToolResult(success=True, data={"result": 56088}, latency_ms=0.5),
        )
        assert call.tool_name == "calculator"
        assert call.params == {"expression": "123*456"}
        assert call.result.success is True
        assert call.result.data["result"] == 56088
        assert call.latency_ms == 0.5

    def test_创建失败的工具调用记录(self):
        """失败的工具调用也应被正常记录"""
        call = ToolCall(
            tool_name="weather",
            params={"city": "火星"},
            result=ToolResult(success=False, error="未找到城市", latency_ms=0.3),
        )
        assert call.tool_name == "weather"
        assert call.result.success is False
        assert "未找到城市" in call.result.error

    def test_耗时默认值(self):
        """不传 latency_ms 时默认取 result.latency_ms"""
        call = ToolCall(
            tool_name="knowledge",
            params={"query": "TCP"},
            result=ToolResult(success=True, data={"answer": "..."}, latency_ms=2.0),
        )
        assert call.latency_ms == 2.0

    def test_to_dict方法(self):
        """to_dict() 将工具调用转为可序列化的字典"""
        call = ToolCall(
            tool_name="weather",
            params={"city": "北京"},
            result=ToolResult(success=True, data={"temp": 35}, latency_ms=1.0),
        )
        d = call.to_dict()
        assert d["tool_name"] == "weather"
        assert d["params"] == {"city": "北京"}
        assert d["success"] is True
        assert d["data"] == {"temp": 35}
        assert d["latency_ms"] == 1.0


class TestAgentTrajectory:
    """AgentTrajectory — 一次 Agent 运行的完整轨迹"""

    def test_创建空轨迹(self):
        """空轨迹：还没有任何工具调用"""
        traj = AgentTrajectory(user_input="北京天气怎么样？")
        assert traj.user_input == "北京天气怎么样？"
        assert traj.tool_calls == []
        assert traj.final_answer == ""
        assert traj.total_rounds == 0

    def test_添加工具调用(self):
        """add_tool_call() 向轨迹中添加一次工具调用"""
        traj = AgentTrajectory(user_input="123*456")
        call = ToolCall(
            tool_name="calculator",
            params={"expression": "123*456"},
            result=ToolResult(success=True, data={"result": 56088}, latency_ms=1.2),
        )
        traj.add_tool_call(call)
        assert len(traj.tool_calls) == 1
        assert traj.total_rounds == 1
        assert traj.tool_calls[0].tool_name == "calculator"

    def test_设置最终答案(self):
        """set_final_answer() 记录 Agent 的最终输出"""
        traj = AgentTrajectory(user_input="TCP三次握手是什么？")
        call = ToolCall(
            tool_name="knowledge",
            params={"query": "TCP三次握手"},
            result=ToolResult(success=True, data={"answer": "SYN..."}, latency_ms=0.8),
        )
        traj.add_tool_call(call)
        traj.set_final_answer("TCP 三次握手是指 SYN、SYN-ACK、ACK 三次报文交换。")
        assert "SYN" in traj.final_answer

    def test_总延迟计算(self):
        """total_latency_ms 应为所有工具调用延迟之和"""
        traj = AgentTrajectory(user_input="多工具任务")
        traj.add_tool_call(ToolCall(
            tool_name="weather",
            params={"city": "北京"},
            result=ToolResult(success=True, data={"temp": 35}, latency_ms=1.5),
        ))
        traj.add_tool_call(ToolCall(
            tool_name="knowledge",
            params={"query": "35度穿什么"},
            result=ToolResult(success=True, data={"answer": "..."}, latency_ms=0.8),
        ))
        assert traj.total_latency_ms == 2.3  # 1.5 + 0.8

    def test_工具名称列表(self):
        """tool_names 属性返回工具调用顺序列表"""
        traj = AgentTrajectory(user_input="多工具任务")
        traj.add_tool_call(ToolCall(
            tool_name="weather",
            params={"city": "北京"},
            result=ToolResult(success=True, data={}, latency_ms=1.0),
        ))
        traj.add_tool_call(ToolCall(
            tool_name="knowledge",
            params={"query": "穿衣"},
            result=ToolResult(success=True, data={}, latency_ms=1.0),
        ))
        assert traj.tool_names == ["weather", "knowledge"]

    def test_是否成功属性(self):
        """all_tools_succeeded 在所有工具成功时返回 True"""
        # 全部成功
        traj = AgentTrajectory(user_input="任务")
        traj.add_tool_call(ToolCall(
            tool_name="weather", params={"city": "北京"},
            result=ToolResult(success=True, data={}, latency_ms=1.0),
        ))
        assert traj.all_tools_succeeded is True

        # 有一个失败
        traj.add_tool_call(ToolCall(
            tool_name="weather", params={"city": "火星"},
            result=ToolResult(success=False, error="未找到", latency_ms=0.5),
        ))
        assert traj.all_tools_succeeded is False
