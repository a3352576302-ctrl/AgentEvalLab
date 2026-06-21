"""
agentevallab/review.py — 人工复核逻辑

复核已在 service.py 中自动触发（失败样本 → review_items）。
本模块提供便捷查询函数。
"""
from __future__ import annotations

from agentevallab.repository import list_review_items, update_review_item


def get_pending_reviews(db_path: str | None = None) -> list[dict]:
    """获取待复核样本。"""
    return list_review_items(status="pending", db_path=db_path)


def submit_review(review_id: int, decision: str, note: str = "",
                  db_path: str | None = None) -> None:
    """提交复核结果。"""
    valid_decisions = {
        "correct", "incorrect", "semantic_equivalent",
        "assertion_too_strict", "update_golden_answer", "ignore",
    }
    if decision not in valid_decisions:
        raise ValueError(f"无效的 decision: {decision}，可选: {valid_decisions}")
    update_review_item(review_id, decision, note, db_path)
