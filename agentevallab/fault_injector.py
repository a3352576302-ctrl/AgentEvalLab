"""
agentevallab/fault_injector.py — 故障注入系统

本模块提供可配置的故障注入能力，用于模拟 Agent 工具调用中的各种异常。

六种故障类型：
- timeout            — 模拟工具响应超时
- http_500           — 模拟服务器 500 错误
- invalid_json       — 模拟返回格式异常数据
- empty_result       — 模拟返回空结果
- permission_denied  — 模拟权限拒绝
- network_unreachable — 模拟网络不可达

三种使用方式：
1. inject_fault(result, type)        — 直接对 ToolResult 注入故障
2. fault_context(tool, type)         — 上下文管理器，临时激活故障
3. @injectable(tool_name)            — 装饰器，让工具函数自动检测故障

面试亮点：用 Python 装饰器做横切关注点（故障注入），比 Flask route 装饰器更有深度。
"""
from __future__ import annotations

import time
import functools
from contextlib import contextmanager
from typing import Any, Callable

from agentevallab.trajectory import ToolResult


# ============================================================
# 故障类型定义
# ============================================================

FAULT_TYPES: dict[str, str] = {
    "timeout": "工具调用超时",
    "http_500": "服务器内部错误",
    "invalid_json": "返回数据格式异常",
    "empty_result": "返回空结果",
    "permission_denied": "权限拒绝",
    "network_unreachable": "网络不可达",
}


def inject_fault(
    result: ToolResult,
    fault_type: str | None,
    **kwargs,
) -> ToolResult:
    """对 ToolResult 注入指定类型的故障。

    如果 fault_type 为 None 或空字符串，返回原始结果。

    参数：
        result     — 原始工具调用结果
        fault_type — 故障类型（FAULT_TYPES 的 key）
        **kwargs   — 故障参数（如 timeout 的 delay）

    返回：
        注入故障后的 ToolResult
    """
    if not fault_type:
        return result

    if fault_type == "timeout":
        delay = kwargs.get("delay", 3.0)
        time.sleep(delay)
        return ToolResult(
            success=False,
            error=f"工具调用超时（超过 {delay} 秒无响应）",
            latency_ms=delay * 1000,
        )

    if fault_type == "http_500":
        return ToolResult(
            success=False,
            error="服务器内部错误（HTTP 500），请稍后重试",
        )

    if fault_type == "invalid_json":
        return ToolResult(
            success=False,
            error="返回数据格式异常：JSON 解析失败，上游返回了非预期的数据格式",
        )

    if fault_type == "empty_result":
        return ToolResult(
            success=False,
            error="查询结果为空：未找到匹配的数据",
        )

    if fault_type == "permission_denied":
        return ToolResult(
            success=False,
            error="权限拒绝：当前 Agent 无权访问该资源",
        )

    if fault_type == "network_unreachable":
        return ToolResult(
            success=False,
            error="网络不可达：目标服务无法连接，请检查网络配置",
        )

    # 未知故障类型，不注入
    return result


# ============================================================
# 全局故障注册表
# ============================================================

class FaultRegistry:
    """全局故障注册表。

    管理"哪个工具当前被注入了什么故障"。
    使用类级别的 _global 单例存放当前活跃故障。
    注意：当前实现为全局字典，并发执行时需要改用 threading.local() 或
    将注册表实例化并传入 Runner。

    方法：
        set(tool, fault, **kwargs)   — 为工具设置故障
        get(tool)                    — 获取工具的故障配置，无则返回 None
        clear(tool)                  — 清除工具的故障
        clear_all()                  — 清除所有故障
    """

    _global: dict[str, tuple[str, dict]] = {}

    @classmethod
    def set(cls, tool_name: str, fault_type: str, **kwargs) -> None:
        """为指定工具设置故障。"""
        cls._global[tool_name] = (fault_type, kwargs)

    @classmethod
    def get(cls, tool_name: str) -> tuple[str, dict] | None:
        """获取指定工具的故障配置。"""
        return cls._global.get(tool_name)

    @classmethod
    def clear(cls, tool_name: str) -> None:
        """清除指定工具的故障。"""
        cls._global.pop(tool_name, None)

    @classmethod
    def clear_all(cls) -> None:
        """清除所有故障。"""
        cls._global.clear()


# ============================================================
# 上下文管理器
# ============================================================

@contextmanager
def fault_context(tool_name: str, fault_type: str | None, **kwargs):
    """上下文管理器：在 with 块内为指定工具临时激活故障。

    用法：
        with fault_context("weather", "timeout", delay=3.0):
            result = tool_weather("北京")  # 会注入超时故障

    退出 with 块后故障自动清除。
    """
    # 保存外层可能已有的故障配置，支持嵌套
    previous = FaultRegistry.get(tool_name)
    if fault_type:
        FaultRegistry.set(tool_name, fault_type, **kwargs)
    try:
        yield
    finally:
        # 恢复外层配置
        if previous is not None:
            FaultRegistry.set(tool_name, previous[0], **previous[1])
        else:
            FaultRegistry.clear(tool_name)


# ============================================================
# @injectable 装饰器
# ============================================================

def injectable(tool_name: str):
    """装饰器：让工具函数自动检测全局故障注册表。

    被装饰的函数在执行前会检查 FaultRegistry 中是否为当前工具注册了故障。
    如果注册了，直接返回故障结果，不执行原函数。

    用法：
        @injectable("calculator")
        def tool_calculator(expression):
            ...

    面试要点：
        - 这是典型的"装饰器实现横切关注点"案例
        - 故障注入与业务逻辑完全解耦
        - 生产环境中可以通过配置/环境变量控制是否启用
    """
    def decorator(func: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        @functools.wraps(func)  # 保留原函数的 __name__ / __doc__
        def wrapper(*args, **kwargs) -> ToolResult:
            # 检查全局注册表中是否有该工具的故障
            fault_config = FaultRegistry.get(tool_name)
            if fault_config is not None:
                fault_type, fault_kwargs = fault_config
                # 注入故障，不执行原函数
                return inject_fault(
                    ToolResult(success=True, data={}),
                    fault_type,
                    **fault_kwargs,
                )
            # 无故障，正常执行原函数
            return func(*args, **kwargs)
        return wrapper
    return decorator
