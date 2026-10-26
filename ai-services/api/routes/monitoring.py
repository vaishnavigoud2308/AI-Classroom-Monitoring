from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
import os
import sys
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(current_dir)
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from schemas.monitoring import MonitoringConfigSchema, MonitoringStatusSchema  # type: ignore
from dependencies import get_monitoring_config, get_session_manager  # type: ignore
import runtime as runtime_state  # type: ignore

router = APIRouter()


@router.get("/config", response_model=MonitoringConfigSchema)
def get_config(config=Depends(get_monitoring_config)):
    """Provides current state of feature toggles."""
    return MonitoringConfigSchema(
        attendance_enabled=config.attendance_enabled,
        phone_detection_enabled=config.phone_detection_enabled,
        talking_detection_enabled=config.talking_detection_enabled,
        audio_monitoring_enabled=getattr(config, "audio_monitoring_enabled", True),
        sleeping_detection_enabled=config.sleeping_detection_enabled,
        looking_away_detection_enabled=config.looking_away_detection_enabled,
        unnecessary_activity_enabled=config.unnecessary_activity_enabled,
    )


@router.put("/config", response_model=MonitoringConfigSchema)
def update_config(updates: MonitoringConfigSchema, config=Depends(get_monitoring_config)):
    """Dynamically applies toggle states to active monitoring backend."""
    config.attendance_enabled = updates.attendance_enabled
    config.phone_detection_enabled = updates.phone_detection_enabled
    config.talking_detection_enabled = updates.talking_detection_enabled
    config.audio_monitoring_enabled = updates.audio_monitoring_enabled
    config.sleeping_detection_enabled = updates.sleeping_detection_enabled
    config.looking_away_detection_enabled = updates.looking_away_detection_enabled
    config.unnecessary_activity_enabled = updates.unnecessary_activity_enabled
    return get_config(config)


@router.get("/status", response_model=MonitoringStatusSchema)
def get_status(
    config=Depends(get_monitoring_config),
    session_manager=Depends(get_session_manager),
):
    """Reflects live monitoring + real webcam status."""
    session_id = session_manager.session_id
    if session_id in (None, "", "offline-fallback-session", "test-mock-session"):
        session_id = None

    cam = {
        "camera_status": "stopped",
        "camera_error": None,
        "frames_processed": 0,
        "last_frame_at": None,
        "is_monitoring": False,
        "recognizer_trained": False,
        "last_recognized": None,
        "audio_status": "stopped",
        "audio_error": None,
        "current_sound_level_db": 0.0,
        "smoothed_sound_level_db": 0.0,
    }
    app = getattr(runtime_state, "webcam_app", None)
    if app and hasattr(app, "get_camera_status"):
        cam = app.get_camera_status()

    features = MonitoringConfigSchema(
        attendance_enabled=config.attendance_enabled,
        phone_detection_enabled=config.phone_detection_enabled,
        talking_detection_enabled=config.talking_detection_enabled,
        audio_monitoring_enabled=getattr(config, "audio_monitoring_enabled", True),
        sleeping_detection_enabled=config.sleeping_detection_enabled,
        looking_away_detection_enabled=config.looking_away_detection_enabled,
        unnecessary_activity_enabled=config.unnecessary_activity_enabled,
    )

    is_active = bool(session_id) and bool(cam.get("is_monitoring"))

    return MonitoringStatusSchema(
        is_active=is_active,
        current_session_id=session_id,
        enabled_features=features,
        camera_status=cam.get("camera_status") or "stopped",
        camera_error=cam.get("camera_error"),
        audio_status=cam.get("audio_status") or "stopped",
        audio_error=cam.get("audio_error"),
        current_sound_level_db=float(cam.get("current_sound_level_db") or 0.0),
        smoothed_sound_level_db=float(cam.get("smoothed_sound_level_db") or 0.0),
        frames_processed=int(cam.get("frames_processed") or 0),
        last_frame_at=cam.get("last_frame_at"),
        is_monitoring=bool(cam.get("is_monitoring")),
        recognizer_trained=bool(cam.get("recognizer_trained")),
        last_recognized=cam.get("last_recognized"),
    )


@router.get("/stream")
def live_camera_stream():
    """
    MJPEG stream of the SAME backend webcam frames used for recognition.
    Browser displays this without opening a second camera.
    """
    app = getattr(runtime_state, "webcam_app", None)
    if not app:
        raise HTTPException(status_code=503, detail="Webcam monitor not initialized.")

    def generate():
        idle_jpeg = None
        while True:
            jpeg = app.get_preview_jpeg() if hasattr(app, "get_preview_jpeg") else None
            if jpeg:
                idle_jpeg = jpeg
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            elif idle_jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + idle_jpeg + b"\r\n"
                )
            time.sleep(0.08)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/preview.jpg")
def live_preview_snapshot():
    """Single JPEG snapshot of the latest processed classroom frame."""
    app = getattr(runtime_state, "webcam_app", None)
    if not app or not hasattr(app, "get_preview_jpeg"):
        raise HTTPException(status_code=503, detail="Webcam monitor not initialized.")
    jpeg = app.get_preview_jpeg()
    if not jpeg:
        raise HTTPException(status_code=404, detail="No live frame yet. Start a session first.")
    return Response(content=jpeg, media_type="image/jpeg")


@router.post("/audio/start", response_model=dict)
def start_audio_monitoring(
    session_manager=Depends(get_session_manager),
    config=Depends(get_monitoring_config),
):
    """Starts standalone audio monitoring for the active classroom session."""
    session_id = session_manager.session_id
    if not session_id or session_id in ("offline-fallback-session", "test-mock-session"):
        raise HTTPException(
            status_code=400,
            detail="Cannot start audio monitoring without an active classroom session.",
        )

    app = getattr(runtime_state, "webcam_app", None) or runtime_state.get_or_init_webcam_app()
    if not app or not getattr(app, "audio_monitor", None):
        raise HTTPException(status_code=503, detail="Audio monitor not initialized.")

    config.audio_monitoring_enabled = True
    ok, err = app.audio_monitor.start_monitoring(session_id=session_id)
    stat = app.audio_monitor.get_status()
    return {
        "ok": ok,
        "session_id": session_id,
        "audio_status": stat.get("audio_status"),
        "audio_error": stat.get("audio_error") or err,
        "current_sound_level_db": stat.get("current_sound_level_db", 0.0),
        "smoothed_sound_level_db": stat.get("smoothed_sound_level_db", 0.0),
    }


@router.post("/audio/stop", response_model=dict)
def stop_audio_monitoring():
    """Safely stops audio monitoring and releases microphone resources."""
    app = getattr(runtime_state, "webcam_app", None) or runtime_state.get_or_init_webcam_app()
    if app and getattr(app, "audio_monitor", None):
        app.audio_monitor.stop_monitoring()
        stat = app.audio_monitor.get_status()
    else:
        stat = {"audio_status": "stopped", "audio_error": None}
    return {
        "ok": True,
        "audio_status": stat.get("audio_status", "stopped"),
        "message": "Audio monitoring stopped.",
    }


@router.get("/audio/status", response_model=dict)
def get_audio_status():
    """Provides granular real-time audio monitoring diagnostics."""
    app = getattr(runtime_state, "webcam_app", None) or runtime_state.get_or_init_webcam_app()
    if app and getattr(app, "audio_monitor", None):
        return app.audio_monitor.get_status()
    return {
        "audio_status": "stopped",
        "audio_error": None,
        "is_monitoring": False,
        "current_sound_level_db": 0.0,
        "smoothed_sound_level_db": 0.0,
        "speech_detected": False,
        "confidence": 0.0,
        "episodes_in_window": 0,
        "session_id": None,
    }

