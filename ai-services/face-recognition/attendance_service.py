import sys
import os

# Dynamically add the ai-services parent directory to the python path 
# so we can import the 'config.py' helper module
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from config import get_supabase_client

class AttendanceService:
    """
    Service responsible for interacting with the Supabase database
    to record class attendance securely.
    """
    def __init__(self):
        # Initialize the Supabase client once per service lifecycle
        self.supabase = get_supabase_client()

    def mark_attendance(self, student_id, session_id, confidence):
        """
        Creates an attendance record in the database for the recognized student.
        Prevents duplicate entries (student marked present twice in same session).
        """
        try:
            # 1. Verification: Query database to see if record already exists
            response = self.supabase.table("attendance") \
                        .select("id") \
                        .eq("student_id", student_id) \
                        .eq("session_id", session_id) \
                        .execute()
            
            if response.data and len(response.data) > 0:
                print(f"Notice: Attendance was already marked for student ID {student_id} in this session.")
                return False, "Already marked"

            # 2. Insertion: Construct the new record
            new_record = {
                "student_id": student_id,
                "session_id": session_id,
                "status": "Present",
                "confidence": round(float(confidence), 2),
                "manually_corrected": False # Because AI did it automatically
            }
            
            # Send payload to Supabase
            insert_response = self.supabase.table("attendance").insert(new_record).execute()
            
            print(f"Success: Marked attendance for student ID {student_id} with confidence {confidence:.2f}%.")
            return True, insert_response.data
            
        except Exception as e:
            print(f"Error marking attendance: {e}")
            return False, str(e)

    def record_face_recognition_attendance(self, match_result, confidence, session_id):
        """
        Takes the output from FaceRecognizer.recognize_test_face() and marks attendance
        if a valid student was recognized.
        """
        if not match_result or match_result == "Unknown":
            print("Notice: Face was not recognized as a registered student. Attendance skipped.")
            return False, "Student not recognized"
            
        student_id = match_result.get("student_id")
        if not student_id:
            print("Error: Recognized match data missing student_id.")
            return False, "Invalid match data"
            
        return self.mark_attendance(student_id=student_id, session_id=session_id, confidence=confidence)

