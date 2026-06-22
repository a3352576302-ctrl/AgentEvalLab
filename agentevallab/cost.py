"""
agentevallab/cost.py — Token 成本估算

价格可配置，需按供应商最新价格手动校准。
默认使用 2026-06 公开价格（近似值，非实时）。

使用方式：
    from agentevallab.cost import estimate_run_cost, monthly_projection
"""
from __future__ import annotations

from typing import Any

# 价格配置（$ per 1M tokens，2026-06 参考值）
_PRICE_TABLE: dict[str, dict[str, float]] = {
    "deepseek": {
        "deepseek-chat": 0.42,   # output $0.42/M; input 约 $0.14/M，加权取 0.42
    },
    "minimax": {
        "minimax-m2": 1.20,       # output $1.20/M
        "minimax-m3": 1.20,
    },
    "openai": {
        "gpt-4o": 10.00,
        "gpt-4o-mini": 0.60,
    },
}

# 默认每 1M token 价格（找不到时）
_DEFAULT_PRICE = 0.50


def _get_price_per_1m(provider: str, model: str) -> float:
    """获取某模型每百万 token 的价格（$）。"""
    provider_prices = _PRICE_TABLE.get(provider, {})
    if model in provider_prices:
        return provider_prices[model]
    if provider_prices:
        # 返回该 provider 下第一个价格作为默认
        return next(iter(provider_prices.values()))
    return _DEFAULT_PRICE


def estimate_run_cost(
    results: list[dict[str, Any]],
    provider: str = "",
    model: str = "",
) -> dict[str, Any]:
    """从 run JSON results 估算成本。

    参数：
        results  — run JSON 中 results 列表
        provider — provider 名称
        model    — 模型名

    返回：{
        total_tokens, prompt_tokens, completion_tokens,
        estimated_cost_usd, price_per_1m_tokens, provider, model
    }
    """
    price = _get_price_per_1m(provider, model)
    total_prompt = 0
    total_completion = 0
    total_all = 0

    for r in results:
        tp = r.get("prompt_tokens", 0) or 0
        tc = r.get("completion_tokens", 0) or 0
        # run JSON 中字段名为 total_tokens 或 tokens
        tt = r.get("total_tokens", 0) or r.get("tokens", 0) or (tp + tc)
        total_prompt += tp
        total_completion += tc
        total_all += tt

    cost = total_all / 1_000_000 * price

    return {
        "total_tokens": total_all,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "estimated_cost_usd": round(cost, 4),
        "price_per_1m_tokens_usd": price,
        "provider": provider,
        "model": model,
        "note": "价格为可配置估算值，需按供应商最新价格更新",
    }


def monthly_projection(
    cost_per_run: float,
    runs_per_day: list[int] | None = None,
) -> dict[str, Any]:
    """根据每次运行成本推算月成本。

    参数：
        cost_per_run — 单次 226 条评测的成本
        runs_per_day  — 每日运行次数列表，默认 [100, 1000, 10000]

    返回：{"cost_per_run": X, "monthly": {"100/day": Y, ...}}
    """
    daily = runs_per_day or [100, 1000, 10000]
    return {
        "cost_per_run_usd": round(cost_per_run, 4),
        "monthly_projections": {
            f"{d}/day": round(cost_per_run * d * 30, 2)
            for d in daily
        },
        "note": "月成本 = 单次成本 × 每日次数 × 30 天；实际成本随 API 价格波动",
    }
