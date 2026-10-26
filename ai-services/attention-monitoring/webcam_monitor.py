import cv2
import time
import argparse
import sys
import os
from datetime import datetime
import threading

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from activity_detector import ClassroomActivityDetector
from monitoring_config import MonitoringConfig
from session_manager import MonitoringSessionManager

alert_dir = os.path.join(parent_dir, "alert-engine")
if alert_dir not in sys.path:
    sys.path.insert(0, alert_dir)
from alert_engine import AlertEngine

audio_dir = os.path.join(parent_dir, "audio-monitoring")
if audio_dir not in sys.path:
    sys.path.insert(0, audio_dir)
from talking_tracker import TalkingTracker
from audio_monitor import AudioMonitor

face_rec_dir = os.path.join(parent_dir, "face-recognition")
if face_rec_dir not in sys.path:
    sys.path.insert(0, face_rec_dir)
from recognizer import FaceRecognizer
from attendance_service import AttendanceService


class ActivityMonitorApp:
    """
    Existing classroom webcam monitor, controlled by session lifecycle.

    - Models load at construction time (FastAPI startup).
    - Physical webcam opens only when start_monitoring() is called (Start Session).
    - stop_monitoring() stops the loop and releases VideoCapture (Stop Session).
    """

    def __init__(self, test_mode=False, max_frames=50, config=None, session_manager=None):
        self._running = False
        self.headless = True
        self._thread = None
        self._cap = None
        self._lifecycle_lock = threading.Lock()

        # Real camera status — never inferred from session_id alone
        self.camera_status = "stopped"  # stopped | starting | active | error
        self.camera_error = None
        self.frames_processed = 0
        self.last_frame_at = None

        try:
            self.detector = ClassroomActivityDetector(static_image_mode=False)
            print("[INFO] ClassroomActivityDetector loaded successfully.")
        except Exception as e:
            print(f"[!] Error loading detector: {e}")
            raise

        self.test_mode = test_mode
        self.max_frames = max_frames
        self.config = config or MonitoringConfig()

        try:
            self.alert_engine = AlertEngine(config=self.config)
            print("[INFO] AlertEngine initialized.")
        except Exception as e:
            print(f"[!] Error loading AlertEngine: {e}")
            self.alert_engine = None

        try:
            self.session_manager = session_manager or MonitoringSessionManager()
        except Exception as e:
            print(f"[!] Target Session DB Error: {e}")
            self.session_manager = session_manager

        try:
            self.recognizer = FaceRecognizer()
            self.face_cascade = self.recognizer.face_detector
        except Exception as e:
            print(f"[!] Face recognition init failed: {e}")
            self.recognizer = None
            self.face_cascade = None

        self.attendance_service = AttendanceService()
        self.talking_tracker = TalkingTracker(self.config)

        try:
            self.audio_monitor = AudioMonitor(
                config=self.config,
                alert_engine=self.alert_engine,
                audio_hook=self.detector.audio_hook,
                session_manager=self.session_manager,
            )
            print("[INFO] AudioMonitor initialized.")
        except Exception as e:
            print(f"[!] AudioMonitor init failed: {e}")
            self.audio_monitor = None

        self.activity_history = []
        self.history_size = 5
        self.current_stable_activity = "unknown"

        # Live dashboard preview + last recognition (for attendance UX)
        self._preview_lock = threading.Lock()
        self._preview_jpeg = None
        self.last_recognized = None  # {name, roll_number, student_id, confidence, at}

    def get_camera_status(self) -> dict:
        audio_stat = (
            self.audio_monitor.get_status()
            if self.audio_monitor
            else {
                "audio_status": "stopped",
                "audio_error": None,
                "is_monitoring": False,
                "current_sound_level_db": 0.0,
                "smoothed_sound_level_db": 0.0,
            }
        )
        return {
            "camera_status": self.camera_status,
            "camera_error": self.camera_error,
            "frames_processed": self.frames_processed,
            "last_frame_at": self.last_frame_at,
            "is_monitoring": self._running and self.camera_status == "active",
            "thread_alive": bool(self._thread and self._thread.is_alive()),
            "recognizer_trained": bool(self.recognizer and self.recognizer.is_trained),
            "last_recognized": self.last_recognized,
            "audio_status": audio_stat.get("audio_status", "stopped"),
            "audio_error": audio_stat.get("audio_error"),
            "current_sound_level_db": audio_stat.get("current_sound_level_db", 0.0),
            "smoothed_sound_level_db": audio_stat.get("smoothed_sound_level_db", 0.0),
        }

    def get_preview_jpeg(self):
        with self._preview_lock:
            return self._preview_jpeg

    def _store_preview(self, frame, analysis_result, stable_activity, recognized_label=None):
        """Encode annotated frame for browser MJPEG preview."""
        try:
            display = self.draw_ui(frame.copy(), analysis_result or {}, stable_activity or "unknown")
            if recognized_label:
                cv2.putText(
                    display,
                    recognized_label,
                    (10, display.shape[0] - 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 180),
                    2,
                )
            ok, buf = cv2.imencode(".jpg", display, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok:
                with self._preview_lock:
                    self._preview_jpeg = buf.tobytes()
        except Exception as e:
            print(f"[!] preview encode failed: {e}")

    def start_monitoring(self, headless=True, open_timeout_sec=8.0):
        """
        Open the physical webcam and start continuous frame processing.
        Safe to call if already active for the same process (no second capture).
        Returns (ok: bool, error_message: str | None)
        """
        with self._lifecycle_lock:
            if self._running and self.camera_status == "active" and self._thread and self._thread.is_alive():
                return True, None

            # Clean up a previous dead/error thread before restarting
            if self._thread and self._thread.is_alive():
                self._running = False
                self._thread.join(timeout=3.0)

            self._running = True
            self.headless = headless
            self.camera_status = "starting"
            self.camera_error = None
            self.frames_processed = 0
            self.last_frame_at = None
            self.activity_history = []
            self.current_stable_activity = "unknown"

            self._thread = threading.Thread(
                target=self._run_loop,
                kwargs={"headless": headless},
                daemon=True,
                name="classroom-webcam-monitor",
            )
            self._thread.start()

        deadline = time.time() + open_timeout_sec
        while time.time() < deadline:
            if self.camera_status == "active":
                # Start audio monitoring alongside active webcam
                if self.audio_monitor and getattr(self.config, "audio_monitoring_enabled", True):
                    sess_id = getattr(self.session_manager, "session_id", None)
                    try:
                        self.audio_monitor.start_monitoring(session_id=sess_id)
                    except Exception as e:
                        print(f"[!] Failed to start audio monitor: {e}")
                return True, None
            if self.camera_status == "error":
                err = self.camera_error or (
                    "Unable to access webcam. Please close other applications using the camera."
                )
                self.stop_monitoring()
                return False, err
            time.sleep(0.1)

        err = self.camera_error or (
            "Unable to access webcam. Please close other applications using the camera."
        )
        self.stop_monitoring()
        self.camera_status = "error"
        self.camera_error = err
        return False, err

    def stop_monitoring(self, join_timeout_sec=6.0):
        """Stop the loop, release VideoCapture, join the thread."""
        with self._lifecycle_lock:
            self._running = False
            thread = self._thread

        if thread and thread.is_alive():
            thread.join(timeout=join_timeout_sec)

        # Defensive release if loop exited without finally
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        with self._lifecycle_lock:
            self._thread = None
            if self.camera_status != "error":
                self.camera_status = "stopped"
                self.camera_error = None

        # Stop audio monitoring cleanly
        if self.audio_monitor:
            try:
                self.audio_monitor.stop_monitoring()
            except Exception as e:
                print(f"[!] Failed to stop audio monitor: {e}")

        print("[INFO] Webcam and audio monitoring stopped; resources released.")

    def update_stable_state(self, incoming_activity):
        self.activity_history.append(incoming_activity)
        if len(self.activity_history) > self.history_size:
            self.activity_history.pop(0)

        counts = {}
        for a in self.activity_history:
            counts[a] = counts.get(a, 0) + 1

        dominant_activity = max(counts, key=counts.get)

        if counts[dominant_activity] >= (self.history_size * 0.6):
            if dominant_activity != self.current_stable_activity:
                self.current_stable_activity = dominant_activity
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] STATUS CHANGED -> "
                    f"{self.current_stable_activity.replace('_', ' ').upper()}"
                )

        return self.current_stable_activity

    def draw_ui(self, frame, analysis_result, stable_activity):
        h, w, _ = frame.shape
        if self.face_cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
            )
            for (fx, fy, fw, fh) in faces:
                cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (255, 200, 50), 2)
                cv2.putText(
                    frame, "Student", (fx, fy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 50), 2,
                )
                break

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (320, 180), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)

        formatted_activity = stable_activity.replace("_", " ").upper()
        if stable_activity == "normal":
            color = (0, 255, 0)
        elif stable_activity in ["unknown", "offline"]:
            color = (150, 150, 150)
        else:
            color = (0, 0, 255)

        cv2.putText(
            frame, f"STATUS: {formatted_activity}", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2,
        )
        details = analysis_result.get("details", {})
        conf = analysis_result.get("confidence", 0.0)
        cv2.putText(
            frame, f"Conf: {conf:.1f}%", (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
        )

        y_offset = 90
        raw_act = analysis_result.get("activity", "unknown")
        if details.get("phone_detected", False):
            cv2.putText(
                frame, "[X] PHONE DETECTED", (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1,
            )
            y_offset += 20
        if raw_act == "sleeping":
            cv2.putText(
                frame, "[X] EYES CLOSED / ASLEEP", (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1,
            )
            y_offset += 20
        if raw_act == "looking_away":
            cv2.putText(
                frame, "[X] LOOKING AWAY", (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1,
            )
            y_offset += 20
        if raw_act in ("talking", "prolonged_discussion"):
            cv2.putText(
                frame, "[X] TALKING / DISCUSSION", (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1,
            )
            y_offset += 20
        if raw_act == "unnecessary_activity":
            cv2.putText(
                frame, "[X] UNNECESSARY MOVEMENT", (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1,
            )

        cv2.putText(
            frame, "Q:Quit  C:Clear", (10, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1,
        )
        return frame

    def _process_frame(self, frame, frame_count):
        session_id = getattr(self.session_manager, "session_id", None)
        if session_id in (None, "", "offline-fallback-session", "test-mock-session"):
            return "offline", {}, None

        current_student_id = "UNKNOWN_STUDENT"
        recognized_label = None

        # Run recognition more often against enrolled face images
        if frame_count % 5 == 0 and self.recognizer and self.recognizer.is_trained:
            try:
                match_data, face_conf = self.recognizer.recognize_test_face(test_frame=frame)
                if match_data != "Unknown" and match_data is not None:
                    current_student_id = match_data.get("student_id", "UNKNOWN_STUDENT")
                    recognized_label = (
                        f"{match_data.get('name')} ({match_data.get('roll_number')}) "
                        f"{face_conf:.0f}%"
                    )
                    self.last_recognized = {
                        "student_id": current_student_id,
                        "name": match_data.get("name"),
                        "roll_number": match_data.get("roll_number"),
                        "confidence": round(float(face_conf), 2),
                        "at": datetime.utcnow().isoformat() + "Z",
                    }
                    if self.config.attendance_enabled:
                        self.attendance_service.record_face_recognition_attendance(
                            match_data, face_conf, session_id
                        )
                elif match_data == "Unknown":
                    recognized_label = f"Unknown face ({face_conf:.0f}%)"
            except Exception as e:
                print(f"[!] Face recognition error: {e}")

        try:
            analysis_result = self.detector.analyze_frame(frame, student_id=current_student_id)
        except Exception as e:
            print(f"[!] Activity detection error: {e}")
            analysis_result = {
                "student_id": current_student_id,
                "activity": "unknown",
                "confidence": 0.0,
                "details": {},
            }

        raw_activity = analysis_result.get("activity", "unknown")

        try:
            if self.alert_engine:
                self.alert_engine.process_activity_event(session_id, analysis_result)

            is_talking = raw_activity in ("prolonged_discussion",) or (
                isinstance(analysis_result.get("details"), dict)
                and float(analysis_result["details"].get("mar") or 0) > 0.5
            )
            talking_alert = self.talking_tracker.process_audio_visual_state(is_talking)
            if talking_alert and raw_activity != "prolonged_discussion" and self.alert_engine:
                self.alert_engine.process_activity_event(
                    session_id,
                    {
                        "student_id": current_student_id,
                        "activity": "prolonged_discussion",
                        "confidence": 85.0,
                    },
                )
        except Exception as e:
            print(f"[!] Alert pipeline error: {e}")

        stable_activity = self.update_stable_state(raw_activity)
        return stable_activity, analysis_result, recognized_label

    def _run_loop(self, headless=True):
        self.headless = headless
        print("\n--- Starting Webcam Activity Monitor (session-controlled) ---")
        cap = None
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(0)
            time.sleep(0.8)

            if not cap.isOpened():
                self.camera_status = "error"
                self.camera_error = (
                    "Unable to access webcam. Please close other applications using the camera."
                )
                print(f"[!] ERROR: {self.camera_error}")
                return

            self._cap = cap
            self.camera_status = "active"
            self.camera_error = None
            print("[INFO] Physical webcam opened — continuous capture active.")

            frame_count = 0
            while self._running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    print("[!] Failed to grab frame from webcam.")
                    self.camera_status = "error"
                    self.camera_error = (
                        "Unable to access webcam. Please close other applications using the camera."
                    )
                    break

                frame = cv2.flip(frame, 1)

                # Count frames before heavy CV so status reflects live capture immediately
                self.frames_processed += 1
                self.last_frame_at = datetime.utcnow().isoformat() + "Z"

                try:
                    stable_activity, analysis_result, recognized_label = self._process_frame(
                        frame, frame_count
                    )
                except Exception as e:
                    print(f"[!] Frame processing error (continuing): {e}")
                    stable_activity, analysis_result, recognized_label = "unknown", {}, None

                # Always publish preview for the Teacher Dashboard (one camera only)
                self._store_preview(frame, analysis_result, stable_activity, recognized_label)

                if not headless and not self.test_mode:
                    display_frame = self.draw_ui(frame.copy(), analysis_result, stable_activity)
                    cv2.imshow("AI Classroom Activity Monitor", display_frame)

                if self.test_mode and not headless:
                    frame_count += 1
                    if frame_count >= self.max_frames:
                        break
                elif not headless:
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    elif key == ord("c"):
                        self.activity_history.clear()
                        self.current_stable_activity = "unknown"

                if headless:
                    time.sleep(0.05)
                frame_count += 1
        except Exception as e:
            self.camera_status = "error"
            self.camera_error = str(e)
            print(f"[!] Webcam loop error: {e}")
        finally:
            self._running = False
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            self._cap = None
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
            if self.camera_status == "active":
                self.camera_status = "stopped"
            print("--- Camera Released. Session Ended ---")

    def run(self, headless=False):
        """Standalone / CLI entry — opens camera and blocks until stop."""
        ok, err = self.start_monitoring(headless=headless)
        if not ok:
            print(f"[!] {err}")
            return
        try:
            while self._running and self._thread and self._thread.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("Session interrupted by user.")
        finally:
            self.stop_monitoring()

    def stop(self):
        """Alias used by FastAPI shutdown."""
        self.stop_monitoring()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-Time Classroom Activity Monitor")
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()

    sm = MonitoringSessionManager()
    sm.start_or_get_session()
    app = ActivityMonitorApp(test_mode=args.test_mode, session_manager=sm)
    app.run()
