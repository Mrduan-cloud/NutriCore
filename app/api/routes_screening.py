"""营养风险筛查路由 — NRS2002。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.risk_screening.nrs2002 import compute_nrs2002
from app.agents.risk_screening.report import archive_report
from app.agents.risk_screening.schemas import NRSAnswer, NRSReport
from app.auth import CurrentUser, get_current_user
from app.core.storage import presigned_url
from app.schemas.models import ScreeningRecord

router = APIRouter()


@router.post("/nrs2002", response_model=NRSReport)
async def submit_nrs2002(
    answer: NRSAnswer,
    user: CurrentUser = Depends(get_current_user),
) -> NRSReport:
    try:
        report = compute_nrs2002(user.user_id, answer)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    key = await archive_report(report)
    await ScreeningRecord.create(
        user_id=user.user_id,
        total_score=report.total_score,
        risk_level=report.risk_level,
        pdf_object_key=key,
        payload=report.model_dump(),
    )
    return report


@router.get("/history")
async def history(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    rows = await ScreeningRecord.filter(user_id=user.user_id).order_by("-created_at").limit(20)
    return [
        {
            "id": r.id,
            "total_score": r.total_score,
            "risk_level": r.risk_level,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/{record_id}/report")
async def get_report(record_id: int, user: CurrentUser = Depends(get_current_user)) -> dict:
    rec = await ScreeningRecord.filter(id=record_id, user_id=user.user_id).first()
    if not rec or not rec.pdf_object_key:
        raise HTTPException(404, "report not found")
    url = await presigned_url(rec.pdf_object_key)
    return {"download_url": url}
