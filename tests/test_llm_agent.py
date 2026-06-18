"""
tests/test_llm_agent.py — LLMAgent 测试（使用标准库 mock）

不调用真实 API，用 mock 验证 Agent 循环逻辑。
"""
import sys
import os
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.llm_agent import LLMAgent, _build_tools_schema
from agentevallab.trajectory import AgentTrajectory
from agentevallab.agent import AgentProtocol


class TestLLMAgentInterface:
    """LLMAgent 接口测试（无需 API Key 和 openai）"""

    def test_实现AgentProtocol(self):
        agent = LLMAgent(api_key="")
        assert isinstance(agent, AgentProtocol)

    def test_无API_Key时降级不崩溃(self):
        agent = LLMAgent(api_key="")
        traj = agent.run("北京天气怎么样？")
        assert isinstance(traj, AgentTrajectory)
        assert "API Key" in traj.final_answer

    def test_环境变量读取(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-env")
        agent = LLMAgent()
        assert agent.api_key == "sk-test-env"

    def test_环境变量优先级(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        agent = LLMAgent()
        assert agent.api_key == "sk-minimax"

    def test_显式deepseek_provider不误用minimax_key(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-deepseek")
        agent = LLMAgent(provider="deepseek", model="deepseek-chat")
        assert agent.provider == "deepseek"
        assert agent.api_key == "sk-deepseek"
        assert agent.base_url == "https://api.deepseek.com/v1"

    def test_base_url自动推断deepseek_provider(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-deepseek")
        agent = LLMAgent(
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
        )
        assert agent.provider == "deepseek"
        assert agent.api_key == "sk-deepseek"

    def test_显式minimax_provider读取minimax_key(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-deepseek")
        agent = LLMAgent(provider="minimax", model="minimax-m2")
        assert agent.provider == "minimax"
        assert agent.api_key == "sk-minimax"

    def test_max_rounds可配置(self):
        agent = LLMAgent(api_key="", max_rounds=5)
        assert agent.max_rounds == 5


class TestToolsSchema:
    """工具描述转 Function Calling 格式"""

    def test_生成schema包含三个工具(self):
        schema = _build_tools_schema()
        tool_names = [t["function"]["name"] for t in schema]
        assert "calculator" in tool_names
        assert "weather" in tool_names
        assert "knowledge" in tool_names

    def test_每个工具有description(self):
        schema = _build_tools_schema()
        for t in schema:
            assert len(t["function"]["description"]) > 0

    def test_每个工具有parameters(self):
        schema = _build_tools_schema()
        for t in schema:
            params = t["function"]["parameters"]
            assert params["type"] == "object"


class TestLLMAgentWithMock:
    """用 mock 验证 LLMAgent 的工具调用循环"""

    @pytest.fixture
    def agent_with_key(self):
        return LLMAgent(api_key="sk-mock", model="mock-model")

    def test_模型返回文本不调工具(self, agent_with_key):
        """模型直接回答，不调任何工具"""
        mock_msg = MagicMock()
        mock_msg.content = "今天北京天气晴朗，35°C。"
        mock_msg.tool_calls = None
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch(
            "openai.resources.chat.completions.Completions.create",
            return_value=mock_response,
        ):
            traj = agent_with_key.run("北京天气怎么样？")

        assert traj.total_rounds == 0
        assert "35°C" in traj.final_answer

    def test_模型调用单个工具(self, agent_with_key):
        """模型调用 weather 工具一次，然后返回最终答案"""
        tool_msg = MagicMock()
        tool_msg.content = None
        tool_call = MagicMock()
        tool_call.id = "call_001"
        tool_call.function.name = "weather"
        tool_call.function.arguments = '{"city": "北京"}'
        tool_msg.tool_calls = [tool_call]

        final_msg = MagicMock()
        final_msg.content = "北京今天晴，35°C。"
        final_msg.tool_calls = None

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=[
                MagicMock(choices=[MagicMock(message=tool_msg)]),
                MagicMock(choices=[MagicMock(message=final_msg)]),
            ],
        ):
            traj = agent_with_key.run("北京天气怎么样？")

        assert traj.total_rounds == 1
        assert traj.tool_names == ["weather"]
        assert "35°C" in traj.final_answer

    def test_API异常时降级不崩溃(self, agent_with_key):
        """API 调用失败时给出错误提示"""
        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=Exception("Connection refused"),
        ):
            traj = agent_with_key.run("北京天气怎么样？")

        assert "失败" in traj.final_answer

    def test_消息顺序正确_assistant先于tool(self, agent_with_key):
        """验证发送给 LLM 的消息顺序：assistant(tool_calls) → tool(result)"""
        tool_msg = MagicMock()
        tool_msg.content = None
        tool_call = MagicMock()
        tool_call.id = "call_001"
        tool_call.function.name = "weather"
        tool_call.function.arguments = '{"city": "北京"}'
        tool_msg.tool_calls = [tool_call]

        final_msg = MagicMock()
        final_msg.content = "北京今天晴，35°C。"
        final_msg.tool_calls = None

        captured_calls = []

        def capture_create(*args, **kwargs):
            captured_calls.append(dict(kwargs))
            if len(captured_calls) == 1:
                return MagicMock(choices=[MagicMock(message=tool_msg)])
            return MagicMock(choices=[MagicMock(message=final_msg)])

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=capture_create,
        ):
            agent_with_key.run("北京天气怎么样？")

        # 第二轮调用应包含 assistant(tool_calls) 和 tool(result)
        assert len(captured_calls) >= 2, f"应至少有2次API调用，实际{len(captured_calls)}次"
        second_messages = captured_calls[1].get("messages", [])

        # 提取角色：dict 用 .get("role")，MagicMock 用 .role 属性
        roles = []
        for m in second_messages:
            if isinstance(m, dict):
                roles.append(m.get("role", ""))
            else:
                # MagicMock — assistant 消息对象
                roles.append(getattr(m, "role", str(type(m).__name__)))

        # 验证消息中有 tool 角色（说明 assistant 在它之前被追加）
        assert "tool" in roles, f"第二轮消息应包含 tool，实际 roles={roles}"
        # 验证 assistant 消息（MagicMock 对象）在 tool 之前
        tool_idx = roles.index("tool")
        has_non_dict_before_tool = any(
            not isinstance(second_messages[i], dict)
            for i in range(tool_idx)
        )
        assert has_non_dict_before_tool, (
            f"消息顺序错误: tool 之前应有 assistant 消息，roles={roles}"
        )
