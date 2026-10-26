from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
import datetime
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(current_dir)
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from schemas.attendance import AttendanceResponse, AttendanceUpdateRequest  # type: ignore
from dependencies import get_db, get_session_manager  # type: ignore

router = APIRouter()

ALLOWED_STATUSES = {"Present", "Absent", "Late"}


class AttendanceSubmitRequest(BaseModel):
    teacher_email: Optional[str] = None


def _is_finalized(db, session_manager, session_id: str) -> bool:
    if session_manager and hasattr(session_manager, "is_session_finalized"):
        if session_manager.is_session_finalized(session_id):
            return True
    try:
        res = (
            db.table("class_sessions")
            .select("attendance_finalized")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        if res.data and bool(res.data[0].get("attendance_finalized")):
            return True
    except Exception:
        pass
    return False


def build_roster(db, session_id: str, phase: str = "live"):
    students = db.table("students").select("id,name,roll_number").order("name").execute().data or []
    records = (
        db.table("attendance").select("*").eq("session_id", session_id).execute().data or []
    )
    by_student = {r["student_id"]: r for r in records}

    rows = []
    present = not_yet = absent = 0
    for s in students:
        rec = by_student.get(s["id"])
        if rec:
            status = rec["status"]
            if status == "Present":
                present += 1
            elif status == "Absent":
                absent += 1
            else:
                present += 1
            rows.append(
                {
                    "student_id": s["id"],
                    "name": s["name"],
                    "roll_number": s["roll_number"],
                    "status": status,
                    "attendance_id": rec["id"],
                    "confidence": rec.get("confidence"),
                    "manually_corrected": bool(rec.get("manually_corrected")),
                }
            )
        else:
            if phase == "live":
                status = "Not Yet Detected"
                not_yet += 1
            else:
                status = "Absent"
                absent += 1
            rows.append(
                {
                    "student_id": s["id"],
                    "name": s["name"],
                    "roll_number": s["roll_number"],
                    "status": status,
                    "attendance_id": None,
                    "confidence": None,
                    "manually_corrected": False,
                }
            )

    return {
        "session_id": session_id,
        "phase": phase,
        "registered": len(students),
        "present": present,
        "not_yet_detected": not_yet,
        "absent": absent,
        "students": rows,
    }


@router.get("/{session_id}/roster")
def get_live_roster(
    session_id: str,
    phase: Optional[str] = None,
    db=Depends(get_db),
    session_manager=Depends(get_session_manager),
):
    """
    Live attendance roster for the teacher dashboard.
    During an active session: Present / Not Yet Detected.
    After stop (or phase=review): Present / Absent.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")

    live_id = getattr(session_manager, "session_id", None)
    if phase in ("live", "review"):
        use_phase = phase
    elif live_id == session_id:
        use_phase = "live"
    else:
        use_phase = "review"

    try:
        roster = build_roster(db, session_id, phase=use_phase)
        roster["finalized"] = _is_finalized(db, session_manager, session_id)
        return roster
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/sheet")
def get_attendance_sheet(
    session_id: str,
    db=Depends(get_db),
    session_manager=Depends(get_session_manager),
):
    """
    Live attendance sheet endpoint for test suites and dashboard clients.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")

    live_id = getattr(session_manager, "session_id", None)
    is_live = bool(live_id and live_id == session_id)
    phase = "live" if is_live else "review"

    try:
        roster = build_roster(db, session_id, phase=phase)
        finalized = _is_finalized(db, session_manager, session_id)
        return {
            "session_id": session_id,
            "session_active": is_live,
            "attendance_finalized": finalized,
            "total_registered": roster["registered"],
            "present_count": roster["present"],
            "not_detected_count": roster["not_yet_detected"],
            "absent_count": roster["absent"],
            "records": roster["students"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
def correct_attendance(
    attendance_id: str,
    payload: AttendanceUpdateRequest,
    db=Depends(get_db),
    session_manager=Depends(get_session_manager),
):
    """Teacher manually corrects an attendance status (blocked after submit)."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")
    try:
        existing = db.table("attendance").select("*").eq("id", attendance_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Attendance record not found.")
        session_id = existing.data[0]["session_id"]
        if _is_finalized(db, session_manager, session_id):
            raise HTTPException(status_code=400, detail="Attendance already submitted. Editing is locked.")

        res = (
            db.table("attendance")
            .update({"status": payload.status, "manually_corrected": True})
            .eq("id", attendance_id)
            .execute()
        )
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{session_id}/student/{student_id}")
def upsert_attendance_status(
    session_id: str,
    student_id: str,
    payload: AttendanceUpdateRequest,
    db=Depends(get_db),
    session_manager=Depends(get_session_manager),
):
    """Create or update attendance for a student in review (Present/Absent)."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")
    if _is_finalized(db, session_manager, session_id):
        raise HTTPException(status_code=400, detail="Attendance already submitted. Editing is locked.")

    try:
        existing = (
            db.table("attendance")
            .select("*")
            .eq("session_id", session_id)
            .eq("student_id", student_id)
            .execute()
        )
        if existing.data:
            res = (
                db.table("attendance")
                .update({"status": payload.status, "manually_corrected": True})
                .eq("id", existing.data[0]["id"])
                .execute()
            )
            return res.data[0]

        res = (
            db.table("attendance")
            .insert(
                {
                    "student_id": student_id,
                    "session_id": session_id,
                    "status": payload.status,
                    "confidence": None,
                    "manually_corrected": True,
                }
            )
            .execute()
        )
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/submit")
def submit_attendance(
    session_id: str,
    payload: AttendanceSubmitRequest = AttendanceSubmitRequest(),
    db=Depends(get_db),
    session_manager=Depends(get_session_manager),
):
    """Finalize attendance for the session — locks further normal editing."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")

    if _is_finalized(db, session_manager, session_id):
        return {
            "status": "already_submitted",
            "session_id": session_id,
            "attendance_finalized": True,
            "message": "Attendance has already been finalized for this session.",
        }

    # Ensure every registered student has a row
    students = db.table("students").select("id").execute().data or []
    existing = (
        db.table("attendance").select("student_id").eq("session_id", session_id).execute().data or []
    )
    seen = {r["student_id"] for r in existing}
    for s in students:
        if s["id"] not in seen:
            db.table("attendance").insert(
                {
                    "student_id": s["id"],
                    "session_id": session_id,
                    "status": "Absent",
                    "confidence": None,
                    "manually_corrected": False,
                }
            ).execute()

    submitted_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    persisted = False
    try:
        upd = (
            db.table("class_sessions")
            .update(
                {
                    "attendance_finalized": True,
                    "attendance_submitted_at": submitted_at,
                }
            )
            .eq("id", session_id)
            .execute()
        )
        persisted = bool(upd.data)
    except Exception as e:
        print(f"[Attendance] Could not persist finalized columns (run migration): {e}")

    meta = session_manager.finalize_session(session_id, submitted_at=submitted_at)
    roster = build_roster(db, session_id, phase="review")
    roster["finalized"] = True
    roster["submitted_at"] = submitted_at
    roster["persisted_to_db"] = persisted
    roster["message"] = "Attendance Submitted"

    return {
        "status": "submitted",
        "session_id": session_id,
        "attendance_finalized": True,
        "submitted_at": submitted_at,
        "teacher_email": payload.teacher_email,
        "persisted_to_db": persisted,
        "review": roster,
        "finalize_meta": meta,
        "message": "Attendance Submitted",
    }
