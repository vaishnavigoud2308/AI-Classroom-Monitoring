"""Shared runtime handles for the live webcam / audio / recognizer process."""
from __future__ import annotations

import os
import sys
from typing import Optional, Any

webcam_app: Optional[Any] = None


def get_or_init_webcam_app() -> Optional[Any]:
    global webcam_app
    if webcam_app is None:
        try:
            # Ensure path resolution
            current_dir = os.path.dirname(os.path.abspath(__file__))
            services_dir = os.path.dirname(current_dir)
            att_mon_dir = os.path.join(services_dir, "attention-monitoring")
            for p in (att_mon_dir, current_dir, services_dir):
                if p not in sys.path:
                    sys.path.insert(0, p)

            try:
                from dependencies import GLOBAL_CONFIG, GLOBAL_SESSION_MANAGER
            except ImportError:
                from api.dependencies import GLOBAL_CONFIG, GLOBAL_SESSION_MANAGER

            from webcam_monitor import ActivityMonitorApp

            webcam_app = ActivityMonitorApp(
                test_mode=False,
                config=GLOBAL_CONFIG,
                session_manager=GLOBAL_SESSION_MANAGER,
            )
        except Exception as e:
            print(f"[runtime] Lazy init webcam_app failed: {e}")
    return webcam_app


def is_monitoring_active() -> bool:
    if webcam_app is None:
        return False
    status = getattr(webcam_app, "camera_status", None)
    thread = getattr(webcam_app, "_thread", None)
    return status == "active" or (thread is not None and thread.is_alive())


def stop_monitoring_pipeline() -> None:
    global webcam_app
    if webcam_app is not None:
        try:
            webcam_app.stop_monitoring()
        except Exception as e:
            print(f"[runtime] Error stopping monitoring pipeline: {e}")


def get_audio_monitor() -> Optional[Any]:
    if webcam_app and hasattr(webcam_app, "audio_monitor"):
        return webcam_app.audio_monitor
    return None
