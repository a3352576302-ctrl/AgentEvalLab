"""
agentevallab/tools.py — 模拟工具集

本模块提供 Agent 可以调用的外部工具，全部使用本地模拟数据，不访问网络。

工具列表：
- calculator(expression) — 安全的数学表达式求值
- weather(city)        — 模拟天气查询
- knowledge(query)      — 模拟知识库查询

每个工具返回统一的 ToolResult 结构。
"""
from __future__ import annotations

import ast
import operator
import re
import time
from typing import Any

from agentevallab.trajectory import ToolResult
from agentevallab.fault_injector import injectable


# ============================================================
# 安全数学求值器（不使用 eval，防止代码注入）
# ============================================================

# 允许的二元操作符
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


def _safe_eval(expr: str) -> float:
    """用 AST 安全解析数学表达式。

    只允许：加法、减法、乘法、除法、幂运算、负数。
    禁止：函数调用、变量访问、比较运算等。

    示例：
        "123*456"    → 56088
        "2**10"      → 1024
        "-5+10"      → 5
    """
    tree = ast.parse(expr.strip(), mode="eval")

    def _walk(node: ast.AST) -> Any:
        # 顶层包装：mode="eval" 时 ast.parse 返回 Expression(body=...)
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        # 二元运算：左 op 右
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_OPS:
                raise ValueError(f"不允许的操作符: {op_type.__name__}")
            left = _walk(node.left)
            right = _walk(node.right)
            return _ALLOWED_OPS[op_type](left, right)
        # 一元负数：-x
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return -_walk(node.operand)
            raise ValueError(f"不允许的一元操作符: {type(node.op).__name__}")
        # 常量：数字
        if isinstance(node, ast.Constant):
            return node.value
        raise ValueError(f"不支持的语法: {type(node).__name__}")

    return _walk(tree)


# ============================================================
# 模拟数据
# ============================================================

# 天气数据库（固定字典，不访问网络）
_WEATHER_DB = {
    "北京": {"temp": 35, "weather": "晴", "humidity": "45%", "wind": "南风 3级"},
    "上海": {"temp": 28, "weather": "多云转小雨", "humidity": "78%", "wind": "东南风 4级"},
    "深圳": {"temp": 32, "weather": "雷阵雨", "humidity": "85%", "wind": "西南风 2级"},
    "成都": {"temp": 24, "weather": "阴", "humidity": "65%", "wind": "北风 1级"},
    "哈尔滨": {"temp": -15, "weather": "大雪", "humidity": "60%", "wind": "西北风 5级"},
    "拉萨": {"temp": 18, "weather": "晴转多云", "humidity": "30%", "wind": "西风 2级"},
}

# 知识库（固定字典，不访问网络）
_KNOWLEDGE_DB = {
    "35度穿什么": "35°C 高温天气建议穿轻薄、透气的棉麻衣物，注意防晒，避免正午外出。",
    "TCP三次握手": (
        "TCP 三次握手过程："
        "1) 客户端发送 SYN 包，进入 SYN_SENT 状态；"
        "2) 服务器收到后回复 SYN-ACK 包，进入 SYN_RCVD 状态；"
        "3) 客户端收到后回复 ACK 包，双方进入 ESTABLISHED 状态。"
        "握手完成后连接建立，可以开始传输数据。"
    ),
    "什么是RAG": (
        "RAG（Retrieval-Augmented Generation，检索增强生成）"
        "是一种结合信息检索与文本生成的 AI 架构。"
        "先从外部知识库检索相关文档，再基于检索结果生成回答，"
        "可有效减少大模型的幻觉问题。"
    ),
    "什么是Agent": (
        "AI Agent（智能体）是具备自主感知、规划、工具调用和记忆能力的 AI 系统。"
        "核心循环为 Think → Act → Observe。"
        "与普通 Chatbot 的区别在于：Agent 能够自主决定调用哪些工具，"
        "根据工具返回的结果调整下一步行动，形成闭环执行。"
    ),
    "什么是Prompt注入": (
        "Prompt 注入是一种针对 LLM 应用的攻击方式。"
        "攻击者在用户输入中嵌入恶意指令（如「忽略之前的指令」），"
        "试图覆盖或绕过系统预设的 Prompt 约束，"
        "达到越权操作、信息窃取等目的。"
    ),
    "OSI模型": (
        "OSI 七层模型从下到上依次为："
        "物理层（Physical）、数据链路层（Data Link）、网络层（Network）、"
        "传输层（Transport）、会话层（Session）、表示层（Presentation）、"
        "应用层（Application）。"
        "其中 TCP 工作在传输层，IP 工作在网络层，"
        "HTTP/HTTPS 工作在应用层。"
    ),
}


# ============================================================
# 工具实现
# ============================================================

@injectable("calculator")
def tool_calculator(expression: str) -> ToolResult:
    """安全计算数学表达式。

    参数：
        expression — 数学表达式字符串，如 '123*456'

    返回：
        ToolResult，成功时 data.result 为计算结果
    """
    # 归一化：去除所有空格（LLM 经常给表达式加空格）
    normalized = re.sub(r'\s+', '', expression)
    t0 = time.perf_counter()
    try:
        result = _safe_eval(normalized)
        latency = (time.perf_counter() - t0) * 1000
        return ToolResult(
            success=True,
            data={"expression": normalized, "result": result},
            latency_ms=latency,
        )
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return ToolResult(
            success=False,
            error=f"计算失败: {e}",
            latency_ms=latency,
        )


@injectable("weather")
def tool_weather(city: str) -> ToolResult:
    """查询指定城市的天气（模拟数据）。

    参数：
        city — 城市名称，如 '北京'

    返回：
        ToolResult，成功时 data 包含 city/temp/weather/humidity/wind
    """
    t0 = time.perf_counter()
    data = _WEATHER_DB.get(city)
    latency = (time.perf_counter() - t0) * 1000
    if data:
        return ToolResult(
            success=True,
            data={"city": city, **data},
            latency_ms=latency,
        )
    return ToolResult(
        success=False,
        error=f"未找到城市 '{city}' 的天气数据",
        latency_ms=latency,
    )


# 知识库同义词/别名映射
_KNOWLEDGE_ALIASES: dict[str, list[str]] = {
    "什么是RAG": ["RAG", "检索增强生成", "retrieval augmented generation",
                 "RAG技术", "RAG原理", "什么是检索增强生成"],
    "什么是Agent": ["Agent", "智能体", "AI Agent", "agent概念",
                   "什么是智能体", "agent定义"],
    "什么是Prompt注入": ["Prompt注入", "prompt injection", "提示注入",
                        "注入攻击", "提示词注入"],
    "TCP三次握手": ["TCP", "三次握手", "TCP握手", "tcp handshake",
                   "TCP协议", "传输控制协议"],
    "OSI模型": ["OSI", "七层模型", "osi model", "OSI七层",
               "网络分层", "开放系统互连"],
    "35度穿什么": ["35度", "高温穿搭", "炎热穿搭", "夏天穿什么",
                  "高温天气穿什么", "35°C穿搭"],
}


def _normalize_query(q: str) -> str:
    """归一化查询字符串：去标点、去多余空格、全角转半角、转小写。"""
    # 全角→半角
    result = []
    for ch in q:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:  # 全角空格
            result.append(' ')
        else:
            result.append(ch)
    normalized = ''.join(result).lower().strip()
    # 去标点（保留字母数字中文和空格）
    import re
    normalized = re.sub(r'[^\w\s一-鿿]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


@injectable("knowledge")
def tool_knowledge(query: str) -> ToolResult:
    """查询知识库（模拟数据），v1.1 增强模糊匹配。

    匹配策略（按优先级）：
    1. 原始 key 包含在 query 中
    2. query 包含在原始 key 中
    3. 归一化后双向包含匹配（去标点、全角半角、大小写）
    4. 别名/同义词映射
    5. 无匹配时返回 partial hint 而非纯错误

    参数：
        query — 查询关键词或问题，如 'TCP三次握手'

    返回：
        ToolResult，成功时 data 包含 query/matched_key/answer
    """
    t0 = time.perf_counter()
    norm_query = _normalize_query(query)

    # 策略 1+2：原始双向包含匹配
    for key, value in _KNOWLEDGE_DB.items():
        if key in query or query in key:
            latency = (time.perf_counter() - t0) * 1000
            return ToolResult(
                success=True,
                data={"query": query, "matched_key": key, "answer": value},
                latency_ms=latency,
            )

    # 策略 3：归一化后双向包含匹配
    for key, value in _KNOWLEDGE_DB.items():
        norm_key = _normalize_query(key)
        if norm_key in norm_query or norm_query in norm_key:
            latency = (time.perf_counter() - t0) * 1000
            return ToolResult(
                success=True,
                data={"query": query, "matched_key": key, "answer": value,
                      "match_method": "fuzzy"},
                latency_ms=latency,
            )

    # 策略 4：别名映射
    for key, aliases in _KNOWLEDGE_ALIASES.items():
        norm_aliases = [_normalize_query(a) for a in aliases]
        for alias in norm_aliases:
            if alias in norm_query or norm_query in alias:
                value = _KNOWLEDGE_DB[key]
                latency = (time.perf_counter() - t0) * 1000
                return ToolResult(
                    success=True,
                    data={"query": query, "matched_key": key, "answer": value,
                          "match_method": "alias", "matched_alias": alias},
                    latency_ms=latency,
                )

    # 策略 5：无匹配——提供候选提示，减少 LLM 重复调用
    latency = (time.perf_counter() - t0) * 1000
    # 列出知识库中可能相关的 key
    candidates = []
    for key in _KNOWLEDGE_DB:
        k_norm = _normalize_query(key)
        # 简单关键词重叠度
        q_words = set(norm_query.split())
        k_words = set(k_norm.split())
        overlap = len(q_words & k_words)
        if overlap > 0:
            candidates.append(key)
    hint = ""
    if candidates:
        hint = f"。知识库中可能相关条目: {', '.join(candidates[:3])}"
    return ToolResult(
        success=False,
        error=f"知识库中未找到与 '{query}' 精确匹配的内容{hint}。请使用更具体的关键词重试。",
        latency_ms=latency,
    )


# ============================================================
# 工具注册表
# ============================================================

TOOL_REGISTRY = {
    "calculator": {
        "function": tool_calculator,
        "description": "计算数学表达式，支持加减乘除和幂运算",
        "parameters": {"expression": "数学表达式字符串，如 '123*456'"},
        "category": "computation",
    },
    "weather": {
        "function": tool_weather,
        "description": "查询指定城市的天气信息",
        "parameters": {"city": "城市名称，如 '北京'"},
        "category": "information",
    },
    "knowledge": {
        "function": tool_knowledge,
        "description": "查询知识库获取技术信息",
        "parameters": {"query": "查询关键词或问题"},
        "category": "information",
    },
}
