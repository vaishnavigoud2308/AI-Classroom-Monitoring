import os
import sys
import time
import cv2
import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

if current_dir not in sys.path: sys.path.insert(0, current_dir)
if parent_dir not in sys.path: sys.path.insert(0, parent_dir)

attention_dir = os.path.join(parent_dir, "attention-monitoring")
if attention_dir not in sys.path: sys.path.insert(0, attention_dir)

face_rec_dir = os.path.join(parent_dir, "face-recognition")
if face_rec_dir not in sys.path: sys.path.insert(0, face_rec_dir)

from session_manager import MonitoringSessionManager
from alert_engine import AlertEngine
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FACE_RECOGNITION_DIR = PROJECT_ROOT / "ai-services" / "face-recognition"
ATTENTION_MONITORING_DIR = PROJECT_ROOT / "ai-services" / "attention-monitoring"

sys.path.insert(0, str(FACE_RECOGNITION_DIR))
sys.path.insert(0, str(ATTENTION_MONITORING_DIR))

from recognizer import FaceRecognizer  # type: ignore
from activity_detector import ClassroomActivityDetector  # type: ignore
from monitoring_config import MonitoringConfig

def test_pipeline_integration():
    print("==================================================")
    print("   Live Monitoring Pipeline Integration Test      ")
    print("==================================================\n")
    
    # 1. Initialize Pipeline Config & DB Session
    print("--- Step 1: Initializing Session Manager ---")
    session_manager = MonitoringSessionManager(supabase_client=False) # mock db 
    session_id = session_manager.start_or_get_session(teacher_name="Pipeline Tester")
    print(f"Generated Session ID: {session_id}")
    assert session_id == "test-mock-session" # since supabase is mocked False
    print("PASS: Session Management isolated successfully.")
    
    # 2. Components
    print("\n--- Step 2: Initializing Deep Learning Components ---")
    recognizer = FaceRecognizer()
    # Provide a mock training array so it thinks it's trained
    recognizer.is_trained = True 
    recognizer.label_to_uuid[0] = "TEST_UUID_001"
    recognizer.uuid_to_details["TEST_UUID_001"] = {"name": "Test", "roll_number": "000"}

    # Mock recognize predict logic since we don't have real LBPH trained weights loaded here
    recognizer.recognize_test_face = lambda test_image_path=None, test_frame=None: ({"student_id": "TEST_UUID_001", "name": "Test", "roll_number": "000"}, 100.0)
    
    detector = ClassroomActivityDetector(static_image_mode=True)
    
    # Override alert engine to mock DB
    class MockSupabase:
        def __init__(self):
            self.inserts = []
        def table(self, n): return self
        def insert(self, r): 
            self.recent = r
            return self
        def execute(self): 
            self.inserts.append(self.recent)
            return type('obj', (object,), {'data': []})
            
    mock_db = MockSupabase()
    config = MonitoringConfig()
    engine = AlertEngine(config=config, supabase_client=mock_db)
    
    # 3. Simulate Pipeline using mock image
    print("\n--- Step 3: Pushing Simulated Frame through Pipeline ---")
    sample_path = os.path.join(face_rec_dir, "sample_face.jpg")
    frame = cv2.imread(sample_path)
    
    # Step 3a: Face Recognizer (in memory)
    match_data, conf = recognizer.recognize_test_face(test_frame=frame)
    student_uuid = match_data["student_id"] if match_data != "Unknown" else "UNKNOWN"
    print(f"Resolved Student UUID dynamically: {student_uuid}")
    assert student_uuid == "TEST_UUID_001"
    
    # Step 3b: Activity Detector
    result = detector.analyze_frame(frame, student_id=student_uuid)
    
    # Step 3c: Orchestrator passes to Alert Engine
    processed = engine.process_activity_event(session_id, result)
    
    print("\n--- Step 4: Verification of Pipeline Outputs ---")
    print(f"Activity identified: {result['activity']}")
    
    # Simulate a phone detection override to verify alert behavior
    result["activity"] = "phone_usage"
    processed_alert = engine.process_activity_event(session_id, result)
    
    assert processed_alert == True
    assert len(mock_db.inserts) == 1
    recent = mock_db.inserts[-1]
    
    assert recent["session_id"] == "test-mock-session"
    assert recent["student_id"] == "TEST_UUID_001"
    assert recent["alert_type"] == "phone_usage"
    print("PASS: Alert Engine received pipeline output correctly and validated schemas.")
    
    print("\n[SUCCESS] Pipeline Integration Tests Complete!")
    
if __name__ == "__main__":
    test_pipeline_integration()
