"""
tests/test_db.py — db 层测试
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.db import get_connection, init_schema


class TestDbConnection:
    """连接 + Schema"""

    def test_创建连接并初始化Schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = get_connection(db_path)
            # 验证表已创建
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = [t[0] for t in tables]
            assert "runs" in table_names
            assert "case_results" in table_names
            assert "tool_traces" in table_names
            assert "review_items" in table_names
            conn.close()

    def test_幂等初始化(self):
        """第二次连接不报错"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn1 = get_connection(db_path)
            conn1.close()
            # 第二次仍然正常
            conn2 = get_connection(db_path)
            conn2.close()
