"""
tests/test_service_api.py — FastAPI 接口测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from server.app import app

client = TestClient(app)


class TestHealth:
    def test_健康检查(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestRuns:
    def test_提交Run并查询(self):
        resp = client.post("/runs", json={
            "agent": "rule",
            "case_ids": ["FUNC-001"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "completed"

        # 查询详情
        run_id = data["run_id"]
        resp2 = client.get(f"/runs/{run_id}")
        assert resp2.status_code == 200
        assert resp2.json()["run_id"] == run_id

    def test_结果查询(self):
        resp = client.post("/runs", json={
            "agent": "rule",
            "case_ids": ["FUNC-001", "FUNC-002"],
        })
        run_id = resp.json()["run_id"]
        resp2 = client.get(f"/runs/{run_id}/results")
        assert resp2.status_code == 200
        assert "case_results" in resp2.json()
        assert len(resp2.json()["case_results"]) >= 1

    def test_列运行列表(self):
        client.post("/runs", json={"agent": "rule", "case_ids": ["FUNC-001"]})
        resp = client.get("/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_不存在的Run返回404(self):
        resp = client.get("/runs/nonexistent")
        assert resp.status_code == 404


class TestReviews:
    def test_获取复核列表(self):
        client.post("/runs", json={
            "agent": "rule",
            "case_ids": ["FUNC-001", "FUNC-004"],
        })
        resp = client.get("/reviews")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_更新复核状态(self):
        client.post("/runs", json={
            "agent": "rule",
            "case_ids": ["FUNC-001", "FUNC-004"],
        })
        reviews = client.get("/reviews").json()
        if reviews:
            rid = reviews[0]["id"]
            resp = client.post(f"/reviews/{rid}", json={
                "reviewer_decision": "assertion_too_strict",
                "reviewer_note": "格式差异",
            })
            assert resp.status_code == 200
