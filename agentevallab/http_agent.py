"""
agentevallab/http_agent.py — HTTP Agent 适配器

通过 HTTP 调用外部 Agent 服务，纳入统一评测。

使用方式：
    agent = HTTPAgent(endpoint_url="http://localhost:8001/agent")
    trajectory = agent.run("北京天气怎么样？")

支持两种响应格式：
1. 简单格式：{"final_answer": "...", "tool_calls": []}
2. 完整格式：{"final_answer": "...", "tool_calls": [{tool_name, params, result, latency_ms}]}
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from agentevallab.agent import AgentProtocol
from agentevallab.trajectory import ToolCall, ToolResult, AgentTrajectory


class HTTPAgent(AgentProtocol):
    """通过 HTTP 调用外部 Agent。"""

    def __init__(
        self,
        endpoint_url: str,
        method: str = "POST",
        timeout: float = 30.0,
        input_field: str = "input",
        headers: dict[str, str] | None = None,
    ):
        self.endpoint_url = endpoint_url
        self.method = method.upper()
        self.timeout = timeout
        self.input_field = input_field
        self.headers = headers or {"Content-Type": "application/json"}

    def run(self, user_input: str) -> AgentTrajectory:
        traj = AgentTrajectory(user_input=user_input)

        try:
            t0 = time.perf_counter()
            resp = requests.request(
                self.method,
                self.endpoint_url,
                json={self.input_field: user_input},
                timeout=self.timeout,
                headers=self.headers,
            )
            latency = (time.perf_counter() - t0) * 1000
            traj.network_latency_ms = latency

            if not resp.ok:
                traj.set_final_answer(
                    f"HTTP Agent 调用失败：{resp.status_code} {resp.reason}"
                )
                return traj

            data = resp.json()
        except requests.Timeout:
            traj.set_final_answer("HTTP Agent 调用超时")
            return traj
        except requests.ConnectionError as e:
            traj.set_final_answer(f"HTTP Agent 连接失败：{e}")
            return traj
        except Exception as e:
            traj.set_final_answer(f"HTTP Agent 调用失败：{e}")
            return traj

        # 解析 final_answer
        final = data.get("final_answer", "")
        traj.set_final_answer(final)

        # 解析 tool_calls
        for tc_data in data.get("tool_calls", []):
            result = ToolResult(
                success=tc_data.get("result", {}).get("success", True),
                data=tc_data.get("result", {}).get("data", {}),
                error=tc_data.get("result", {}).get("error"),
            )
            call = ToolCall(
                tool_name=tc_data.get("tool_name", "unknown"),
                params=tc_data.get("params", {}),
                result=result,
                latency_ms=tc_data.get("latency_ms", 0),
            )
            traj.add_tool_call(call)

        return traj
