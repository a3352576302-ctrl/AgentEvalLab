"""
agentevallab/llm_agent.py — LLM Agent 适配器（v0.5）

本模块实现通过 OpenAI-compatible API 调用的真实 LLM Agent。
支持 MiniMax、OpenAI、DeepSeek 等兼容接口。

使用方式：
    agent = LLMAgent()                              # 从环境变量读取
    agent = LLMAgent(api_key="xxx", model="minimax-m2")
    trajectory = agent.run("北京天气怎么样？")

环境变量：
    MINIMAX_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY   — API 密钥
    MINIMAX_BASE_URL / DEEPSEEK_BASE_URL / OPENAI_BASE_URL — API 端点（可选）
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from agentevallab.agent import AgentProtocol
from agentevallab.trajectory import ToolCall, ToolResult, AgentTrajectory
from agentevallab.tools import TOOL_REGISTRY


PROVIDER_CONFIG = {
    "minimax": {
        "api_key_envs": ("MINIMAX_API_KEY",),
        "base_url_envs": ("MINIMAX_BASE_URL",),
        "default_base_url": "https://api.minimax.chat/v1",
    },
    "deepseek": {
        # DEEPSEEK_API_KEY is preferred. OPENAI_API_KEY is kept as a
        # compatibility fallback because early project docs used it for DeepSeek.
        "api_key_envs": ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"),
        "base_url_envs": ("DEEPSEEK_BASE_URL", "OPENAI_BASE_URL"),
        "default_base_url": "https://api.deepseek.com/v1",
    },
    "openai": {
        "api_key_envs": ("OPENAI_API_KEY",),
        "base_url_envs": ("OPENAI_BASE_URL",),
        "default_base_url": "https://api.openai.com/v1",
    },
}


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _is_retryable(exception: Exception) -> bool:
    """判断异常是否可重试。

    可重试：限流(429)、服务端错误(5xx)、网络超时、连接错误
    不可重试：认证错误(401/403)、请求格式错误(400)、余额不足(402)
    """
    msg = str(exception).lower()
    # 不可重试
    non_retryable = ["401", "402", "403", "400", "insufficient_balance",
                     "invalid_api_key", "authentication"]
    for keyword in non_retryable:
        if keyword in msg:
            return False
    # 可重试
    retryable = ["429", "500", "502", "503", "504", "timeout", "timed out",
                 "connection", "rate limit", "rate_limit", "overloaded",
                 "server error", "internal error", "temporarily"]
    for keyword in retryable:
        if keyword in msg:
            return True
    # 默认不可重试（保守策略）
    return False


def _infer_provider(provider: str, base_url: str | None, model: str) -> str:
    """Resolve provider from explicit input, endpoint, or model name."""
    if provider != "auto":
        if provider not in PROVIDER_CONFIG:
            raise ValueError(
                f"未知 provider: {provider}，可选: auto/minimax/deepseek/openai"
            )
        return provider

    signal = f"{base_url or ''} {model or ''}".lower()
    if "deepseek" in signal:
        return "deepseek"
    if "minimax" in signal:
        return "minimax"
    if "openai" in signal or "gpt-" in signal:
        return "openai"

    # Backward-compatible default for earlier MiniMax-oriented usage.
    return "minimax"


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
        provider — 供应商：auto/minimax/deepseek/openai，默认 auto
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
        provider: str = "auto",
        max_rounds: int = 10,
        max_retries: int = 3,
    ):
        self.provider = _infer_provider(provider, base_url, model)
        config = PROVIDER_CONFIG[self.provider]
        self.api_key = api_key or _first_env(config["api_key_envs"])
        self.base_url = (
            base_url
            or _first_env(config["base_url_envs"])
            or config["default_base_url"]
        )
        self.model = model
        self.max_rounds = max_rounds
        self.max_retries = max_retries
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
            # 带指数退避的重试
            last_error: Exception | None = None
            for attempt in range(self.max_retries + 1):  # 1 次原始 + N 次重试
                try:
                    t_api_start = time.perf_counter()
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        tools=self.tools_schema,
                        tool_choice="auto",
                        temperature=0.1,
                    )
                    api_latency = (time.perf_counter() - t_api_start) * 1000
                    traj.network_latency_ms += api_latency
                    if hasattr(response, "usage") and response.usage:
                        traj.prompt_tokens += response.usage.prompt_tokens or 0
                        traj.completion_tokens += response.usage.completion_tokens or 0
                        traj.total_tokens += response.usage.total_tokens or 0
                    last_error = None
                    break  # 成功，跳出重试循环
                except Exception as e:
                    last_error = e
                    if attempt < self.max_retries and _is_retryable(e):
                        wait_s = 2 ** attempt  # 1s, 2s, 4s
                        time.sleep(wait_s)
                        continue
                    break  # 不可重试或用完重试次数

            if last_error is not None:
                traj.set_final_answer(f"LLM 调用失败：{last_error}")
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
