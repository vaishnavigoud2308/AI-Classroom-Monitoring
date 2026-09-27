"""Rebuild the live FaceRecognizer from enrolled face images on disk + Supabase students."""
from __future__ import annotations

import os
import threading
from typing import Any, Optional

FACES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "faces",
)

_lock = threading.Lock()


def ensure_faces_dir() -> str:
    os.makedirs(FACES_DIR, exist_ok=True)
    return FACES_DIR


def face_path_for_student(student_id: str) -> str:
    ensure_faces_dir()
    return os.path.join(FACES_DIR, f"{student_id}.jpg")


def resolve_face_path(face_image_url: Optional[str], student_id: str) -> Optional[str]:
    """Resolve a stored face_image_url or default local enrolled path."""
    candidates = []
    if face_image_url:
        if os.path.isabs(face_image_url) and os.path.exists(face_image_url):
            return face_image_url
        # Relative to project / faces dir
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates.append(os.path.join(project_root, face_image_url))
        candidates.append(os.path.join(FACES_DIR, os.path.basename(face_image_url)))
        candidates.append(face_image_url)
    candidates.append(face_path_for_student(student_id))

    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def rebuild_recognizer(recognizer: Any, students: list[dict]) -> dict:
    """
    Reset and retrain the shared FaceRecognizer from student rows that have face images.
    Thread-safe against the webcam loop.
    """
    ensure_faces_dir()
    registered = 0
    skipped = 0

    with _lock:
        recognizer.current_int_label = 0
        recognizer.label_to_uuid = {}
        recognizer.uuid_to_details = {}
        recognizer.faces_data = []
        recognizer.labels_data = []
        recognizer.is_trained = False

        for student in students:
            sid = student.get("id")
            if not sid:
                skipped += 1
                continue
            path = resolve_face_path(student.get("face_image_url"), sid)
            if not path:
                skipped += 1
                continue
            ok = recognizer.register_student(
                student_id=sid,
                name=student.get("name") or "Unknown",
                roll_number=student.get("roll_number") or "",
                image_path=path,
            )
            if ok:
                registered += 1
            else:
                skipped += 1

        trained = False
        if registered > 0:
            trained = bool(recognizer.train_model())

    return {
        "registered": registered,
        "skipped": skipped,
        "trained": trained,
        "is_trained": bool(getattr(recognizer, "is_trained", False)),
    }
