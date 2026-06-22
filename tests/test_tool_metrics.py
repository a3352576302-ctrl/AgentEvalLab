"""
tests/test_tool_metrics.py — 工具调用统计测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.tool_metrics import compute_tool_metrics


def _tc(name, success=True, params=None):
    return {"tool_name": name, "success": success, "params_json": params or {}}


def _result(cid, *tool_calls, **kw):
    tc = [{"tool_name": t.get("tool_name", "?"),
           "success": t.get("success", True),
           "params_json": t.get("params_json", {})}
          for t in tool_calls] if isinstance(tool_calls[0], dict) else []
    assertions = kw.get("assertions", [])
    return {"case_id": cid, "tool_calls": tc, "assertions": assertions}


class TestToolMetrics:
    def test_空结果(self):
        m = compute_tool_metrics([])
        assert m["global"]["total_tool_calls"] == 0

    def test_单工具成功(self):
        m = compute_tool_metrics([_result("A", _tc("weather"))])
        assert m["global"]["total_tool_calls"] == 1
        assert m["global"]["success_rate"] == 100.0

    def test_工具失败统计(self):
        m = compute_tool_metrics([
            _result("A", _tc("weather", True)),
            _result("B", _tc("weather", False)),
        ])
        assert m["global"]["failed"] == 1
        assert m["by_tool"]["weather"]["failure_count"] == 1

    def test_重复调用检测(self):
        m = compute_tool_metrics([
            _result("A", _tc("weather"), _tc("weather")),
        ])
        assert m["global"]["duplicate_calls"] >= 1
        assert len(m["cases_with_duplicate_ids"]) >= 1

    def test_不同case相同工具不算重复(self):
        m = compute_tool_metrics([
            _result("A", _tc("weather")),
            _result("B", _tc("weather")),
        ])
        assert m["global"]["duplicate_calls"] == 0
        assert m["by_tool"]["weather"]["call_count"] == 2

    def test_按工具统计(self):
        m = compute_tool_metrics([
            _result("A", _tc("weather"), _tc("knowledge")),
            _result("B", _tc("weather")),
        ])
        assert m["by_tool"]["weather"]["call_count"] == 2
        assert m["by_tool"]["knowledge"]["call_count"] == 1

    def test_max_rounds失败统计(self):
        m = compute_tool_metrics([
            _result("A", _tc("knowledge"), _tc("knowledge"),
                    assertions=[{"name": "轮次检查", "passed": False}]),
        ])
        assert m["global"]["max_rounds_failures"] == 1
        assert m["max_rounds_failure_ids"] == ["A"]
