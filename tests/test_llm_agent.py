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


class TestLLMAgentRetry:
    """LLMAgent retry 行为测试"""

    @pytest.fixture
    def agent_with_retry(self):
        return LLMAgent(api_key="sk-mock", model="mock-model", max_retries=2)

    def test_429限流时重试(self, agent_with_retry):
        """429 应触发重试"""
        call_count = [0]

        def create_side_effect(*args, **kwargs):
            call_count[0] += 1
            raise Exception("429 Too Many Requests - rate limit exceeded")

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=create_side_effect,
        ), patch("time.sleep", return_value=None):  # 跳过 sleep
            traj = agent_with_retry.run("测试")

        # max_retries=2 → 1原始 + 2重试 = 3次
        assert call_count[0] == 3
        assert "LLM 调用失败" in traj.final_answer

    def test_500服务端错误时重试(self, agent_with_retry):
        """500 应触发重试"""
        call_count = [0]

        def create_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("500 Internal Server Error")
            # 第二次成功
            msg = MagicMock()
            msg.content = "北京今天晴，35°C。"
            msg.tool_calls = None
            return MagicMock(choices=[MagicMock(message=msg)])

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=create_side_effect,
        ), patch("time.sleep", return_value=None):
            traj = agent_with_retry.run("北京天气怎么样？")

        assert "35°C" in traj.final_answer

    def test_401不重试(self, agent_with_retry):
        """401 认证错误不应重试"""
        call_count = [0]

        def create_side_effect(*args, **kwargs):
            call_count[0] += 1
            raise Exception("401 Unauthorized - invalid_api_key")

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=create_side_effect,
        ), patch("time.sleep", return_value=None):
            traj = agent_with_retry.run("测试")

        # 不应重试，只调1次
        assert call_count[0] == 1
        assert "LLM 调用失败" in traj.final_answer

    def test_400不重试(self, agent_with_retry):
        """400 请求错误不应重试"""
        call_count = [0]

        def create_side_effect(*args, **kwargs):
            call_count[0] += 1
            raise Exception("400 Bad Request")

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=create_side_effect,
        ), patch("time.sleep", return_value=None):
            traj = agent_with_retry.run("测试")

        assert call_count[0] == 1

    def test_402余额不足不重试(self, agent_with_retry):
        """402 余额不足不应重试"""
        call_count = [0]

        def create_side_effect(*args, **kwargs):
            call_count[0] += 1
            raise Exception("402 insufficient_balance_error")

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=create_side_effect,
        ), patch("time.sleep", return_value=None):
            traj = agent_with_retry.run("测试")

        assert call_count[0] == 1

    def test_timeout时重试(self, agent_with_retry):
        """Timeout 应触发重试"""
        call_count = [0]

        def create_side_effect(*args, **kwargs):
            call_count[0] += 1
            raise Exception("Connection timed out")

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=create_side_effect,
        ), patch("time.sleep", return_value=None):
            traj = agent_with_retry.run("测试")

        assert call_count[0] == 3  # max_retries=2

    def test_max_retries为0时不重试(self):
        """max_retries=0 → 不重试"""
        agent = LLMAgent(api_key="sk-mock", model="mock-model", max_retries=0)
        call_count = [0]

        def create_side_effect(*args, **kwargs):
            call_count[0] += 1
            raise Exception("500 server error")

        with patch(
            "openai.resources.chat.completions.Completions.create",
            side_effect=create_side_effect,
        ), patch("time.sleep", return_value=None):
            traj = agent.run("测试")

        assert call_count[0] == 1


class TestLLMAgentDedup:
    """v1.1 Stage 2: 工具调用去重测试"""

    @pytest.fixture
    def agent(self):
        return LLMAgent(api_key="sk-mock", model="mock-model")

    def test_相同tool_params被去重(self, agent):
        """同一 tool+args 第二次调用返回 cached"""
        msg1 = MagicMock(); msg1.content = None
        tc1 = MagicMock(); tc1.id = "c1"; tc1.function.name = "weather"
        tc1.function.arguments = '{"city": "北京"}'; msg1.tool_calls = [tc1]
        msg2 = MagicMock(); msg2.content = None
        tc2 = MagicMock(); tc2.id = "c2"; tc2.function.name = "weather"
        tc2.function.arguments = '{"city": "北京"}'; msg2.tool_calls = [tc2]
        fmsg = MagicMock(); fmsg.content = "北京35度。"; fmsg.tool_calls = None
        cnt = [0]
        def side(*a, **kw):
            cnt[0] += 1
            if cnt[0] == 1: return MagicMock(choices=[MagicMock(message=msg1)])
            if cnt[0] == 2: return MagicMock(choices=[MagicMock(message=msg2)])
            return MagicMock(choices=[MagicMock(message=fmsg)])
        with patch("openai.resources.chat.completions.Completions.create", side_effect=side):
            traj = agent.run("北京天气怎么样？")
        assert traj.total_rounds == 2
        assert traj.tool_calls[1].result.data.get("deduped") is True
        assert "35度" in traj.final_answer

    def test_不同knowledge查询不被误去重(self, agent):
        """不同 query 的 knowledge 调用仍分别执行"""
        msg1 = MagicMock(); msg1.content = None
        tc1 = MagicMock(); tc1.id = "c1"; tc1.function.name = "knowledge"
        tc1.function.arguments = '{"query": "TCP三次握手"}'; msg1.tool_calls = [tc1]
        msg2 = MagicMock(); msg2.content = None
        tc2 = MagicMock(); tc2.id = "c2"; tc2.function.name = "knowledge"
        tc2.function.arguments = '{"query": "什么是RAG"}'; msg2.tool_calls = [tc2]
        fmsg = MagicMock(); fmsg.content = "TCP和RAG。"; fmsg.tool_calls = None
        cnt = [0]
        def side(*a, **kw):
            cnt[0] += 1
            if cnt[0] == 1: return MagicMock(choices=[MagicMock(message=msg1)])
            if cnt[0] == 2: return MagicMock(choices=[MagicMock(message=msg2)])
            return MagicMock(choices=[MagicMock(message=fmsg)])
        with patch("openai.resources.chat.completions.Completions.create", side_effect=side):
            traj = agent.run("TCP和RAG是什么？")
        assert traj.total_rounds == 2
        assert traj.tool_calls[1].result.data.get("deduped") is None

    def test_deduped保留原始数据(self, agent):
        """去重调用复用首次的真实 ToolResult"""
        msg1 = MagicMock(); msg1.content = None
        tc1 = MagicMock(); tc1.id = "c1"; tc1.function.name = "weather"
        tc1.function.arguments = '{"city": "北京"}'; msg1.tool_calls = [tc1]
        msg2 = MagicMock(); msg2.content = None
        tc2 = MagicMock(); tc2.id = "c2"; tc2.function.name = "weather"
        tc2.function.arguments = '{"city": "北京"}'; msg2.tool_calls = [tc2]
        fmsg = MagicMock(); fmsg.content = "done"; fmsg.tool_calls = None
        cnt = [0]
        def side(*a, **kw):
            cnt[0] += 1
            if cnt[0] == 1: return MagicMock(choices=[MagicMock(message=msg1)])
            if cnt[0] == 2: return MagicMock(choices=[MagicMock(message=msg2)])
            return MagicMock(choices=[MagicMock(message=fmsg)])
        with patch("openai.resources.chat.completions.Completions.create", side_effect=side):
            traj = agent.run("北京天气")
        assert traj.tool_calls[0].result.success is True
        assert traj.tool_calls[1].result.data.get("deduped") is True
        assert "temp" in traj.tool_calls[1].result.data

    def test_deduped延迟为0(self, agent):
        """deduped 调用 latency_ms 必须为 0，不污染统计"""
        msg1 = MagicMock(); msg1.content = None
        tc1 = MagicMock(); tc1.id = "c1"; tc1.function.name = "calculator"
        tc1.function.arguments = '{"expression": "1+1"}'; msg1.tool_calls = [tc1]
        msg2 = MagicMock(); msg2.content = None
        tc2 = MagicMock(); tc2.id = "c2"; tc2.function.name = "calculator"
        tc2.function.arguments = '{"expression": "1+1"}'; msg2.tool_calls = [tc2]
        fmsg = MagicMock(); fmsg.content = "2"; fmsg.tool_calls = None
        cnt = [0]
        def side(*a, **kw):
            cnt[0] += 1
            if cnt[0] == 1: return MagicMock(choices=[MagicMock(message=msg1)])
            if cnt[0] == 2: return MagicMock(choices=[MagicMock(message=msg2)])
            return MagicMock(choices=[MagicMock(message=fmsg)])
        with patch("openai.resources.chat.completions.Completions.create", side_effect=side):
            traj = agent.run("1+1")
        # 第一次调用有实际耗时
        assert traj.tool_calls[0].latency_ms > 0
        # deduped 调用 latency 为 0
        assert traj.tool_calls[1].latency_ms == 0.0
        assert traj.tool_calls[1].result.latency_ms == 0.0
