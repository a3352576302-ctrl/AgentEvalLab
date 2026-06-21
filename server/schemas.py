"""
server/schemas.py — Pydantic 请求/响应模型
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SubmitRunRequest(BaseModel):
    agent: str = Field(default="rule", description="rule / llm / http")
    case_ids: list[str] | None = Field(default=None, description="用例ID列表")
    provider: str = Field(default="auto")
    model: str = Field(default="")
    model_alias: str | None = None
    endpoint_url: str | None = Field(default=None, description="HTTP Agent 端点")
    repeat: int = Field(default=1, ge=1, le=10)


class SubmitRunResponse(BaseModel):
    run_id: str
    status: str
    total_cases: int | None = None
    passed: int | None = None
    failed: int | None = None


class ReviewUpdateRequest(BaseModel):
    reviewer_decision: str = Field(..., description="correct/incorrect/semantic_equivalent/assertion_too_strict")
    reviewer_note: str = Field(default="")


class HealthResponse(BaseModel):
    status: str = "ok"
