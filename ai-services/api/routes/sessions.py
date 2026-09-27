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

router = APIRouter()


@router.post("/start", response_model=dict, status_code=201)
def start_session(
    request: SessionStartRequest,
    session_manager=Depends(get_session_manager),
):
    """Starts a new live monitoring session and returns the UUID."""
    session_id = session_manager.start_or_get_session(
        teacher_name=request.teacher_name,
        subject=request.subject,
        classroom=request.classroom,
    )
    if session_id == "offline-fallback-session":
        raise HTTPException(status_code=500, detail="Failed to initialize live session through database.")
    return {"session_id": session_id}


@router.post("/{session_id}/stop", response_model=dict)
def stop_session(
    session_id: str,
    db=Depends(get_db),
    session_manager=Depends(get_session_manager),
):
    """Marks a monitoring session as completed and clears the live in-memory session."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")

    end_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        res = db.table("class_sessions").update({"end_time": end_time}).eq("id", session_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Session not found.")

        # Stop webcam processing for this live run
        if getattr(session_manager, "session_id", None) == session_id:
            session_manager.session_id = None

        return {"status": "stopped", "session_id": session_id, "end_time": end_time}
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
