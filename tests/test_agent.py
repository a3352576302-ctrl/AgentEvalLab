"""
tests/test_agent.py — RuleBasedAgent 测试

测试 Agent 的意图识别、工具调用和轨迹返回。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.agent import RuleBasedAgent, AgentProtocol
from agentevallab.trajectory import AgentTrajectory


# ============================================================
# 每个测试共用的 Agent 实例
# ============================================================

@pytest.fixture
def agent():
    """创建一个 RuleBasedAgent 实例"""
    return RuleBasedAgent()


# ============================================================
# AgentProtocol 接口测试
# ============================================================

class TestAgentProtocol:
    """验证 RuleBasedAgent 符合 AgentProtocol 接口"""

    def test_是AgentProtocol的子类(self):
        """RuleBasedAgent 应继承 AgentProtocol"""
        assert issubclass(RuleBasedAgent, AgentProtocol) is True

    def test_run方法返回AgentTrajectory(self, agent):
        """run() 必须返回 AgentTrajectory 实例"""
        traj = agent.run("北京天气怎么样？")
        assert isinstance(traj, AgentTrajectory)

    def test_trajectory包含用户输入(self, agent):
        """轨迹中的 user_input 应与传入一致"""
        traj = agent.run("TCP三次握手的过程是什么？")
        assert traj.user_input == "TCP三次握手的过程是什么？"


# ============================================================
# 单工具调用测试
# ============================================================

class TestCalculatorIntent:
    """计算器意图识别"""

    def test_乘法(self, agent):
        """'123*456 等于多少？' → 调 calculator，返回 56088"""
        traj = agent.run("123*456 等于多少？")
        assert traj.tool_names == ["calculator"]
        assert traj.all_tools_succeeded is True
        assert "56088" in traj.final_answer

    def test_加法(self, agent):
        """'1+2+3 等于多少？' → 调 calculator"""
        traj = agent.run("1+2+3 等于多少？")
        assert traj.tool_names == ["calculator"]
        assert "6" in traj.final_answer

    def test_带中文字的描述(self, agent):
        """'帮我算一下 100 / 4' → 仍应识别为计算意图"""
        traj = agent.run("帮我算一下 100 / 4 等于多少")
        assert traj.tool_names == ["calculator"]
        assert "25" in traj.final_answer


class TestWeatherIntent:
    """天气查询意图识别"""

    def test_北京天气(self, agent):
        """'北京今天天气怎么样？' → 调 weather('北京')"""
        traj = agent.run("北京今天天气怎么样？")
        assert traj.tool_names == ["weather"]
        assert traj.all_tools_succeeded is True
        assert "北京" in traj.final_answer

    def test_上海天气(self, agent):
        """'上海多少度？' → 调 weather('上海')"""
        traj = agent.run("上海今天多少度？")
        assert traj.tool_names == ["weather"]

    def test_不存在的城市(self, agent):
        """'火星天气' → weather 调用失败，但 Agent 不应崩溃"""
        traj = agent.run("火星今天天气怎么样？")
        assert traj.tool_names == ["weather"]
        assert traj.all_tools_succeeded is False
        # Agent 应优雅处理失败，给出提示
        assert len(traj.final_answer) > 0


class TestKnowledgeIntent:
    """知识库查询意图识别"""

    def test_TCP查询(self, agent):
        """'TCP三次握手的过程是怎样的？' → 调 knowledge"""
        traj = agent.run("TCP三次握手的过程是怎样的？")
        assert traj.tool_names == ["knowledge"]
        assert traj.all_tools_succeeded is True
        assert "SYN" in traj.final_answer

    def test_RAG查询(self, agent):
        """'什么是RAG？' → 调 knowledge"""
        traj = agent.run("什么是RAG？")
        assert traj.tool_names == ["knowledge"]


# ============================================================
# 多工具串联测试（核心亮点）
# ============================================================

class TestMultiTool:
    """多工具串联场景"""

    def test_天气加穿搭(self, agent):
        """'北京今天多少度？35度穿什么衣服合适？'
        → weather('北京') → knowledge('35度穿什么')
        → 两条工具调用，顺序正确
        """
        traj = agent.run("北京今天多少度？35度穿什么衣服合适？")
        assert traj.tool_names == ["weather", "knowledge"]
        assert traj.total_rounds == 2
        assert traj.all_tools_succeeded is True
        # 最终答案应同时包含天气和穿搭信息
        assert len(traj.final_answer) > 0

    def test_多工具轨迹顺序正确(self, agent):
        """验证 weather 必须在 knowledge 之前调用"""
        traj = agent.run("深圳今天多少度？35度穿什么合适？")
        # 必须先查天气，再根据结果查穿搭
        assert traj.tool_names[0] == "weather"
        assert traj.tool_names[1] == "knowledge"


# ============================================================
# 无法识别意图
# ============================================================

class TestUnknownIntent:
    """无法识别的输入"""

    def test_无意义输入不崩溃(self, agent):
        """'哈哈哈哈哈' → 不调任何工具，不崩溃，给友好提示"""
        traj = agent.run("哈哈哈哈哈")
        assert traj.total_rounds == 0
        assert len(traj.final_answer) > 0  # 有回复，不是空白

    def test_空字符串不崩溃(self, agent):
        """空字符串 → 不崩溃"""
        traj = agent.run("")
        assert traj.total_rounds == 0
