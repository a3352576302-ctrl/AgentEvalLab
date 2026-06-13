"""
agentevallab/llm_agent.py — LLM Agent 适配器（v0.5）

本模块实现通过 OpenAI-compatible API 调用的真实 LLM Agent。
支持 MiniMax、OpenAI、DeepSeek 等兼容接口。

使用方式：
    agent = LLMAgent()                              # 从环境变量读取
    agent = LLMAgent(api_key="xxx", model="minimax-m2")
    trajectory = agent.run("北京天气怎么样？")

环境变量：
    MINIMAX_API_KEY  / OPENAI_API_KEY   — API 密钥
    MINIMAX_BASE_URL / OPENAI_BASE_URL  — API 端点（可选）
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from agentevallab.agent import AgentProtocol
from agentevallab.trajectory import ToolCall, ToolResult, AgentTrajectory
from agentevallab.tools import TOOL_REGISTRY


# ============================================================
# 工具定义 → OpenAI Function Calling 格式
# ============================================================

def _build_tools_schema() -> list[dict[str, Any]]:
    """将 TOOL_REGISTRY 转为 OpenAI Function Calling 的工具描述。"""
    schema = []
    for name, meta in TOOL_REGISTRY.items():
        # 构建 parameters schema
        properties = {}
        required = []
        for param_name, param_desc in meta.get("parameters", {}).items():
            properties[param_name] = {
                "type": "string",
                "description": param_desc,
            }
            required.append(param_name)

        schema.append({
            "type": "function",
            "function": {
                "name": name,
                "description": meta["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return schema


# ============================================================
# LLMAgent
# ============================================================

class LLMAgent(AgentProtocol):
    """使用真实 LLM API（OpenAI 兼容接口）的 Agent。

    通过 Function Calling 让模型自主决定调用哪些工具。
    每次调用返回完整的 AgentTrajectory。

    参数：
        api_key  — API 密钥，默认从 MINIMAX_API_KEY / OPENAI_API_KEY 读取
        base_url — API 端点，默认 https://api.minimax.chat/v1
        model    — 模型名称，默认 minimax-m2
        max_rounds — 最大工具调用轮次，默认 10
    """

    SYSTEM_PROMPT = (
        "你是一个有用的 AI 助手，可以调用工具来回答用户问题。"
        "当用户询问天气时，使用 weather 工具。"
        "当用户询问技术概念时，使用 knowledge 工具。"
        "当用户需要计算时，使用 calculator 工具。"
        "如果用户的问题无法用现有工具回答，直接说明。"
        "不要调用未提供的工具。"
        "不要编造工具返回结果中没有的信息。"
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "minimax-m2",
        max_rounds: int = 10,
    ):
        self.api_key = (
            api_key
            or os.environ.get("MINIMAX_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )
        self.base_url = (
            base_url
            or os.environ.get("MINIMAX_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.minimax.chat/v1"
        )
        self.model = model
        self.max_rounds = max_rounds
        self.tools_schema = _build_tools_schema()

    def run(self, user_input: str) -> AgentTrajectory:
        """执行 LLM Agent 循环，返回完整轨迹。

        流程：
        1. 向 LLM 发送 user_input + 可用工具列表
        2. LLM 决定是否调用工具 → 执行工具 → 将结果返回 LLM
        3. 重复直到 LLM 决定不再调用工具（或达到 max_rounds）
        """
        try:
            from openai import OpenAI
        except ImportError:
            return self._fallback_no_openai(user_input)

        if not self.api_key:
            return self._fallback_no_key(user_input)

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        traj = AgentTrajectory(user_input=user_input)

        # 对话历史
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        for _round in range(self.max_rounds):
            try:
                t_api_start = time.perf_counter()
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools_schema,
                    tool_choice="auto",
                    temperature=0.1,  # 低温度减少随机性
                )
                api_latency = (time.perf_counter() - t_api_start) * 1000
                traj.network_latency_ms += api_latency
            except Exception as e:
                traj.set_final_answer(f"LLM 调用失败：{e}")
                return traj

            choice = response.choices[0]
            msg = choice.message

            # 如果模型决定不调工具，直接返回文本
            if not msg.tool_calls:
                traj.set_final_answer(msg.content or "")
                return traj

            # 先将 assistant 消息（含 tool_calls）加入对话
            messages.append(msg)

            # 再执行所有工具调用，将工具结果加入对话
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                try:
                    params = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    params = {}

                # 调用工具
                t0 = time.perf_counter()
                if tool_name in TOOL_REGISTRY:
                    result = TOOL_REGISTRY[tool_name]["function"](
                        **params
                    )
                else:
                    result = ToolResult(
                        success=False,
                        error=f"未知工具: {tool_name}",
                    )
                latency = (time.perf_counter() - t0) * 1000

                # 记录轨迹
                call_record = ToolCall(
                    tool_name=tool_name,
                    params=params,
                    result=result,
                    latency_ms=latency,
                )
                traj.add_tool_call(call_record)

                # 将工具结果加入对话（在 assistant 消息之后）
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result.data, ensure_ascii=False)
                    if result.success
                    else result.error,
                })

        # 超过最大轮次
        traj.set_final_answer("达到最大工具调用轮次限制")
        return traj

    def _fallback_no_key(self, user_input: str) -> AgentTrajectory:
        """未配置 API Key 时的降级处理。"""
        traj = AgentTrajectory(user_input=user_input)
        traj.set_final_answer(
            "LLMAgent 未配置 API Key。"
            "请设置环境变量 MINIMAX_API_KEY 或 OPENAI_API_KEY。"
        )
        return traj

    def _fallback_no_openai(self, user_input: str) -> AgentTrajectory:
        """未安装 openai 包时的降级处理。"""
        traj = AgentTrajectory(user_input=user_input)
        traj.set_final_answer(
            "LLMAgent 需要 openai 包。请运行: pip install openai"
        )
        return traj
