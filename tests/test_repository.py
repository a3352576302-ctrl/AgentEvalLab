"""
tests/test_repository.py — repository 层测试
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.repository import (
    init_storage,
    save_run_record,
    get_run,
    list_runs_db,
    save_case_result,
    list_case_results,
    save_tool_trace,
    list_tool_traces,
    create_review_item,
    list_review_items,
    update_review_item,
)
from agentevallab.run_store import RunRecord
from agentevallab.runner import CaseResult
from agentevallab.trajectory import AgentTrajectory, ToolCall, ToolResult


def _make_tmp_db():
    td = tempfile.TemporaryDirectory()
    db_path = os.path.join(td.name, "test.db")
    init_storage(db_path)
    return db_path, td


class TestRunStorage:
    """Run 存储"""

    def test_保存并获取Run(self):
        db_path, td = _make_tmp_db()
        record = RunRecord.from_case_results(
            [CaseResult("A", "a", "functional", passed=True)],
            run_id="r1", provider="deepseek", model="d",
        )
        save_run_record(record, db_path)
        r = get_run("r1", db_path)
        assert r is not None
        assert r["run_id"] == "r1"
        assert r["provider"] == "deepseek"
        td.cleanup()

    def test_列表多个Run(self):
        db_path, td = _make_tmp_db()
        for rid in ["r1", "r2", "r3"]:
            record = RunRecord.from_case_results([], run_id=rid)
            save_run_record(record, db_path)
        runs = list_runs_db(limit=10, db_path=db_path)
        assert len(runs) == 3
        td.cleanup()


class TestCaseResultStorage:
    """CaseResult 存储"""

    def test_保存并查询(self):
        db_path, td = _make_tmp_db()
        record = RunRecord.from_case_results([], run_id="r1")
        save_run_record(record, db_path)

        cr = CaseResult("FUNC-001", "test", "functional", passed=True,
                         trajectory=AgentTrajectory(user_input="hi",
                                                    final_answer="hello"))
        save_case_result("r1", cr, db_path)
        results = list_case_results("r1", db_path)
        assert len(results) == 1
        assert results[0]["case_id"] == "FUNC-001"
        td.cleanup()


class TestToolTraceStorage:
    """ToolTrace 存储"""

    def test_保存轨迹(self):
        db_path, td = _make_tmp_db()
        record = RunRecord.from_case_results([], run_id="r1")
        save_run_record(record, db_path)

        traj = AgentTrajectory(user_input="hi")
        traj.add_tool_call(ToolCall(
            tool_name="weather", params={"city": "北京"},
            result=ToolResult(success=True, data={"temp": 35}),
        ))
        save_tool_trace("r1", "FUNC-001", traj, db_path)
        traces = list_tool_traces("r1", "FUNC-001", db_path)
        assert len(traces) == 1
        assert traces[0]["tool_name"] == "weather"
        td.cleanup()


class TestReviewStorage:
    """Review 存储"""

    def test_创建更新查询(self):
        db_path, td = _make_tmp_db()
        record = RunRecord.from_case_results([], run_id="r1")
        save_run_record(record, db_path)

        rid = create_review_item("r1", "FUNC-002", reason="L2失败",
                                 auto_failure_taxonomy=["TOOL_SEQUENCE_MISMATCH"],
                                 db_path=db_path)
        items = list_review_items(db_path=db_path)
        assert len(items) == 1
        assert items[0]["status"] == "pending"

        update_review_item(rid, "semantic_equivalent", "表达差异", db_path)
        items2 = list_review_items(status="reviewed", db_path=db_path)
        assert len(items2) == 1
        td.cleanup()
