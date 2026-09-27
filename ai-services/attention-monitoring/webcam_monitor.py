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

# Alert Engine (handle dash in folder name)
alert_dir = os.path.join(parent_dir, "alert-engine")
if alert_dir not in sys.path:
    sys.path.insert(0, alert_dir)
from alert_engine import AlertEngine

# Talking Tracker
audio_dir = os.path.join(parent_dir, "audio-monitoring")
if audio_dir not in sys.path:
    sys.path.insert(0, audio_dir)
from talking_tracker import TalkingTracker

# Face Recognition
face_rec_dir = os.path.join(parent_dir, "face-recognition")
if face_rec_dir not in sys.path:
    sys.path.insert(0, face_rec_dir)
from recognizer import FaceRecognizer
from attendance_service import AttendanceService

class ActivityMonitorApp:
    def __init__(self, test_mode=False, max_frames=50, config=None, session_manager=None):
        self._running = False
        self.headless = False
        try:
            self.detector = ClassroomActivityDetector(static_image_mode=False)
            print("[INFO] ClassroomActivityDetector loaded successfully.")
        except Exception as e:
            print(f"[!] Error loading detector: {e}")
            sys.exit(1)

        self.test_mode = test_mode
        self.max_frames = max_frames
        
        self.config = config or MonitoringConfig()
        
        try:
            self.alert_engine = AlertEngine(config=self.config)
            print("[INFO] AlertEngine initialized.")
        except Exception as e:
            print(f"[!] Error loading AlertEngine: {e}")
            
        try:
            self.session_manager = session_manager or MonitoringSessionManager()
        except Exception as e:
            print(f"[!] Target Session DB Error: {e}")
            
        try:
            self.recognizer = FaceRecognizer()
            self.face_cascade = self.recognizer.face_detector
        except Exception as e:
            print(f"[!] Target DB not connected or missing models for face recognition: {e}")
            self.recognizer = None
            self.face_cascade = None

        self.attendance_service = AttendanceService()
        self.talking_tracker = TalkingTracker(self.config)

        self.activity_history = []
        self.history_size = 5 
        self.current_stable_activity = "unknown"
        
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
                print(f"[{datetime.now().strftime('%H:%M:%S')}] STATUS CHANGED -> {self.current_stable_activity.replace('_', ' ').upper()}")
                
        return self.current_stable_activity

    def draw_ui(self, frame, analysis_result, stable_activity):
        h, w, _ = frame.shape
        if self.face_cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            for (fx, fy, fw, fh) in faces:
                cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (255, 200, 50), 2)
                cv2.putText(frame, "Student", (fx, fy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 50), 2)
                break 

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (320, 180), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)

        formatted_activity = stable_activity.replace("_", " ").upper()
        if stable_activity == "normal":
            color = (0, 255, 0) 
        elif stable_activity in ["unknown"]:
            color = (150, 150, 150) 
        else:
            color = (0, 0, 255) 

        cv2.putText(frame, f"STATUS: {formatted_activity}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        details = analysis_result.get("details", {})
        conf = analysis_result.get("confidence", 0.0)
        cv2.putText(frame, f"Conf: {conf:.1f}%", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        y_offset = 90
        raw_act = analysis_result.get('activity', 'unknown')
        if details.get("phone_detected", False):
            cv2.putText(frame, "[X] PHONE DETECTED", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1)
            y_offset += 20
        if raw_act == "sleeping":
            cv2.putText(frame, "[X] EYES CLOSED / ASLEEP", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1)
            y_offset += 20
        if raw_act == "looking_away":
            cv2.putText(frame, "[X] LOOKING AWAY", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1)
            y_offset += 20
        if raw_act == "talking":
            cv2.putText(frame, "[X] TALKING / MOUTH OPEN", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1)
            y_offset += 20
        if raw_act == "unnecessary_activity":
            cv2.putText(frame, "[X] UNNECESSARY MOVEMENT", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 1)

        cv2.putText(frame, "Q:Quit  S:Save  C:Clear", (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        return frame

    def run(self, headless=False):
        self._running = True
        self.headless = headless
        print("\n--- Starting Webcam Activity Monitor ---")
        cap = cv2.VideoCapture(0)
        time.sleep(1.0) 
        if not cap.isOpened():
            print("[!] ERROR: Cannot open webcam.")
            return

        frame_count = 0
        try:
            while self._running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    print("[!] Failed to grab frame from webcam. Exiting...")
                    break
                    
                frame = cv2.flip(frame, 1)
                
                # Check active session. Only process if active.
                session_id = self.session_manager.session_id
                # Ignore offline fallback / cleared sessions
                if session_id in (None, "", "offline-fallback-session", "test-mock-session"):
                    session_id = None
                
                if session_id:
                    current_student_id = "UNKNOWN_STUDENT"
                    if frame_count % 15 == 0 and self.recognizer and self.recognizer.is_trained:
                        match_data, face_conf = self.recognizer.recognize_test_face(test_frame=frame)
                        if match_data != "Unknown" and match_data is not None:
                            current_student_id = match_data.get("student_id", "UNKNOWN_STUDENT")
                            if self.config.attendance_enabled:
                                self.attendance_service.record_face_recognition_attendance(match_data, face_conf, session_id)
                    
                    analysis_result = self.detector.analyze_frame(frame, student_id=current_student_id)
                    raw_activity = analysis_result.get("activity", "unknown")
                    
                    self.alert_engine.process_activity_event(session_id, analysis_result)
                    
                    # Audio/Talking Integration — detector already emits prolonged_discussion via MAR tracker.
                    # Keep secondary tracker for mouth-open frames as "talking-like" signal.
                    is_talking = raw_activity in ("prolonged_discussion",) or (
                        isinstance(analysis_result.get("details"), dict)
                        and float(analysis_result["details"].get("mar") or 0) > 0.5
                    )
                    talking_alert = self.talking_tracker.process_audio_visual_state(is_talking)
                    if talking_alert and raw_activity != "prolonged_discussion":
                        self.alert_engine.process_activity_event(session_id, {
                            "student_id": current_student_id,
                            "activity": "prolonged_discussion",
                            "confidence": 85.0
                        })
                    
                    stable_activity = self.update_stable_state(raw_activity)
                else:
                    stable_activity = "offline"
                    analysis_result = {}

                if not self.headless and not self.test_mode:
                    display_frame = self.draw_ui(frame.copy(), analysis_result, stable_activity)
                    cv2.imshow("AI Classroom Activity Monitor", display_frame)
                
                if self.test_mode and not self.headless:
                    frame_count += 1
                    if frame_count >= self.max_frames:
                        break
                elif not self.headless:
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        break
                    elif key == ord('c'):
                        self.activity_history.clear()
                        self.current_stable_activity = "unknown"
                        
                if self.headless:
                    time.sleep(0.1) # Throttle headless loop
                frame_count += 1
        except KeyboardInterrupt:
            print("Session interrupted by user.")
        finally:
            self._running = False
            cap.release()
            cv2.destroyAllWindows()
            print("--- Camera Released. Session Ended ---")

    def stop(self):
        self._running = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-Time Classroom Activity Monitor")
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    
    # In standalone mode, we get a new session ID
    sm = MonitoringSessionManager()
    sm.start_or_get_session()
    app = ActivityMonitorApp(test_mode=args.test_mode, session_manager=sm)
    app.run()
