"""
agentevallab/agent.py — Agent 接口与实现

本模块定义：

- AgentProtocol   — 抽象基类，所有 Agent 必须实现 run(input) → AgentTrajectory
- RuleBasedAgent  — 基于关键词+正则匹配的规则引擎 Agent（v0.1）

将来对接真实 LLM 时，只需新增 LLMAgent(AgentProtocol) 实现类即可。
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from agentevallab.trajectory import ToolCall, AgentTrajectory
from agentevallab.tools import (
    ToolResult,
    tool_calculator,
    tool_weather,
    tool_knowledge,
    _WEATHER_DB,   # 城市列表
    _KNOWLEDGE_DB,  # 知识库 key 列表
)


# ============================================================
# 抽象接口
# ============================================================

class AgentProtocol(ABC):
    """Agent 抽象基类。

    所有 Agent（无论是规则引擎还是 LLM 驱动）都必须实现 run 方法。
    Runner 和 Assertions 只依赖此接口，不关心底层实现。
    """

    @abstractmethod
    def run(self, user_input: str) -> AgentTrajectory:
        """接收用户输入，执行 Think-Act-Observe 循环，返回完整轨迹。"""
        ...


# ============================================================
# RuleBasedAgent 实现
# ============================================================

class RuleBasedAgent(AgentProtocol):
    """基于规则的 Agent（模拟实现）。

    意图识别方式：
    - 计算：输入中包含数字和运算符（*, +, -, /, **）
    - 天气：输入中包含城市名 + 天气关键词
    - 知识：输入中包含知识库 key
    - 多工具：同时满足天气和知识意图时，先查天气再查知识

    不依赖任何外部 API，所有决策都是确定性的。
    """

    # 天气相关的关键词
    WEATHER_KEYWORDS = ["天气", "多少度", "温度", "热不热", "冷不冷",
                        "下雨", "下雪", "刮风", "湿度", "空气质量"]

    # 数学相关的关键词
    MATH_KEYWORDS = ["等于多少", "计算", "算一下", "帮我算", "多少",
                     "加", "减", "乘", "除"]

    def run(self, user_input: str) -> AgentTrajectory:
        """执行规则引擎，返回完整轨迹。"""
        traj = AgentTrajectory(user_input=user_input)

        # 空输入直接返回
        if not user_input.strip():
            traj.set_final_answer("抱歉，我没有理解您的问题。请尝试描述您想查询的内容。")
            return traj

        # 步骤 1：检测所有可能的意图
        has_math = self._detect_math(user_input)
        has_weather = self._detect_weather(user_input)
        has_knowledge = self._detect_knowledge(user_input)

        # 步骤 2：按优先级执行
        if has_weather and has_knowledge:
            # 多工具串联：先查天气，再查知识
            self._do_weather(user_input, traj)
            weather_part = traj.final_answer  # 暂存天气结果
            self._do_knowledge(user_input, traj)
            # 拼接两个工具的答案，避免后执行的覆盖先执行的
            traj.set_final_answer(f"{weather_part}\n\n{traj.final_answer}")
        elif has_math:
            self._do_math(user_input, traj)
        elif has_weather:
            self._do_weather(user_input, traj)
        elif has_knowledge:
            self._do_knowledge(user_input, traj)
        else:
            # 无法识别
            traj.set_final_answer(
                "抱歉，我没有理解您的问题。您可以尝试：\n"
                "  - 数学计算：如 '123*456 等于多少？'\n"
                "  - 天气查询：如 '北京今天天气怎么样？'\n"
                "  - 知识问答：如 '什么是RAG？'"
            )

        return traj

    # ================================================================
    # 意图检测
    # ================================================================

    def _detect_math(self, text: str) -> bool:
        """检测是否包含数学计算意图。

        条件：包含数字 + 运算符（*, +, -, /, **）或数学关键词。
        """
        # 必须有数字
        if not re.search(r"\d", text):
            return False
        # 有运算符或数学关键词
        has_operator = bool(re.search(r"[\+\-\*\/\*\*]", text))
        has_keyword = any(kw in text for kw in self.MATH_KEYWORDS)
        return has_operator or has_keyword

    def _detect_weather(self, text: str) -> bool:
        """检测是否包含天气查询意图。

        条件：
        1. 已知城市名 + 天气关键词（如 '北京天气'）
        2. 或匹配 'XX天气/XX多少度' 模式（如 '火星天气'，城市即使不在库也尝试）
        """
        has_known_city = any(city in text for city in _WEATHER_DB)
        has_keyword = any(kw in text for kw in self.WEATHER_KEYWORDS)
        # 精确匹配：已知城市 + 天气关键词
        if has_known_city and has_keyword:
            return True
        # 模糊匹配：'XX天气' / 'XX的天气' / 'XX多少度' 模式
        if re.search(r"\S{1,6}(?:的)?(?:天气|多少度|温度|热不热)", text):
            return True
        return False

    def _detect_knowledge(self, text: str) -> bool:
        """检测是否包含知识库查询意图。

        条件：包含知识库中任一 key。
        """
        return any(key in text for key in _KNOWLEDGE_DB)

    # ================================================================
    # 参数提取
    # ================================================================

    def _extract_expression(self, text: str) -> str | None:
        """从文本中提取数学表达式。

        支持中文数学词的转换：
            '除以' → '/'，'乘以' → '*'，'减去' → '-'，'加上' → '+'
            '的N次方' → '**N'

        示例：
            '123*456 等于多少？'        → '123*456'
            '100 除以 4 等于多少？'      → '100/4'
            '2的10次方等于多少？'        → '2**10'
            '500减去123等于多少？'       → '500-123'
        """
        # 预处理：中文数学词 → 运算符
        normalized = text
        normalized = re.sub(r"的\s*(\d+)\s*次方", r"**\1", normalized)
        normalized = normalized.replace("除以", "/")
        normalized = normalized.replace("乘以", "*")
        normalized = normalized.replace("减去", "-")
        normalized = normalized.replace("加上", "+")
        normalized = normalized.replace("乘", "*")
        normalized = normalized.replace("除", "/")

        # 匹配包含数字和运算符的连续片段
        match = re.search(r"[\d\s\+\-\*\/\(\)\.]+", normalized)
        if match:
            # 清理多余空格
            expr = re.sub(r"\s+", "", match.group())
            # 确保至少有一个运算符（排除纯数字）
            if re.search(r"[\+\-\*\/]", expr):
                return expr
        return None

    def _extract_city(self, text: str) -> str | None:
        """从文本中提取城市名。

        优先匹配已知城市，其次用正则提取 'XX天气' 模式中的 XX。
        """
        # 优先匹配已知城市
        for city in _WEATHER_DB:
            if city in text:
                return city
        # 正则提取：'XX天气' / 'XX的天气' 模式
        match = re.search(r"(\S{1,6})(?:的)?(?:天气|多少度|温度)", text)
        if match:
            return match.group(1)
        return None

    def _extract_knowledge_query(self, text: str) -> str | None:
        """从文本中提取知识库查询 key。

        遍历知识库中所有 key，返回第一个在文本中出现的。
        """
        for key in _KNOWLEDGE_DB:
            if key in text:
                return key
        return None

    # ================================================================
    # 工具调用执行
    # ================================================================

    def _do_math(self, text: str, traj: AgentTrajectory) -> None:
        """执行数学计算并记录轨迹。"""
        expr = self._extract_expression(text)
        if expr is None:
            traj.set_final_answer("抱歉，我没有识别到有效的数学表达式。")
            return

        result = tool_calculator(expr)
        call = ToolCall(tool_name="calculator", params={"expression": expr}, result=result)
        traj.add_tool_call(call)

        if result.success:
            traj.set_final_answer(f"{expr} = {result.data['result']}")
        else:
            traj.set_final_answer(f"计算 {expr} 时出错：{result.error}")

    def _do_weather(self, text: str, traj: AgentTrajectory) -> None:
        """执行天气查询并记录轨迹。"""
        city = self._extract_city(text)
        if city is None:
            traj.set_final_answer("抱歉，我没有识别到城市名称。")
            return

        result = tool_weather(city)
        call = ToolCall(tool_name="weather", params={"city": city}, result=result)
        traj.add_tool_call(call)

        if result.success:
            d = result.data
            traj.set_final_answer(
                f"{city}当前天气：{d['weather']}，气温 {d['temp']}°C，"
                f"湿度 {d['humidity']}，{d['wind']}。"
            )
        else:
            traj.set_final_answer(f"查询 {city} 天气失败：{result.error}")

    def _do_knowledge(self, text: str, traj: AgentTrajectory) -> None:
        """执行知识库查询并记录轨迹。"""
        query = self._extract_knowledge_query(text)
        if query is None:
            traj.set_final_answer("抱歉，我没有在知识库中找到相关内容。")
            return

        result = tool_knowledge(query)
        call = ToolCall(tool_name="knowledge", params={"query": query}, result=result)
        traj.add_tool_call(call)

        if result.success:
            traj.set_final_answer(result.data["answer"])
        else:
            traj.set_final_answer(f"知识查询失败：{result.error}")
