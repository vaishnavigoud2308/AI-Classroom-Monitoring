import os
import sys

# Ensure script directory is in sys.path and resolve relative paths using __file__
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from recognizer import FaceRecognizer

def run_test():
    print("==================================================")
    print("      Face Recognizer Local Test Execution        ")
    print("==================================================\n")

    # Path to test image relative to test_recognizer.py
    sample_image_path = os.path.join(current_dir, "sample_face.jpg")

    if not os.path.exists(sample_image_path):
        print(f"[!] ERROR: Test image not found at '{sample_image_path}'.")
        sys.exit(1)

    # 1. Initialize FaceRecognizer
    try:
        recognizer = FaceRecognizer()
        print("FaceRecognizer Initialized: OK")
    except Exception as e:
        print(f"[!] ERROR Initializing FaceRecognizer: {e}")
        sys.exit(1)

    # 2. Student registration details
    student_id = "test-student-001"
    name = "Kiran"
    roll_number = "TEST001"

    # 3. Call register_student()
    print("\n--- Step 1: Register Student ---")
    reg_success = recognizer.register_student(
        student_id=student_id,
        name=name,
        roll_number=roll_number,
        image_path=sample_image_path
    )
    print(f"Face Registration Result: {'SUCCESS' if reg_success else 'FAILED'}")
    
    if not reg_success:
        print("[!] Registration failed (no face detected or unreadable image).")
        sys.exit(1)

    # 4. Call train_model()
    print("\n--- Step 2: Train Model ---")
    train_success = recognizer.train_model()
    print(f"Training Result: {'SUCCESS' if train_success else 'FAILED'}")
    
    if not train_success:
        print("[!] Model training failed.")
        sys.exit(1)

    # 5. Call recognize_test_face()
    print("\n--- Step 3: Recognize Test Face ---")
    match_result, confidence = recognizer.recognize_test_face(sample_image_path)

    # 6. Print clear results
    if match_result == "Unknown" or match_result is None:
        print("Recognition Result: UNKNOWN / NOT RECOGNIZED")
        print(f"Confidence: {confidence:.2f}%")
    else:
        print("Recognition Result: MATCH FOUND")
        print(f"Student Name:       {match_result['name']}")
        print(f"Roll Number:        {match_result['roll_number']}")
        print(f"Student ID:         {match_result['student_id']}")
        print(f"Confidence:         {confidence:.2f}%")

if __name__ == "__main__":
    run_test()
