"""
tests/test_cost.py — 成本估算测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.cost import estimate_run_cost, monthly_projection


def _make_result(**kw):
    return {"prompt_tokens": kw.get("p", 500),
            "completion_tokens": kw.get("c", 300),
            "total_tokens": kw.get("t", 800)}


class TestEstimateCost:
    def test_正常计算(self):
        results = [_make_result() for _ in range(10)]  # 10 cases, 8000 tokens
        r = estimate_run_cost(results, provider="deepseek", model="deepseek-chat")
        assert r["total_tokens"] == 8000
        assert r["estimated_cost_usd"] == round(8000 / 1_000_000 * 0.42, 4)

    def test_空结果(self):
        r = estimate_run_cost([], provider="deepseek", model="deepseek-chat")
        assert r["total_tokens"] == 0
        assert r["estimated_cost_usd"] == 0.0

    def test_未知provider使用默认价格(self):
        r = estimate_run_cost([_make_result()], provider="unknown", model="?")
        assert r["total_tokens"] == 800
        assert r["estimated_cost_usd"] >= 0

    def test_缺失token字段不崩溃(self):
        r = estimate_run_cost([{"case_id": "X"}], provider="deepseek", model="x")
        assert r["total_tokens"] == 0


class TestMonthlyProjection:
    def test_月成本估算(self):
        p = monthly_projection(0.05, [100, 1000])
        assert p["cost_per_run_usd"] == 0.05
        assert p["monthly_projections"]["100/day"] == 150.0   # 0.05 * 100 * 30
        assert p["monthly_projections"]["1000/day"] == 1500.0

    def test_默认日运行量(self):
        p = monthly_projection(0.01)
        assert "100/day" in p["monthly_projections"]
        assert "10000/day" in p["monthly_projections"]
