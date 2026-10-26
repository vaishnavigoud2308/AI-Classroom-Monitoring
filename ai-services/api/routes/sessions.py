import datetime
from fastapi import APIRouter, Depends, HTTPException
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(current_dir)
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from schemas.session import SessionStartRequest, SessionResponse  # type: ignore
from dependencies import get_session_manager, get_db  # type: ignore
import runtime as runtime_state  # type: ignore

router = APIRouter()


def _get_webcam_app():
    return getattr(runtime_state, "webcam_app", None)


def _build_roster(db, session_id: str, phase: str = "live"):
    """
    phase=live  -> Present | Not Yet Detected
    phase=review -> Present | Absent (after stop)
    """
    students = db.table("students").select("id,name,roll_number").order("name").execute().data or []
    records = (
        db.table("attendance")
        .select("*")
        .eq("session_id", session_id)
        .execute()
        .data
        or []
    )
    by_student = {r["student_id"]: r for r in records}

    rows = []
    present = 0
    not_yet = 0
    absent = 0
    for s in students:
        rec = by_student.get(s["id"])
        if rec:
            status = rec["status"]
            if status == "Present":
                present += 1
            elif status == "Absent":
                absent += 1
            else:
                # Late etc. count as present-ish for overview
                present += 1
            rows.append(
                {
                    "student_id": s["id"],
                    "name": s["name"],
                    "roll_number": s["roll_number"],
                    "status": status,
                    "attendance_id": rec["id"],
                    "confidence": rec.get("confidence"),
                    "manually_corrected": rec.get("manually_corrected", False),
                }
            )
        else:
            display = "Not Yet Detected" if phase == "live" else "Absent"
            if phase == "live":
                not_yet += 1
            else:
                absent += 1
            rows.append(
                {
                    "student_id": s["id"],
                    "name": s["name"],
                    "roll_number": s["roll_number"],
                    "status": display,
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


def _mark_undetected_absent(db, session_id: str):
    """After stop: create Absent rows for registered students never detected."""
    students = db.table("students").select("id").execute().data or []
    existing = (
        db.table("attendance")
        .select("student_id")
        .eq("session_id", session_id)
        .execute()
        .data
        or []
    )
    seen = {r["student_id"] for r in existing}
    created = 0
    for s in students:
        if s["id"] in seen:
            continue
        db.table("attendance").insert(
            {
                "student_id": s["id"],
                "session_id": session_id,
                "status": "Absent",
                "confidence": None,
                "manually_corrected": False,
            }
        ).execute()
        created += 1
    return created


@router.post("/start", response_model=dict, status_code=201)
def start_session(
    request: SessionStartRequest,
    session_manager=Depends(get_session_manager),
    db=Depends(get_db),
):
    """
    Create classroom session AND start the physical webcam monitoring pipeline.
    Rolls back the session if the webcam cannot open.
    """
    webcam = _get_webcam_app()
    if not webcam:
        raise HTTPException(status_code=503, detail="Webcam monitor is not initialized on the server.")

    # One camera only — stop any previous run before starting
    if webcam.camera_status in ("active", "starting") or (
        webcam._thread and webcam._thread.is_alive()
    ):
        webcam.stop_monitoring()

    session_id = session_manager.start_or_get_session(
        teacher_name=request.teacher_name,
        subject=request.subject,
        classroom=request.classroom,
    )
    if session_id == "offline-fallback-session":
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize live session through database.",
        )

    ok, cam_err = webcam.start_monitoring(headless=True)
    if not ok:
        # Rollback: do not leave a "live" session without a camera
        end_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            db.table("class_sessions").update({"end_time": end_time}).eq("id", session_id).execute()
        except Exception:
            pass
        session_manager.session_id = None
        raise HTTPException(
            status_code=503,
            detail=cam_err
            or "Unable to access webcam. Please close other applications using the camera.",
        )

    cam = webcam.get_camera_status()
    return {
        "session_id": session_id,
        "camera_status": cam["camera_status"],
        "is_monitoring": cam["is_monitoring"],
        "frames_processed": cam["frames_processed"],
        "message": "Live classroom session started. Webcam is capturing.",
    }


@router.post("/{session_id}/stop", response_model=dict)
def stop_session(
    session_id: str,
    db=Depends(get_db),
    session_manager=Depends(get_session_manager),
):
    """
    Stop webcam, release camera, mark undetected students Absent, return review roster.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")

    webcam = _get_webcam_app()
    if webcam:
        webcam.stop_monitoring()

    end_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        res = (
            db.table("class_sessions")
            .update({"end_time": end_time})
            .eq("id", session_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Session not found.")

        if getattr(session_manager, "session_id", None) == session_id:
            session_manager.session_id = None

        absent_created = _mark_undetected_absent(db, session_id)
        roster = _build_roster(db, session_id, phase="review")

        cam = webcam.get_camera_status() if webcam else {"camera_status": "stopped"}

        return {
            "status": "stopped",
            "session_id": session_id,
            "end_time": end_time,
            "camera_status": cam.get("camera_status", "stopped"),
            "absent_marked": absent_created,
            "review": roster,
            "message": "Session stopped. Review attendance, then submit.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-orphans", response_model=dict)
def cleanup_orphan_sessions(db=Depends(get_db), session_manager=Depends(get_session_manager)):
    """Close any class_sessions that still have null end_time (except the live one)."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    end_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    live_id = getattr(session_manager, "session_id", None)
    try:
        query = db.table("class_sessions").update({"end_time": end_time}).is_("end_time", "null")
        if live_id:
            query = query.neq("id", live_id)
        res = query.execute()
        return {"closed": len(res.data or []), "live_session_id": live_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, db=Depends(get_db)):
    """Retrieves session details securely."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    try:
        res = db.table("class_sessions").select("*").eq("id", session_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Session not found.")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
