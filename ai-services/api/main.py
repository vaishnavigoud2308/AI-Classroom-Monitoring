from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import threading
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
services_dir = os.path.dirname(current_dir)
att_mon_dir = os.path.join(services_dir, "attention-monitoring")
for path in (att_mon_dir, current_dir, services_dir):
    if path not in sys.path:
        sys.path.insert(0, path)

# Support both `uvicorn main:app` (--app-dir) and package-style imports
try:
    from .routes import health, sessions, students, attendance, alerts, monitoring
    from .dependencies import GLOBAL_CONFIG, GLOBAL_SESSION_MANAGER, get_db
    from .face_registry import rebuild_recognizer, ensure_faces_dir
    from . import runtime as runtime_state
except ImportError:
    from routes import health, sessions, students, attendance, alerts, monitoring
    from dependencies import GLOBAL_CONFIG, GLOBAL_SESSION_MANAGER, get_db
    from face_registry import rebuild_recognizer, ensure_faces_dir
    import runtime as runtime_state

from webcam_monitor import ActivityMonitorApp

app = FastAPI(
    title="AI Classroom Monitoring Backend",
    description="API gateway mapping frontend dashboard requests to backend AI pipelines and Supabase abstractions.",
    version="1.0.0",
)

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(students.router, prefix="/api/students", tags=["Students"])
app.include_router(attendance.router, prefix="/api/attendance", tags=["Attendance"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(monitoring.router, prefix="/api/monitoring", tags=["Monitoring"])

webcam_app = None


@app.on_event("startup")
async def startup_event():
    print("[API] Starting AI Classroom Infrastructure Layer")
    global webcam_app
    ensure_faces_dir()
    webcam_app = ActivityMonitorApp(
        test_mode=False,
        config=GLOBAL_CONFIG,
        session_manager=GLOBAL_SESSION_MANAGER,
    )
    runtime_state.webcam_app = webcam_app

    try:
        db = get_db()
        students_rows = db.table("students").select("*").execute().data or []
        if webcam_app.recognizer:
            info = rebuild_recognizer(webcam_app.recognizer, students_rows)
            print(f"[API] Face model bootstrap: {info}")
    except Exception as e:
        print(f"[API] Face model bootstrap skipped: {e}")

    thread = threading.Thread(target=webcam_app.run, kwargs={"headless": True}, daemon=True)
    thread.start()
    print("[API] Background Webcam Activity Monitor Started")


@app.on_event("shutdown")
async def shutdown_event():
    print("[API] Shutting down infrastructure")
    global webcam_app
    if webcam_app:
        webcam_app.stop()
    runtime_state.webcam_app = None
