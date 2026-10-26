from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
services_dir = os.path.dirname(current_dir)
att_mon_dir = os.path.join(services_dir, "attention-monitoring")
alert_dir = os.path.join(services_dir, "alert-engine")
audio_dir = os.path.join(services_dir, "audio-monitoring")
face_dir = os.path.join(services_dir, "face-recognition")
for path in (att_mon_dir, alert_dir, audio_dir, face_dir, current_dir, services_dir):
    if path not in sys.path:
        sys.path.insert(0, path)

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

# Parse any additional production origins from environment variables (comma-separated)
custom_origins_raw = os.environ.get("ALLOWED_ORIGINS") or os.environ.get("CORS_ORIGINS") or ""
custom_origins = [o.strip() for o in custom_origins_raw.split(",") if o.strip()]

default_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:8080",
]

origins = list(dict.fromkeys(default_origins + custom_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$",
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
    """
    Load AI models and prepare the monitor.
    Physical webcam is NOT opened here — Start Session opens it.
    """
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

    print("[API] Models ready. Webcam will open when teacher starts a session.")


@app.on_event("shutdown")
async def shutdown_event():
    print("[API] Shutting down infrastructure")
    global webcam_app
    if webcam_app:
        webcam_app.stop_monitoring()
    runtime_state.webcam_app = None


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"[API] Starting server on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)
