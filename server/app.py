"""
server/app.py — FastAPI 主程序
"""
from __future__ import annotations

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, HTTPException
from server.schemas import (
    SubmitRunRequest,
    SubmitRunResponse,
    ReviewUpdateRequest,
    HealthResponse,
)
from agentevallab.service import (
    submit_run,
    get_run_status,
    get_run_results,
    list_runs_service,
    get_reviews_service,
    update_review_service,
)

app = FastAPI(title="AgentEvalLab API", version="0.1")


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/runs", response_model=SubmitRunResponse)
async def create_run(req: SubmitRunRequest):
    """提交一次评测运行（同步执行）。"""
    result = submit_run(
        agent_type=req.agent,
        case_ids=req.case_ids,
        provider=req.provider,
        model=req.model,
        repeat=req.repeat,
    )
    return SubmitRunResponse(**result)


@app.get("/runs")
async def list_runs(limit: int = 50):
    return list_runs_service(limit=limit)


@app.get("/runs/{run_id}")
async def get_run_detail(run_id: str):
    status = get_run_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="run not found")
    return status


@app.get("/runs/{run_id}/results")
async def get_run_results_endpoint(run_id: str):
    detail = get_run_results(run_id)
    if "error" in detail:
        raise HTTPException(status_code=404, detail=detail["error"])
    return detail


@app.get("/reviews")
async def list_reviews(status: str | None = None):
    return get_reviews_service(status=status)


@app.post("/reviews/{review_id}")
async def update_review(review_id: int, req: ReviewUpdateRequest):
    update_review_service(review_id, req.reviewer_decision, req.reviewer_note)
    return {"status": "updated"}
