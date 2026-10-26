import os
import sys
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Add attention-monitoring to path
attention_monitor_dir = os.path.join(parent_dir, "attention-monitoring")
if attention_monitor_dir not in sys.path:
    sys.path.insert(0, attention_monitor_dir)

import cv2
from talking_tracker import TalkingTracker
from monitoring_config import MonitoringConfig
from activity_detector import ClassroomActivityDetector  # type: ignore


def test_1():
    print("\n--- Test 1: One short talking event -> no alert ---")
    config = MonitoringConfig()
    tracker = TalkingTracker(config)
    
    t = 0.0
    for _ in range(30): # 3s of talking
        tracker.process_audio_visual_state(True, current_time=t)
        t += 0.1
    
    # Fast forward to allow silence gap to close the event
    for _ in range(30):
        tracker.process_audio_visual_state(False, current_time=t)
        t += 0.1
        
    print(f"Events recorded: {len(tracker.event_history)}")
    assert len(tracker.event_history) == 1
    print("PASS")


def test_2():
    print("\n--- Test 2: Four separate talking events -> no alert ---")
    config = MonitoringConfig()
    tracker = TalkingTracker(config)
    
    t = 0.0
    alert = None
    for i in range(4):
        # 3 seconds talking
        for _ in range(30):
            tracker.process_audio_visual_state(True, current_time=t)
            t += 0.1
        # 3 seconds silence
        for _ in range(30):
            alert = tracker.process_audio_visual_state(False, current_time=t)
            t += 0.1
        
    print(f"Events recorded: {len(tracker.event_history)}")
    assert len(tracker.event_history) == 4
    assert alert is None, "Should not alert on 4 events"
    print("PASS")


def test_3():
    print("\n--- Test 3: Five separate talking events -> alert generated ---")
    config = MonitoringConfig()
    tracker = TalkingTracker(config)
    
    t = 0.0
    final_alert = None
    for i in range(5):
        for _ in range(30):
            alert = tracker.process_audio_visual_state(True, current_time=t)
            t += 0.1
            if alert: final_alert = alert
        for _ in range(30):
            alert = tracker.process_audio_visual_state(False, current_time=t)
            t += 0.1
            if alert: final_alert = alert

        
    print(f"Final Alert Triggered: {final_alert}")
    assert final_alert == "Possible Prolonged Discussion"
    print("PASS")


def test_4():
    print("\n--- Test 4: One continuous 20-second talking period -> one event ---")
    config = MonitoringConfig()
    tracker = TalkingTracker(config)
    
    t = 0.0
    for step in range(20):
        tracker.process_audio_visual_state(True, current_time=t)
        t += 1.0 # 1 second increments of continuous talking
        
    alert = tracker.process_audio_visual_state(False, current_time=t + 3.0) # gap
    print(f"Events recorded: {len(tracker.event_history)}")
    assert len(tracker.event_history) == 1, f"Expected 1 event, got {len(tracker.event_history)}"
    assert alert is None
    print("PASS")


def test_5_and_6():
    print("\n--- Test 5/6: Talking disabled -> no talking alert, phone works ---")
    config = MonitoringConfig()
    config.talking_detection_enabled = False
    config.phone_detection_enabled = True
    
    detector = ClassroomActivityDetector(config=config)
    frame = 255 * np.ones((480, 640, 3), dtype=np.uint8) # synthetic frame
    
    # Mock phone detection to True to verify other systems run
    detector._detect_phone = lambda f: (True, 0.95)
    
    # Force 10 speech states
    for i in range(10):
        detector.audio_hook.set_speech_state(True, 1.0)
        res = detector.analyze_frame(frame, current_time=i * 5.0)
        detector.audio_hook.set_speech_state(False, 0.0)
        res = detector.analyze_frame(frame, current_time=i * 5.0 + 3.0)
        
    print(f"Final Activity Payload Activity: {res['activity']}")
    assert res['activity'] == "phone_usage"
    assert len(detector.talking_tracker.event_history) == 0, "Tracker shouldn't log when disabled"
    print("PASS")


def test_7_and_8():
    import numpy as np
    print("\n--- Test 7/8: AV Combination Logic ---")
    config = MonitoringConfig()
    config.talking_min_duration_seconds = 0.5
    detector = ClassroomActivityDetector(config=config)
    
    img_path = os.path.join(parent_dir, "face-recognition", "sample_face.jpg")
    frame = cv2.imread(img_path)
    if frame is None:
        frame = 255 * np.ones((480, 640, 3), dtype=np.uint8)
        
    class MockLM:
        x, y, z = 0.5, 0.5, 0.0
    mock_landmarks = [MockLM() for _ in range(468)]
    class MockResults:
        multi_face_landmarks = [type('FaceObj', (), {'landmark': mock_landmarks})()]
    detector.face_mesh.process = lambda x: MockResults()
    detector._estimate_head_pose = lambda *args: (0.0, 0.0, 0.0)
    
    # Mock out EAR/MAR evaluation for controllable tests
    detector._calculate_ear = lambda *args: 0.25 # Awake
    detector._detect_phone = lambda *args: (False, 0.0)
    
    t = 0.0
    final_alert = None
    
    # Use MAR + Audio to trigger
    detector._calculate_mar = lambda *args: 0.50
    detector.audio_hook.is_talking_detected = lambda: (True, 0.99)
    
    for i in range(5):
        # 3 seconds talking
        detector._calculate_mar = lambda *args: 0.50
        detector.audio_hook.is_talking_detected = lambda: (True, 0.99)
        for _ in range(30):
            res = detector.analyze_frame(frame, current_time=t)
            if res['activity'] == "prolonged_discussion": final_alert = True
            t += 0.1
            
        # 3 seconds silence
        detector._calculate_mar = lambda *args: 0.20
        detector.audio_hook.is_talking_detected = lambda: (False, 0.0)
        for _ in range(30):
            res = detector.analyze_frame(frame, current_time=t)
            if res['activity'] == "prolonged_discussion": final_alert = True
            t += 0.1
            
    print(f"Tracking Events Registered: {len(detector.talking_tracker.event_history)}")
    assert final_alert == True, "Prolonged discussion alert not triggered."
    print("PASS")

if __name__ == "__main__":
    import numpy as np
    test_1()
    test_2()
    test_3()
    test_4()
    test_5_and_6()
    test_7_and_8()
    print("\n[SUCCESS] ALL AUDIO / TALKING TESTS PASSED PERFECTLY.")
