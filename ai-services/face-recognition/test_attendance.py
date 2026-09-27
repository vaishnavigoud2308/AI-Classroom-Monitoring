import os
import sys

# Ensure current directory and parent directory are in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from recognizer import FaceRecognizer
from attendance_service import AttendanceService
from config import get_supabase_client
from seed_dev_data import ensure_dev_seed_data

def test_attendance_integration():
    print("==================================================")
    print("  Face Recognition -> Supabase Attendance Test    ")
    print("==================================================\n")

    # 1. Ensure development seed data exists in Supabase
    print("--- Step 1: Ensuring Development Seed Data in Supabase ---")
    teacher, student, session = ensure_dev_seed_data()

    student_id = student["id"]
    student_name = student["name"]
    roll_number = student["roll_number"]
    session_id = session["id"]

    print(f"\nActive Test Student: {student_name} (Roll: {roll_number}, UUID: {student_id})")
    print(f"Active Test Session: {session['subject']} in {session['classroom']} (UUID: {session_id})")

    # 2. Initialize services
    print("\n--- Step 2: Initializing FaceRecognizer & AttendanceService ---")
    try:
        attendance_service = AttendanceService()
        recognizer = FaceRecognizer()
        print("Initialization SUCCESS: FaceRecognizer & AttendanceService Ready")
    except Exception as e:
        print(f"[!] Initialization Error: {e}")
        sys.exit(1)

    # 3. Path to sample face image
    sample_image_path = os.path.join(current_dir, "sample_face.jpg")
    if not os.path.exists(sample_image_path):
        print(f"[!] Test image not found at '{sample_image_path}'.")
        sys.exit(1)

    # 4. Register face with real student_id from Supabase
    print(f"\n--- Step 3: Registering Student Face ({student_name} / {roll_number}) ---")
    reg_success = recognizer.register_student(
        student_id=student_id,
        name=student_name,
        roll_number=roll_number,
        image_path=sample_image_path
    )
    
    if not reg_success:
        print("[!] Registration failed.")
        sys.exit(1)

    # 5. Train LBPH model
    print("\n--- Step 4: Training LBPH Model ---")
    train_success = recognizer.train_model()
    if not train_success:
        print("[!] Training failed.")
        sys.exit(1)

    # 6. Recognize face
    print("\n--- Step 5: Recognizing Test Face ---")
    match_result, confidence = recognizer.recognize_test_face(sample_image_path)

    if match_result == "Unknown" or not match_result:
        print("[!] Face not recognized.")
        sys.exit(1)

    print(f"Recognized Student: {match_result['name']} (ID: {match_result['student_id']})")
    print(f"Confidence: {confidence:.2f}%")

    # Clean up any pre-existing attendance for clean idempotent test run
    client = get_supabase_client()
    client.table("attendance").delete().eq("student_id", student_id).eq("session_id", session_id).execute()

    # 7. Record Attendance in Supabase
    print("\n--- Step 6: Recording Attendance in Supabase ---")
    success, result = attendance_service.record_face_recognition_attendance(
        match_result=match_result,
        confidence=confidence,
        session_id=session_id
    )

    print(f"Attendance Record Result: Success={success}")

    # 8. Verify record exists in Supabase
    print("\n--- Step 7: Verifying Attendance Record in Supabase Table ---")
    verify_res = client.table("attendance") \
                        .select("*") \
                        .eq("student_id", student_id) \
                        .eq("session_id", session_id) \
                        .execute()
    
    if verify_res.data and len(verify_res.data) > 0:
        record = verify_res.data[0]
        print("Verification SUCCESS: Record found in Supabase 'attendance' table!")
        print(f"  - Record ID:    {record['id']}")
        print(f"  - Student ID:   {record['student_id']}")
        print(f"  - Session ID:   {record['session_id']}")
        print(f"  - Status:       {record['status']}")
        print(f"  - Confidence:   {record['confidence']}%")
        print(f"  - Created At:   {record['created_at']}")
    else:
        print("[!] VERIFICATION FAILED: Attendance record not found in database!")
        sys.exit(1)

    # 9. Test duplicate attendance prevention
    print("\n--- Step 8: Testing Duplicate Attendance Prevention ---")
    dup_success, dup_result = attendance_service.record_face_recognition_attendance(
        match_result=match_result,
        confidence=confidence,
        session_id=session_id
    )

    print(f"Duplicate Attendance Attempt Result: Success={dup_success}, Message='{dup_result}'")
    if not dup_success and dup_result == "Already marked":
        print("\n[+] SUCCESS: Duplicate attendance prevention verified!")
    else:
        print("[!] WARNING: Duplicate prevention did not return expected status.")

    print("\n==================================================")
    print("      ALL TEST STEPS COMPLETED SUCCESSFULLY       ")
    print("==================================================")

if __name__ == "__main__":
    test_attendance_integration()
