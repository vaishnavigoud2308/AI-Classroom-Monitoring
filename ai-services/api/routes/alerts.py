from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(current_dir)
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from schemas.alert import AlertResponse, AlertUpdateRequest  # type: ignore
from dependencies import get_db  # type: ignore

router = APIRouter()

ALLOWED_STATUSES = {"New", "Reviewed", "Dismissed"}


@router.get("/{session_id}", response_model=List[AlertResponse])
def get_session_alerts(
    session_id: str,
    status: Optional[str] = None,
    alert_type: Optional[str] = None,
    db=Depends(get_db),
):
    """Retrieve all alerts for a given monitoring session."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    try:
        query = db.table("classroom_alerts").select("*").eq("session_id", session_id).order("created_at", desc=True)
        if status:
            query = query.eq("status", status)
        if alert_type:
            query = query.eq("alert_type", alert_type)
        res = query.execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/item/{alert_id}", response_model=AlertResponse)
def update_alert_status(alert_id: str, payload: AlertUpdateRequest, db=Depends(get_db)):
    """Teacher review/dismiss an alert."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")
    try:
        res = (
            db.table("classroom_alerts")
            .update({"status": payload.status})
            .eq("id", alert_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Alert not found.")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
