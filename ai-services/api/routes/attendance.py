from fastapi import APIRouter, Depends, HTTPException
from typing import List
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(current_dir)
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from schemas.attendance import AttendanceResponse, AttendanceUpdateRequest  # type: ignore
from dependencies import get_db  # type: ignore

router = APIRouter()

ALLOWED_STATUSES = {"Present", "Absent", "Late"}


@router.get("/{session_id}", response_model=List[AttendanceResponse])
def get_session_attendance(session_id: str, db=Depends(get_db)):
    """Retrieve all attendance records for a specific monitoring session."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    try:
        res = (
            db.table("attendance")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/item/{attendance_id}", response_model=AttendanceResponse)
def correct_attendance(attendance_id: str, payload: AttendanceUpdateRequest, db=Depends(get_db)):
    """Teacher manually corrects an attendance status."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")
    try:
        res = (
            db.table("attendance")
            .update({"status": payload.status, "manually_corrected": True})
            .eq("id", attendance_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Attendance record not found.")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
