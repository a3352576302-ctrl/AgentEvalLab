"""
tests/test_run_store.py — 运行存储 + 续跑测试
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.runner import CaseResult
from agentevallab.run_store import (
    RunRecord,
    save_run,
    load_run,
    list_runs,
    get_completed_case_ids,
    _generate_run_id,
)
from agentevallab.assertions import AssertionResult, AssertionReport


class TestRunRecord:
    """RunRecord 数据结构"""

    def test_空结果创建记录(self):
        record = RunRecord.from_case_results(
            [], provider="deepseek", model="deepseek-chat",
        )
        assert record.total_cases == 0
        assert record.passed == 0
        assert record.provider == "deepseek"

    def test_混合结果统计正确(self):
        results = [
            CaseResult("A", "a", "functional", passed=True),
            CaseResult("B", "b", "functional", passed=False,
                       error="something went wrong"),
            CaseResult("C", "c", "security", passed=True),
        ]
        record = RunRecord.from_case_results(results)
        assert record.total_cases == 3
        assert record.passed == 2
        assert record.failed == 1


class TestSaveLoad:
    """保存和加载"""

    def test_保存并加载(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                CaseResult("X", "x", "functional", passed=True),
            ]
            record = RunRecord.from_case_results(results, run_id="test-run-1")
            path = save_run(record, reports_dir=tmpdir)
            assert os.path.exists(path)

            loaded = load_run("test-run-1", reports_dir=tmpdir)
            assert loaded is not None
            assert loaded["pass_rate"] == 100.0
            assert loaded["total_cases"] == 1

    def test_加载不存在的运行(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert load_run("nonexistent", reports_dir=tmpdir) is None


class TestListRuns:
    """列出历史运行"""

    def test_空目录无运行(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert list_runs(reports_dir=tmpdir) == []

    def test_列出多个运行(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                record = RunRecord.from_case_results(
                    [], run_id=f"run-{i}",
                )
                save_run(record, reports_dir=tmpdir)
            runs = list_runs(reports_dir=tmpdir)
            assert len(runs) == 3


class TestResume:
    """续跑"""

    def test_获取已完成用例ID(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [
                CaseResult("FUNC-001", "a", "functional", passed=True),
                CaseResult("FUNC-002", "b", "functional", passed=False),
            ]
            record = RunRecord.from_case_results(results, run_id="run-resume")
            save_run(record, reports_dir=tmpdir)

            completed = get_completed_case_ids("run-resume", reports_dir=tmpdir)
            assert "FUNC-001" in completed
            assert "FUNC-002" in completed


class TestRunId:
    """run_id 生成"""

    def test_唯一性(self):
        ids = [_generate_run_id() for _ in range(10)]
        assert len(set(ids)) == 10
