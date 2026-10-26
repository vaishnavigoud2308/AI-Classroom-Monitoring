from fastapi import APIRouter, Depends, HTTPException
from typing import List
import base64
import os
import re
import sys

import cv2
import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(current_dir)
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from schemas.student import StudentResponse, StudentCreateRequest  # type: ignore
from dependencies import get_db  # type: ignore
from face_registry import (  # type: ignore
    face_path_for_student,
    rebuild_recognizer,
    ensure_faces_dir,
    resolve_face_path,
)
import runtime as runtime_state  # type: ignore
from fastapi.responses import FileResponse

router = APIRouter()


def _get_webcam_app():
    return getattr(runtime_state, "webcam_app", None)


def _decode_image(face_image_base64: str) -> np.ndarray:
    raw = face_image_base64.strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        binary = base64.b64decode(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")
    arr = np.frombuffer(binary, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Could not decode face image.")
    return img


def _retrain_from_db(db) -> dict:
    app = _get_webcam_app()
    if not app or not getattr(app, "recognizer", None):
        return {"trained": False, "reason": "recognizer unavailable"}
    students = db.table("students").select("*").execute().data or []
    return rebuild_recognizer(app.recognizer, students)


@router.get("/", response_model=List[StudentResponse])
def list_students(db=Depends(get_db)):
    """Retrieve a list of all registered students."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    try:
        res = db.table("students").select("*").order("created_at").execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{student_id}/face")
def get_student_face(student_id: str, db=Depends(get_db)):
    """Serve the enrolled face image used by LBPH attendance matching."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    res = db.table("students").select("id,face_image_url").eq("id", student_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Student not found.")
    path = resolve_face_path(res.data[0].get("face_image_url"), student_id)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Enrolled face image not found.")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/{student_id}", response_model=StudentResponse)
def get_student(student_id: str, db=Depends(get_db)):
    """Retrieve details for a specific student."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    try:
        res = db.table("students").select("*").eq("id", student_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Student not found.")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=StudentResponse, status_code=201)
def create_student(payload: StudentCreateRequest, db=Depends(get_db)):
    """
    Create a student, save an enrolled face image locally, and retrain LBPH.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")

    name = payload.name.strip()
    roll = payload.roll_number.strip()
    if not name or not roll:
        raise HTTPException(status_code=400, detail="name and roll_number are required.")
    if not re.match(r"^[\w\-]+$", roll):
        raise HTTPException(status_code=400, detail="roll_number must be alphanumeric.")

    img = _decode_image(payload.face_image_base64)

    # Quick face presence check before DB insert
    app = _get_webcam_app()
    if app and getattr(app, "recognizer", None):
        roi = app.recognizer._extract_face_roi(frame=img)
        if roi is None:
            raise HTTPException(status_code=400, detail="No face detected in the captured image. Try again with clearer lighting.")

    row = {
        "name": name,
        "roll_number": roll,
        "email": payload.email.strip() if payload.email else None,
    }
    try:
        insert_res = db.table("students").insert(row).execute()
        if not insert_res.data:
            raise HTTPException(status_code=500, detail="Student insert returned no data.")
        student = insert_res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not create student (duplicate roll/email?): {e}")

    ensure_faces_dir()
    path = face_path_for_student(student["id"])
    if not cv2.imwrite(path, img):
        db.table("students").delete().eq("id", student["id"]).execute()
        raise HTTPException(status_code=500, detail="Failed to save face image.")

    rel = f"ai-services/data/faces/{student['id']}.jpg"
    try:
        updated = (
            db.table("students")
            .update({"face_image_url": rel})
            .eq("id", student["id"])
            .execute()
        )
        student = updated.data[0] if updated.data else {**student, "face_image_url": rel}
    except Exception:
        student["face_image_url"] = rel

    train_info = _retrain_from_db(db)
    # Attach train info is not in schema; log only
    print(f"[Students] Enrolled {name}. Retrain: {train_info}")
    return student


@router.post("/retrain", response_model=dict)
def retrain_faces(db=Depends(get_db)):
    """Force rebuild of the in-memory LBPH model from enrolled faces."""
    if not db:
        raise HTTPException(status_code=500, detail="Database connection missing.")
    try:
        return _retrain_from_db(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
