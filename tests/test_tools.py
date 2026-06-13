"""
tests/test_tools.py — 模拟工具测试

测试 calculator、weather、knowledge 三个工具的正常和异常情况。
"""
import sys
import os

# 将 agentevallab 包加入搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.tools import (
    tool_calculator,
    tool_weather,
    tool_knowledge,
    ToolResult,
)


# ============================================================
# calculator 测试
# ============================================================

class TestCalculator:
    """calculator 工具测试"""

    def test_乘法正常(self):
        """正常计算：123*456 应返回 56088"""
        result = tool_calculator("123*456")
        assert result.success is True
        assert result.data["result"] == 56088

    def test_加法正常(self):
        """正常计算：1+2+3 应返回 6"""
        result = tool_calculator("1+2+3")
        assert result.success is True
        assert result.data["result"] == 6

    def test_除法正常(self):
        """正常计算：10/3 应返回浮点数"""
        result = tool_calculator("10/3")
        assert result.success is True
        assert abs(result.data["result"] - 3.333333) < 0.001

    def test_负数正常(self):
        """负数运算：-5+10 应返回 5"""
        result = tool_calculator("-5+10")
        assert result.success is True
        assert result.data["result"] == 5

    def test_幂运算(self):
        """幂运算：2**10 应返回 1024"""
        result = tool_calculator("2**10")
        assert result.success is True
        assert result.data["result"] == 1024

    def test_返回结构正确(self):
        """ToolResult 应包含 success/data/error/latency_ms 四个字段"""
        result = tool_calculator("1+1")
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data is not None
        assert result.error is None
        assert result.latency_ms >= 0

    def test_非法表达式返回失败(self):
        """传入不是数学表达式的内容应返回失败"""
        result = tool_calculator("__import__('os').system('dir')")
        assert result.success is False
        assert result.error is not None

    def test_空字符串返回失败(self):
        """空字符串应返回失败"""
        result = tool_calculator("")
        assert result.success is False


# ============================================================
# weather 测试
# ============================================================

class TestWeather:
    """weather 工具测试"""

    def test_北京天气(self):
        """查询北京天气，应返回'晴'"""
        result = tool_weather("北京")
        assert result.success is True
        assert result.data["city"] == "北京"
        assert "temp" in result.data
        assert "weather" in result.data

    def test_上海天气(self):
        """查询上海天气"""
        result = tool_weather("上海")
        assert result.success is True
        assert result.data["city"] == "上海"

    def test_不存在的城市(self):
        """查询不存在的城市应返回失败"""
        result = tool_weather("火星")
        assert result.success is False
        assert result.error is not None

    def test_返回结构正确(self):
        """返回的 data 应包含 city/temp/weather/humidity/wind"""
        result = tool_weather("深圳")
        assert result.success is True
        keys = result.data.keys()
        assert "city" in keys
        assert "temp" in keys
        assert "weather" in keys


# ============================================================
# knowledge 测试
# ============================================================

class TestKnowledge:
    """knowledge 工具测试"""

    def test_TCP查询(self):
        """查询'TCP三次握手'应返回相关内容"""
        result = tool_knowledge("TCP三次握手")
        assert result.success is True
        assert "SYN" in result.data["answer"]

    def test_RAG查询(self):
        """查询'RAG'应返回相关内容"""
        result = tool_knowledge("什么是RAG")
        assert result.success is True
        assert "检索增强" in result.data["answer"]

    def test_未知查询(self):
        """查询知识库中没有的内容应返回失败"""
        result = tool_knowledge("今天股票涨了吗")
        assert result.success is False
        assert result.error is not None

    def test_返回结构正确(self):
        """返回的 data 应包含 query/matched_key/answer"""
        result = tool_knowledge("什么是Agent")
        assert result.success is True
        assert "query" in result.data
        assert "matched_key" in result.data
        assert "answer" in result.data
