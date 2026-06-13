"""
tests/test_fault_injector.py — 故障注入测试

测试 6 种故障注入类型及其装饰器/上下文管理器用法。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.tools import ToolResult, tool_calculator, tool_weather
from agentevallab.fault_injector import (
    inject_fault,
    FaultRegistry,
    fault_context,
    injectable,
    FAULT_TYPES,
)


# ============================================================
# 故障类型测试
# ============================================================

class TestFaultTypes:
    """每种故障类型是否正确定义"""

    def test_六种故障类型已注册(self):
        """FAULT_TYPES 包含全部 6 种故障"""
        assert "timeout" in FAULT_TYPES
        assert "http_500" in FAULT_TYPES
        assert "invalid_json" in FAULT_TYPES
        assert "empty_result" in FAULT_TYPES
        assert "permission_denied" in FAULT_TYPES
        assert "network_unreachable" in FAULT_TYPES

    def test_timeout故障_延迟正确(self):
        """timeout 注入后，延迟应 >= 指定值"""
        result = inject_fault(ToolResult(success=True, data={"x": 1}), "timeout", delay=0.05)
        assert result.success is False
        assert "超时" in result.error
        assert result.data is None

    def test_http_500故障(self):
        """http_500 应返回服务器错误"""
        result = inject_fault(ToolResult(success=True, data={"temp": 35}), "http_500")
        assert result.success is False
        assert "500" in result.error or "服务器" in result.error

    def test_invalid_json故障(self):
        """invalid_json 应返回解析失败"""
        result = inject_fault(ToolResult(success=True, data={"answer": "..."}), "invalid_json")
        assert result.success is False
        assert "JSON" in result.error or "格式" in result.error or "解析" in result.error

    def test_empty_result故障(self):
        """empty_result 应返回空数据"""
        result = inject_fault(ToolResult(success=True, data={"temp": 35}), "empty_result")
        assert result.success is False
        assert "空" in result.error or "结果" in result.error

    def test_permission_denied故障(self):
        """permission_denied 应返回权限拒绝"""
        result = inject_fault(ToolResult(success=True, data={}), "permission_denied")
        assert result.success is False
        assert "权限" in result.error or "拒绝" in result.error

    def test_network_unreachable故障(self):
        """network_unreachable 应返回网络错误"""
        result = inject_fault(ToolResult(success=True, data={}), "network_unreachable")
        assert result.success is False
        assert "网络" in result.error or "不可达" in result.error

    def test_正常结果不受影响(self):
        """不注入故障时，正常 ToolResult 不受影响"""
        original = ToolResult(success=True, data={"temp": 35})
        result = inject_fault(original, None)  # 无故障
        assert result.success is True
        assert result.data == {"temp": 35}


# ============================================================
# FaultRegistry 测试
# ============================================================

class TestFaultRegistry:
    """故障注册表：管理哪些工具被注入了什么故障"""

    def test_注册故障(self):
        """set() 为工具设置故障，get() 获取"""
        reg = FaultRegistry()
        reg.set("weather", "timeout", delay=2.0)
        assert reg.get("weather") == ("timeout", {"delay": 2.0})

    def test_清除故障(self):
        """clear() 后 get() 返回 None"""
        reg = FaultRegistry()
        reg.set("weather", "timeout")
        reg.clear("weather")
        assert reg.get("weather") is None

    def test_未注册的工具返回None(self):
        """未注册故障的工具 get() 返回 None"""
        reg = FaultRegistry()
        assert reg.get("calculator") is None

    def test_清空全部(self):
        """clear_all() 清除所有注册"""
        reg = FaultRegistry()
        reg.set("weather", "timeout")
        reg.set("knowledge", "http_500")
        reg.clear_all()
        assert reg.get("weather") is None
        assert reg.get("knowledge") is None


# ============================================================
# fault_context 上下文管理器测试
# ============================================================

class TestFaultContext:
    """fault_context 用于在测试期间临时注入故障"""

    def test_上下文内注入生效(self):
        """with fault_context(...) 内，注册的故障生效"""
        with fault_context("weather", "timeout", delay=0.01):
            reg = FaultRegistry._global
            assert reg.get("weather") == ("timeout", {"delay": 0.01})

    def test_上下文退出后故障清除(self):
        """退出 with 块后，故障自动清除"""
        with fault_context("weather", "http_500"):
            pass
        reg = FaultRegistry._global
        assert reg.get("weather") is None

    def test_嵌套上下文(self):
        """嵌套时内层覆盖外层，退出后恢复"""
        with fault_context("weather", "timeout"):
            assert FaultRegistry._global.get("weather")[0] == "timeout"
            with fault_context("weather", "http_500"):
                assert FaultRegistry._global.get("weather")[0] == "http_500"
            assert FaultRegistry._global.get("weather")[0] == "timeout"


# ============================================================
# injectable 装饰器测试
# ============================================================

class TestInjectableDecorator:
    """@injectable 装饰器：让工具函数自动检测并注入故障"""

    def test_无故障时正常调用(self):
        """全局注册表中无故障时，被装饰函数正常执行"""

        @injectable("calculator")
        def my_tool(x):
            return ToolResult(success=True, data={"result": int(x) * 2})

        result = my_tool("5")
        assert result.success is True
        assert result.data["result"] == 10

    def test_有故障时自动注入(self):
        """全局注册表中有对应工具故障时，函数被拦截"""

        @injectable("calculator")
        def my_tool(x):
            return ToolResult(success=True, data={"result": int(x) * 2})

        with fault_context("calculator", "timeout", delay=0.01):
            result = my_tool("5")
            assert result.success is False
            assert "超时" in result.error

    def test_故障只影响注册的工具(self):
        """故障只注入到指定工具，其他工具不受影响"""

        @injectable("weather")
        def weather_tool(city):
            return ToolResult(success=True, data={"city": city})

        @injectable("calculator")
        def calc_tool(x):
            return ToolResult(success=True, data={"result": x})

        with fault_context("weather", "http_500"):
            weather_result = weather_tool("北京")
            calc_result = calc_tool("123")
            # weather 被注入故障
            assert weather_result.success is False
            # calculator 不受影响
            assert calc_result.success is True
