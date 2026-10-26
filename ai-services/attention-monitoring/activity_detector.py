import cv2
import numpy as np
import datetime
import os
import sys
import mediapipe as mp

# Add current folder to sys.path for relative import safety
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Ensure parent dir is in sys.path for top-level importing
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
    
audio_monitor_dir = os.path.join(parent_dir, "audio-monitoring")
if audio_monitor_dir not in sys.path:
    sys.path.insert(0, audio_monitor_dir)

from audio_hook import AudioActivityHook
from monitoring_config import MonitoringConfig
from talking_tracker import TalkingTracker  # type: ignore


try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False


class ClassroomActivityDetector:
    """
    Computer-Vision powered Classroom Activity Detector.
    Uses Haar Cascade + MediaPipe Face Mesh for facial landmark analysis (EAR, MAR, 3D head pose)
    and YOLOv8 object detection for phone usage detection.
    Integrates AudioActivityHook for multi-modal audio monitoring (talking/murmuring detection).
    """
    def __init__(self, ear_threshold=0.18, mar_threshold=0.35, yaw_threshold=25.0, pitch_threshold=25.0, static_image_mode=False, audio_hook=None, config=None, talking_tracker=None):
        self.ear_threshold = ear_threshold
        self.mar_threshold = mar_threshold
        self.yaw_threshold = yaw_threshold
        self.pitch_threshold = pitch_threshold
        self.static_image_mode = static_image_mode
        
        self.config = config or MonitoringConfig()
        self.audio_hook = audio_hook or AudioActivityHook()
        
        # Note: If no custom tracker provided, import securely
        if talking_tracker is None:
            self.talking_tracker = TalkingTracker(self.config)
        else:
            self.talking_tracker = talking_tracker
        
        # 1. Initialize Haar Cascade face detector fallback
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_cascade = os.path.join(base_dir, "..", "face-recognition", "models", "haarcascade_frontalface_default.xml")
        cv2_cascade = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        
        cascade_path = local_cascade if os.path.exists(local_cascade) else cv2_cascade
        if os.path.exists(cascade_path):
            self.haar_cascade = cv2.CascadeClassifier(cascade_path)
        else:
            self.haar_cascade = None

        # 2. Initialize MediaPipe Face Mesh (reuse — never recreate per frame)
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=self.static_image_mode,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.3,
            min_tracking_confidence=0.3
        )
        # Separate static mesh for Haar-crop fallback (created once)
        self.face_mesh_roi = self.mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.1,
            min_tracking_confidence=0.1,
        )
        
        # 3. Lazy-loaded YOLO object detector for cell phones
        self._yolo_model = None
        self._yolo_attempted = False

    def _get_yolo_model(self):
        if not self._yolo_attempted and YOLO_AVAILABLE:
            self._yolo_attempted = True
            try:
                # Load lightweight nano YOLOv8 model for real-time phone detection
                self._yolo_model = YOLO("yolov8n.pt")
            except Exception as e:
                print(f"Warning: Could not load YOLO model for phone detection ({e}).")
                self._yolo_model = None
        return self._yolo_model

    @staticmethod
    def _euclidean_dist(p1, p2):
        return np.linalg.norm(np.array(p1) - np.array(p2))

    def _calculate_ear(self, landmarks, img_w, img_h):
        """Calculates Eye Aspect Ratio (EAR) for left and right eyes."""
        def eye_aspect_ratio(eye_pts):
            p1, p2, p3, p4, p5, p6 = eye_pts
            v1 = self._euclidean_dist(p2, p6)
            v2 = self._euclidean_dist(p3, p5)
            h = self._euclidean_dist(p1, p4)
            if h == 0:
                return 0.0
            return (v1 + v2) / (2.0 * h)

        def get_pt(idx):
            lm = landmarks[idx]
            return np.array([lm.x * img_w, lm.y * img_h])

        left_pts = [get_pt(33), get_pt(160), get_pt(158), get_pt(133), get_pt(153), get_pt(144)]
        right_pts = [get_pt(362), get_pt(385), get_pt(387), get_pt(263), get_pt(373), get_pt(380)]

        left_ear = eye_aspect_ratio(left_pts)
        right_ear = eye_aspect_ratio(right_pts)

        return (left_ear + right_ear) / 2.0

    def _calculate_mar(self, landmarks, img_w, img_h):
        """Calculates Mouth Aspect Ratio (MAR) for mouth opening visual detection."""
        p_upper = np.array([landmarks[13].x * img_w, landmarks[13].y * img_h])
        p_lower = np.array([landmarks[14].x * img_w, landmarks[14].y * img_h])
        p_left = np.array([landmarks[61].x * img_w, landmarks[61].y * img_h])
        p_right = np.array([landmarks[291].x * img_w, landmarks[291].y * img_h])

        vertical = self._euclidean_dist(p_upper, p_lower)
        horizontal = self._euclidean_dist(p_left, p_right)

        if horizontal == 0:
            return 0.0
        return vertical / horizontal

    def _estimate_head_pose(self, landmarks, img_w, img_h):
        """Estimates 3D Head Pose (Yaw, Pitch, Roll) using OpenCV solvePnP."""
        model_points = np.array([
            (0.0, 0.0, 0.0),             # Nose tip (1)
            (0.0, -330.0, -65.0),        # Chin (152)
            (-225.0, 170.0, -135.0),     # Left eye left corner (33)
            (225.0, 170.0, -135.0),      # Right eye right corner (263)
            (-150.0, -150.0, -125.0),    # Left Mouth corner (61)
            (150.0, -150.0, -125.0)      # Right mouth corner (291)
        ], dtype=np.float64)

        image_points = np.array([
            (landmarks[1].x * img_w, landmarks[1].y * img_h),
            (landmarks[152].x * img_w, landmarks[152].y * img_h),
            (landmarks[33].x * img_w, landmarks[33].y * img_h),
            (landmarks[263].x * img_w, landmarks[263].y * img_h),
            (landmarks[61].x * img_w, landmarks[61].y * img_h),
            (landmarks[291].x * img_w, landmarks[291].y * img_h)
        ], dtype=np.float64)

        focal_length = img_w
        center = (img_w / 2.0, img_h / 2.0)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)

        dist_coeffs = np.zeros((4, 1))
        
        success, rvec, tvec = cv2.solvePnP(
            model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )
        if not success:
            return 0.0, 0.0, 0.0

        rmat, _ = cv2.Rodrigues(rvec)

        sy = np.sqrt(rmat[0, 0] * rmat[0, 0] + rmat[1, 0] * rmat[1, 0])
        singular = sy < 1e-6

        if not singular:
            pitch = np.arctan2(rmat[2, 1], rmat[2, 2])
            yaw = np.arctan2(-rmat[2, 0], sy)
            roll = np.arctan2(rmat[1, 0], rmat[0, 0])
        else:
            pitch = np.arctan2(-rmat[1, 2], rmat[1, 1])
            yaw = np.arctan2(-rmat[2, 0], sy)
            roll = 0.0

        pitch_deg = np.degrees(pitch)
        yaw_deg = np.degrees(yaw)
        roll_deg = np.degrees(roll)

        # Normalize pitch to [-90, 90]
        if pitch_deg > 90.0:
            pitch_deg -= 180.0
        elif pitch_deg < -90.0:
            pitch_deg += 180.0

        # Normalize yaw to [-90, 90]
        if yaw_deg > 90.0:
            yaw_deg -= 180.0
        elif yaw_deg < -90.0:
            yaw_deg += 180.0

        return yaw_deg, pitch_deg, roll_deg

    def _detect_phone(self, frame):
        """Runs YOLO object detector on the frame to detect cell phone presence."""
        model = self._get_yolo_model()
        if model is None:
            return False, 0.0

        try:
            results = model(frame, verbose=False, conf=0.35)
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    # COCO class 67 is 'cell phone'
                    if cls_id == 67:
                        conf = float(box.conf[0])
                        return True, conf
        except Exception as e:
            print(f"Error running YOLO phone detector: {e}")

        return False, 0.0

    def analyze_frame(self, frame, student_id="UNKNOWN_STUDENT", current_time=None):
        """
        Analyzes a single video frame for student activity.
        Returns a structured output dictionary.
        """
        if frame is None or frame.size == 0:
            return {
                "student_id": student_id,
                "activity": "unknown",
                "confidence": 0.0,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }

        img_h, img_w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 1. Phone Detection (YOLO)
        phone_detected, phone_conf = self._detect_phone(frame)

        # 2. MediaPipe Facial Landmark Analysis
        mesh_results = self.face_mesh.process(rgb_frame)
        landmarks = None
        target_w, target_h = img_w, img_h

        if mesh_results and mesh_results.multi_face_landmarks:
            landmarks = mesh_results.multi_face_landmarks[0].landmark
        elif self.haar_cascade:
            # Fallback: Detect face with Haar Cascade and run FaceMesh on cropped ROI with margin
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.haar_cascade.detectMultiScale(gray, 1.1, 5)
            if len(faces) > 0:
                (fx, fy, fw, fh) = faces[0]
                mw, mh = int(fw * 0.3), int(fh * 0.3)
                x1, y1 = max(0, fx - mw), max(0, fy - mh)
                x2, y2 = min(img_w, fx + fw + mw), min(img_h, fy + fh + mh)
                
                roi = rgb_frame[y1:y2, x1:x2]
                if roi.size > 0:
                    roi_res = self.face_mesh_roi.process(roi)
                    if roi_res and roi_res.multi_face_landmarks:
                        landmarks = roi_res.multi_face_landmarks[0].landmark
                        target_w, target_h = (x2 - x1), (y2 - y1)

        if landmarks is None:
            if phone_detected:
                activity = "phone_usage"
                confidence = round(phone_conf * 100.0, 2)
            else:
                activity = "unknown"
                confidence = 0.0

            return {
                "student_id": student_id,
                "activity": activity,
                "confidence": confidence,
                "details": {
                    "phone_detected": phone_detected
                },
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }

        # Calculate facial metrics
        ear = self._calculate_ear(landmarks, target_w, target_h)
        mar = self._calculate_mar(landmarks, target_w, target_h)
        yaw, pitch, roll = self._estimate_head_pose(landmarks, target_w, target_h)

        # Check Audio Hook for speech/talking
        audio_talking, audio_conf = self.audio_hook.is_talking_detected()

        # Update Talking Tracker (Joint logic: Audio OR Visual MAR is considered speech activity step)
        is_speech_active = False
        if self.config.talking_detection_enabled:
            is_speech_active = audio_talking or (mar > self.mar_threshold)

        # Process through tracker
        prolonged_alert = self.talking_tracker.process_audio_visual_state(is_speech_active, current_time=current_time)

        # Activity Classification Priority
        # 1. Phone Usage
        if phone_detected and self.config.phone_detection_enabled:
            activity = "phone_usage"
            confidence = round(max(0.70, phone_conf) * 100.0, 2)

        # 2. Prolonged Discussion Alert (if enabled and triggered)
        elif prolonged_alert and self.config.talking_detection_enabled:
            activity = "prolonged_discussion"
            confidence = 100.0

        # 3. Sleeping / Eyes Closed
        elif ear < self.ear_threshold and self.config.sleeping_detection_enabled:
            activity = "sleeping"
            confidence = round(max(70.0, (1.0 - (ear / self.ear_threshold)) * 100.0), 2)

        # 4. Looking Away / Sideways
        elif (abs(yaw) > self.yaw_threshold or abs(pitch) > self.pitch_threshold) and self.config.looking_away_detection_enabled:
            activity = "looking_away"
            deviation = max(abs(yaw) / self.yaw_threshold, abs(pitch) / self.pitch_threshold)
            confidence = round(min(100.0, deviation * 80.0), 2)

        # 5. Visual Talking / Mouth Open (We no longer generate an alert immediately, but we can pass it as a minor 'talking' state if requested. However, per requirement, simple talking is normal.)
        # We will NOT alert on immediate talking per requirements, only on prolonged_discussion.
        
        # 6. Unnecessary Activity
        elif abs(roll) > 35.0 and self.config.unnecessary_activity_enabled:
            activity = "unnecessary_activity"
            confidence = round(min(100.0, (abs(roll) / 35.0) * 75.0), 2)

        # 7. Normal Engaged Activity
        else:
            activity = "normal"
            confidence = 95.0

        return {
            "student_id": student_id,
            "activity": activity,
            "confidence": float(confidence),
            "details": {
                "ear": round(float(ear), 4),
                "mar": round(float(mar), 4),
                "head_pose": {
                    "yaw": round(float(yaw), 2),
                    "pitch": round(float(pitch), 2),
                    "roll": round(float(roll), 2)
                },
                "phone_detected": phone_detected,
                "audio_speech_detected": audio_talking
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
