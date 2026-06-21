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
        model_alias=req.model_alias,
        endpoint_url=req.endpoint_url,
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


@app.get("/runs/{run_id}/report")
async def get_run_report(run_id: str):
    """返回运行报告（HTML）。"""
    detail = get_run_results(run_id)
    if "error" in detail:
        raise HTTPException(status_code=404, detail=detail["error"])
    from agentevallab.reporter import build_html_report
    # 从数据库结果重建 CaseResult 列表用于报告
    # 简化版：返回元数据摘要
    return {
        "run_id": run_id,
        "report_url": f"/runs/{run_id}/report.html",
        "summary": {
            "total": detail["run"].get("total_cases", 0),
            "passed": detail["run"].get("passed", 0),
            "failed": detail["run"].get("failed", 0),
            "pass_rate": detail["run"].get("pass_rate", 0),
            "created_at": detail["run"].get("created_at", ""),
        },
    }


@app.get("/runs/{run_id}/report.html")
async def get_run_report_html(run_id: str):
    """返回完整 HTML 报告。"""
    from fastapi.responses import HTMLResponse
    from agentevallab.runner import CaseResult
    from agentevallab.trajectory import AgentTrajectory
    from agentevallab.reporter import build_html_report

    detail = get_run_results(run_id)
    if "error" in detail:
        raise HTTPException(status_code=404, detail=detail["error"])

    # 从 DB 结果重建 CaseResult 列表
    results = []
    for c in detail.get("case_results", []):
        traj = AgentTrajectory(
            user_input="",
            final_answer=c.get("final_answer", ""),
            network_latency_ms=c.get("total_latency_ms", 0) or 0,
        )
        traj.prompt_tokens = 0
        traj.completion_tokens = 0
        traj.total_tokens = c.get("total_tokens", 0) or 0
        # 重建 tool_calls
        for tc in c.get("tool_traces", []):
            from agentevallab.trajectory import ToolCall, ToolResult
            res = ToolResult(
                success=bool(tc.get("success")),
                data=tc.get("result_json", {}),
            )
            call = ToolCall(
                tool_name=tc.get("tool_name", ""),
                params=tc.get("params_json", {}),
                result=res,
                latency_ms=tc.get("latency_ms", 0),
            )
            traj.add_tool_call(call)

        cr = CaseResult(
            case_id=c.get("case_id", ""),
            case_name=c.get("case_name", ""),
            category=c.get("category", ""),
            passed=bool(c.get("passed")),
            trajectory=traj,
            error=c.get("error"),
        )
        results.append(cr)

    provider = detail["run"].get("provider", "")
    model = detail["run"].get("model", "")
    title = f"AgentEvalLab 报告 ({provider}/{model})"
    html = build_html_report(results, title=title, provider=provider, model=model)
    return HTMLResponse(content=html)


@app.get("/reviews")
async def list_reviews(status: str | None = None):
    return get_reviews_service(status=status)


@app.post("/reviews/{review_id}")
async def update_review(review_id: int, req: ReviewUpdateRequest):
    update_review_service(review_id, req.reviewer_decision, req.reviewer_note)
    return {"status": "updated"}
