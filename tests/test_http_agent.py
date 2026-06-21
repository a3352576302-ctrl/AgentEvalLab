"""
tests/test_http_agent.py — HTTP Agent 测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from agentevallab.http_agent import HTTPAgent
from agentevallab.agent import AgentProtocol
from agentevallab.trajectory import AgentTrajectory


class TestHTTPAgentInterface:
    def test_实现AgentProtocol(self):
        agent = HTTPAgent("http://localhost/agent")
        assert isinstance(agent, AgentProtocol)


class TestHTTPAgentWithMock:
    @pytest.fixture
    def agent(self):
        return HTTPAgent("http://localhost/agent", timeout=5)

    def test_正常调用_简单格式(self, agent):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "final_answer": "北京今天35°C",
            "tool_calls": [],
        }
        with patch("requests.request", return_value=mock_resp):
            traj = agent.run("北京天气怎么样？")
            assert "35°C" in traj.final_answer
            assert traj.total_rounds == 0

    def test_正常调用_带工具轨迹(self, agent):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "final_answer": "北京35°C",
            "tool_calls": [{
                "tool_name": "weather",
                "params": {"city": "北京"},
                "result": {"success": True, "data": {"temp": 35}},
                "latency_ms": 12,
            }],
        }
        with patch("requests.request", return_value=mock_resp):
            traj = agent.run("北京天气")
            assert traj.total_rounds == 1
            assert traj.tool_names == ["weather"]

    def test_HTTP错误(self, agent):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.reason = "Internal Server Error"
        with patch("requests.request", return_value=mock_resp):
            traj = agent.run("test")
            assert "500" in traj.final_answer

    def test_超时(self, agent):
        import requests
        with patch("requests.request", side_effect=requests.Timeout):
            traj = agent.run("test")
            assert "超时" in traj.final_answer

    def test_连接失败(self, agent):
        import requests
        with patch("requests.request", side_effect=requests.ConnectionError("refused")):
            traj = agent.run("test")
            assert "连接失败" in traj.final_answer
