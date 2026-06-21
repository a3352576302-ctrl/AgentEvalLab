"""
tests/test_baseline.py — baseline 回归检测测试
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.baseline import (
    save_baseline,
    load_baseline,
    list_baselines,
    compare_baseline,
    BaselineResult,
)


def _make_run(pass_rate=80.0, results=None, run_id="test-run"):
    """构建模拟 run data。"""
    return {
        "run_id": run_id,
        "pass_rate": pass_rate,
        "total_cases": 10,
        "passed": int(pass_rate / 10),
        "failed": 10 - int(pass_rate / 10),
        "results": results or [],
    }


class TestSaveLoad:
    """保存和加载"""

    def test_保存并加载(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run = _make_run(pass_rate=85.0)
            path = save_baseline("test-v1", run, baselines_dir=tmpdir)
            assert os.path.exists(path)

            loaded = load_baseline("test-v1", baselines_dir=tmpdir)
            assert loaded is not None
            assert loaded["name"] == "test-v1"

    def test_加载不存在的baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert load_baseline("nonexistent", baselines_dir=tmpdir) is None

    def test_列baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_baseline("a", _make_run(), baselines_dir=tmpdir)
            save_baseline("b", _make_run(), baselines_dir=tmpdir)
            assert list_baselines(baselines_dir=tmpdir) == ["a", "b"]


class TestCompare:
    """对比检测"""

    def test_无退化(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_baseline("base", _make_run(pass_rate=80.0), baselines_dir=tmpdir)
            current = _make_run(pass_rate=78.0)  # 下降2%，阈值5%→OK
            result = compare_baseline(current, "base", baselines_dir=tmpdir)
            assert result.is_ok

    def test_通过率下降超阈值(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_baseline("base", _make_run(pass_rate=80.0), baselines_dir=tmpdir)
            current = _make_run(pass_rate=70.0)  # 下降10%
            result = compare_baseline(
                current, "base",
                thresholds={"pass_rate": 5},
                baselines_dir=tmpdir,
            )
            assert result.status == "REGRESSION"

    def test_baseline不存在时OK(self):
        current = _make_run(pass_rate=80.0)
        result = compare_baseline(current, "nonexistent")
        assert result.is_ok

    def test_安全通过率下降(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = _make_run(pass_rate=90.0, results=[
                {"category": "security", "passed": True},
                {"category": "security", "passed": True},
            ])
            cur = _make_run(pass_rate=85.0, results=[
                {"category": "security", "passed": True},
                {"category": "security", "passed": False},
            ])
            save_baseline("base", base, baselines_dir=tmpdir)
            result = compare_baseline(
                cur, "base",
                thresholds={"security": 0},
                baselines_dir=tmpdir,
            )
            assert result.status == "SAFETY_REGRESSION"
