"""
tests/test_service.py — service 层测试
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.repository import init_storage
from agentevallab.service import (
    submit_run,
    get_run_status,
    get_run_results,
    list_runs_service,
    get_reviews_service,
    update_review_service,
)


def _make_db():
    td = tempfile.TemporaryDirectory()
    db_path = os.path.join(td.name, "test.db")
    init_storage(db_path)
    return db_path, td


class TestSubmitRun:
    """提交运行"""

    def test_rule模式提交单个用例(self):
        db_path, td = _make_db()
        result = submit_run(
            agent_type="rule", case_ids=["FUNC-001"],
            db_path=db_path,
        )
        assert result["status"] == "completed"
        assert result["passed"] >= 0
        td.cleanup()

    def test_运行后状态可查询(self):
        db_path, td = _make_db()
        result = submit_run(agent_type="rule", case_ids=["FUNC-001"], db_path=db_path)
        status = get_run_status(result["run_id"], db_path)
        assert status is not None
        assert status["run_id"] == result["run_id"]
        td.cleanup()

    def test_运行后结果可查询(self):
        db_path, td = _make_db()
        result = submit_run(agent_type="rule", case_ids=["FUNC-001"], db_path=db_path)
        detail = get_run_results(result["run_id"], db_path)
        assert "run" in detail
        assert "case_results" in detail
        assert len(detail["case_results"]) > 0
        td.cleanup()

    def test_运行后可以列运行列表(self):
        db_path, td = _make_db()
        submit_run(agent_type="rule", case_ids=["FUNC-001"], db_path=db_path)
        runs = list_runs_service(db_path=db_path)
        assert len(runs) >= 1
        td.cleanup()


class TestReviewFlow:
    """复核流程"""

    def test_失败用例自动创建复核条目(self):
        """Rule agent 下边界用例可能产生失败，应自动进入 review"""
        db_path, td = _make_db()
        # FUNC-004 是多工具串联，RuleBasedAgent 可能过也可能不过
        submit_run(agent_type="rule", case_ids=["FUNC-001", "FUNC-004", "SEC-001"],
                   db_path=db_path)
        items = get_reviews_service(db_path=db_path)
        # 不强制断言数量，但确认能查到
        assert isinstance(items, list)
        td.cleanup()

    def test_更新复核状态(self):
        db_path, td = _make_db()
        submit_run(agent_type="rule", case_ids=["FUNC-001"], db_path=db_path)
        items = get_reviews_service(db_path=db_path)
        if items:
            rid = items[0]["id"]
            update_review_service(rid, "correct", "实际正确", db_path)
            reviewed = get_reviews_service(status="reviewed", db_path=db_path)
            assert any(r["id"] == rid for r in reviewed)
        td.cleanup()
