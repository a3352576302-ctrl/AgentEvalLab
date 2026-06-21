"""
tests/test_dashboard.py — Dashboard 生成测试
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.dashboard import build_dashboard
from agentevallab.run_store import save_run, RunRecord
from agentevallab.runner import CaseResult


def _add_fake_run(tmpdir, run_id, pass_rate=80, provider="deepseek", model="d"):
    results = [
        CaseResult("A", "a", "functional", passed=pass_rate > 50),
        CaseResult("B", "b", "functional", passed=pass_rate > 66),
        CaseResult("C", "c", "security", passed=True),
    ]
    total = len(results)
    record = RunRecord.from_case_results(results, provider=provider, model=model, run_id=run_id)
    passed_count = sum(1 for r in results if r.passed)
    record.passed = passed_count
    record.failed = total - passed_count
    record.total_cases = total
    return save_run(record, reports_dir=tmpdir)


class TestDashboard:
    """Dashboard 生成"""

    def test_空目录能生成(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            html = build_dashboard(runs_dir=tmpdir)
            assert "Dashboard" in html
            assert "历史运行：0" in html

    def test_有数据能生成(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _add_fake_run(tmpdir, "run-1", pass_rate=67)
            html = build_dashboard(runs_dir=tmpdir)
            assert "Dashboard" in html
            assert "run-1" in html
            assert "历史运行：1" in html

    def test_多模型对比(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _add_fake_run(tmpdir, "ds-1", pass_rate=80, provider="deepseek", model="deepseek-chat")
            _add_fake_run(tmpdir, "mm-1", pass_rate=67, provider="minimax", model="minimax-m2")
            html = build_dashboard(runs_dir=tmpdir)
            assert "deepseek" in html
            assert "minimax" in html

    def test_安全统计(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _add_fake_run(tmpdir, "r1", pass_rate=67, provider="deepseek", model="d")
            html = build_dashboard(runs_dir=tmpdir)
            assert "安全用例" in html

    def test_归因统计不崩溃(self):
        """即使没有归因数据也能正常渲染"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _add_fake_run(tmpdir, "r1", pass_rate=33)
            html = build_dashboard(runs_dir=tmpdir)
            assert "Dashboard" in html

    def test_空运行不崩溃(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            html = build_dashboard(runs_dir=tmpdir)
            assert "Dashboard" in html
