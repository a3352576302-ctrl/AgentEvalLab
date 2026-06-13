"""
agentevallab/trajectory.py — 数据结构

本模块定义 AgentEvalLab 的核心数据结构：

- ToolResult       — 工具调用返回的统一结构
- ToolCall         — 一次工具调用记录（工具名、参数、结果、耗时）
- AgentTrajectory  — 一次 Agent 运行轨迹（输入、多次调用、最终答案）

所有结构使用 dataclass，保持简单、可序列化。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ============================================================
# ToolResult — 工具返回的统一结构
# ============================================================

@dataclass
class ToolResult:
    """工具调用返回的统一结构。

    success    — 调用是否成功
    data       — 成功时返回的数据
    error      — 失败时的错误信息
    latency_ms — 执行耗时（毫秒）
    """
    success: bool
    data: Any = None
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class ToolCall:
    """记录一次工具调用的完整信息。

    tool_name  — 被调用的工具名称（如 'calculator'）
    params     — 传给工具的参数（如 {'expression': '123*456'}）
    result     — 工具返回的 ToolResult 对象
    latency_ms — 本次调用耗时（毫秒），默认取 result.latency_ms
    """
    tool_name: str
    params: dict[str, Any]
    result: ToolResult
    latency_ms: float | None = None

    def __post_init__(self):
        """如果未指定 latency_ms，自动从 result 中获取。"""
        if self.latency_ms is None:
            self.latency_ms = getattr(self.result, "latency_ms", 0.0)

    def to_dict(self) -> dict[str, Any]:
        """转为可序列化的字典，方便输出到 JSON/YAML/报告。

        返回字段：
            tool_name / params / success / data / error / latency_ms
        """
        return {
            "tool_name": self.tool_name,
            "params": self.params,
            "success": self.result.success,
            "data": self.result.data,
            "error": self.result.error,
            "latency_ms": self.latency_ms,
        }


@dataclass
class AgentTrajectory:
    """记录一次 Agent 运行的执行轨迹。

    记录内容：
        - 工具调用（名称、参数、返回结果、耗时）
        - 最终答案
        - 不记录私有思维链（CoT），仅记录可验证的 action/observation

    user_input    — 用户输入的原始文本
    tool_calls    — 按顺序记录的所有工具调用
    final_answer  — Agent 最终返回给用户的答案
    total_rounds  — 工具调用总轮次（自动计算）
    """
    user_input: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_answer: str = ""

    # ================================================================
    # 只读属性
    # ================================================================

    @property
    def total_rounds(self) -> int:
        """工具调用总轮次 = tool_calls 的长度。"""
        return len(self.tool_calls)

    @property
    def total_latency_ms(self) -> float:
        """总耗时 = 所有工具调用耗时之和（毫秒）。"""
        return sum(call.latency_ms or 0 for call in self.tool_calls)

    @property
    def tool_names(self) -> list[str]:
        """按调用顺序返回工具名称列表，方便断言 tool_sequence。"""
        return [call.tool_name for call in self.tool_calls]

    @property
    def all_tools_succeeded(self) -> bool:
        """所有工具调用是否都成功。"""
        if not self.tool_calls:
            return True
        return all(call.result.success for call in self.tool_calls)

    # ================================================================
    # 方法
    # ================================================================

    def add_tool_call(self, call: ToolCall) -> None:
        """向轨迹中添加一次工具调用记录。"""
        self.tool_calls.append(call)

    def set_final_answer(self, answer: str) -> None:
        """设置 Agent 的最终输出答案。"""
        self.final_answer = answer
