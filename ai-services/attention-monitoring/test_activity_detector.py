import os
import sys
import cv2
import json

# Ensure sys.path includes module parent directories
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from activity_detector import ClassroomActivityDetector
from audio_hook import AudioActivityHook

def run_test():
    print("==================================================")
    print("   Classroom Activity Detector Module Test        ")
    print("==================================================\n")

    # 1. Initialize Audio Hook & Activity Detector
    audio_hook = AudioActivityHook()
    detector = ClassroomActivityDetector(audio_hook=audio_hook)
    print("ClassroomActivityDetector Initialized: SUCCESS")

    # 2. Test Image Path (using sample_face.jpg from face-recognition)
    sample_img_path = os.path.join(parent_dir, "face-recognition", "sample_face.jpg")
    if not os.path.exists(sample_img_path):
        print(f"[!] Warning: Sample image not found at '{sample_img_path}'. Creating synthetic test frame.")
        frame = 255 * (0.5 * (1 + 0.5 * (0.5 * (1)))) # gray frame
    else:
        frame = cv2.imread(sample_img_path)
        print(f"Loaded test frame: {sample_img_path} ({frame.shape[1]}x{frame.shape[0]})")

    # 3. Test 1: Normal Engaged Activity Analysis
    print("\n--- Test 1: Frame Activity Analysis ---")
    result1 = detector.analyze_frame(frame, student_id="TEST_STUDENT_001")
    print("Result Payload:")
    print(json.dumps(result1, indent=2))

    # Verify structured fields
    required_keys = ["student_id", "activity", "confidence", "timestamp"]
    for key in required_keys:
        assert key in result1, f"Missing required key: {key}"

    valid_activities = ["normal", "phone_usage", "sleeping", "looking_away", "talking", "prolonged_discussion", "unnecessary_activity", "unknown"]
    assert result1["activity"] in valid_activities, f"Invalid activity status: {result1['activity']}"
    print(f"\n[+] Test 1 PASSED: Valid result schema verified for activity '{result1['activity']}'.")

    # 4. Test 2: Audio Hook Integration (Simulating prolonged discussion detection via Audio Engine)
    print("\n--- Test 2: Audio Monitoring Architecture Hook ---")
    t = 0.0
    final_alert = False
    for i in range(5):
        audio_hook.set_speech_state(is_talking=True, confidence=0.92)
        for _ in range(30):
            res = detector.analyze_frame(frame, student_id="TEST_STUDENT_001", current_time=t)
            if res["activity"] == "prolonged_discussion": final_alert = True
            t += 0.1
        audio_hook.set_speech_state(is_talking=False, confidence=0.0)
        for _ in range(30):
            res = detector.analyze_frame(frame, student_id="TEST_STUDENT_001", current_time=t)
            if res["activity"] == "prolonged_discussion": final_alert = True
            t += 0.1
            
    print(f"Final evaluated activity containing audio hook triggered states: '{res['activity']}'")
    assert final_alert, f"Expected prolonged_discussion alert after sustained audio hook triggers."
    print("[+] Test 2 PASSED: Audio Hook integration and Smart Tracker logic verified!")

    # Reset audio hook
    audio_hook.set_speech_state(is_talking=False, confidence=0.0)

    print("\n==================================================")
    print("     ALL ACTIVITY DETECTOR TESTS PASSED OK       ")
    print("==================================================")

if __name__ == "__main__":
    run_test()
