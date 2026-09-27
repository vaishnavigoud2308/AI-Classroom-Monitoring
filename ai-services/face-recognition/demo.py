import os
from recognizer import FaceRecognizer
from attendance_service import AttendanceService

def run_local_demo():
    print("==================================================")
    print(" AI Classroom MVP: Face Recognition Local Demo")
    print("==================================================\n")
    
    # -------------------------------------------------------------
    # SETUP
    # IMPORTANT: To test the actual Supabase insert, you must provide
    # REAL a student UUID and session UUID that already exist in your db.
    # Otherwise, it will fail Database Foreign Key constraints!
    # -------------------------------------------------------------
    # Example placeholder: "ec989c9e-56e2-45e3-9ecb-38fe35f9227c"
    TEST_STUDENT_ID = "00000000-0000-0000-0000-000000000001" 
    TEST_SESSION_ID = "00000000-0000-0000-0000-000000000002"
    
    sample_image = "sample_face.jpg"
    
    if not os.path.exists(sample_image):
        print(f"[!] HALTED: Could not find '{sample_image}'.")
        print(f"Please put a JPG photo containing a clear face into the directory:")
        print(f"{os.path.abspath(os.path.dirname(__file__))}")
        print(f"and name it '{sample_image}' before running the demo.")
        return

    print("Step 1: Initializing modules...")
    recognizer = FaceRecognizer()
    
    # In a real environment, we would initialize AttendanceService here too,
    # but let's wait until we have a match so we don't connect unnecessarily if it fails.

    # -------------------------------------------------------------
    # REGISTRATION & TRAINING
    # -------------------------------------------------------------
    print("\nStep 2: Training / Registering the face from our database")
    success = recognizer.register_student(
        student_id=TEST_STUDENT_ID,
        name="John Doe",
        roll_number="CS-2026-01",
        image_path=sample_image # using the sample image for registration
    )
    
    if not success:
        print("Demo failed during Registration.")
        return
        
    # NEW REQUIREMENT for OpenCV: We must formally build and train the model 
    # after all registrations are loaded into memory.
    recognizer.train_model()

    # -------------------------------------------------------------
    # RECOGNITION
    # -------------------------------------------------------------
    print(f"\nStep 3: Simulating camera frame / testing recognition...")
    
    # For demo purposes, we will test the model using the exact same image.
    # Naturally, it should result in a 100% (or very high) match confidence.
    # You could change this to `test_face.jpg` if you provide a second image.
    match_result, confidence = recognizer.recognize_test_face(sample_image)
    
    if match_result == "Unknown":
        print(f"Result: The AI did not recognize the person in the frame (Confidence: {confidence:.2f}%).")
        return
        
    print(f"Result: IN-CLASS MATCH FOUND -> {match_result['name']} ({match_result['roll_number']})")
    print(f"Confidence Level: {confidence:.2f}%\n")
    
    # -------------------------------------------------------------
    # ATTENDANCE
    # -------------------------------------------------------------
    print("Step 4: Attempting to log attendance to Supabase...")
    
    if TEST_STUDENT_ID == "00000000-0000-0000-0000-000000000001":
        print("[!] WARNING: You are using the placeholder UUIDs in demo.py")
        print("This will likely crash during the database insert due to Foreign Key rules.")
        print("Please edit demo.py with real UUIDs from your tables to see a successful insert.")
    
    attendance = AttendanceService()
    success, data = attendance.mark_attendance(
        student_id=match_result['student_id'],
        session_id=TEST_SESSION_ID,
        confidence=confidence
    )
    
    if success:
        print("\n[SUCCESS] MVP TEST FINISHED CORRECTLY!")
        print("Attendance is now safely securely logged in Supabase.")
    else:
        print("\n[ERROR] Test did not finish properly. Check errors above.")

if __name__ == "__main__":
    run_local_demo()
