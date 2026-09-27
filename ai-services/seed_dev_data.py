import os
import sys
import datetime

# Ensure parent directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from config import get_supabase_client

def ensure_dev_seed_data():
    """
    Inserts minimal initial development records (Teacher, Student, Class Session)
    if they do not already exist in Supabase. Returns the seed record details.
    """
    client = get_supabase_client()
    print("Checking Supabase development seed records...")

    # 1. Ensure Teacher
    teacher_res = client.table("teachers").select("*").eq("email", "alan.turing@example.com").execute()
    if not teacher_res.data:
        teacher_ins = client.table("teachers").insert({
            "name": "Dr. Alan Turing",
            "email": "alan.turing@example.com"
        }).execute()
        teacher = teacher_ins.data[0]
        print(f"Created Seed Teacher: {teacher['name']} ({teacher['id']})")
    else:
        teacher = teacher_res.data[0]
        print(f"Found Existing Seed Teacher: {teacher['name']} ({teacher['id']})")

    # 2. Ensure Student
    student_res = client.table("students").select("*").eq("roll_number", "TEST001").execute()
    if not student_res.data:
        student_ins = client.table("students").insert({
            "name": "Kiran",
            "roll_number": "TEST001",
            "email": "kiran.test@example.com"
        }).execute()
        student = student_ins.data[0]
        print(f"Created Seed Student: {student['name']} ({student['id']})")
    else:
        student = student_res.data[0]
        print(f"Found Existing Seed Student: {student['name']} ({student['id']})")

    # 3. Ensure Class Session
    session_res = client.table("class_sessions").select("*").eq("subject", "Computer Vision 101").execute()
    if not session_res.data:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        session_ins = client.table("class_sessions").insert({
            "teacher_id": teacher["id"],
            "subject": "Computer Vision 101",
            "classroom": "Room 301",
            "start_time": now_iso
        }).execute()
        session = session_ins.data[0]
        print(f"Created Seed Session: {session['subject']} ({session['id']})")
    else:
        session = session_res.data[0]
        print(f"Found Existing Seed Session: {session['subject']} ({session['id']})")

    return teacher, student, session

if __name__ == "__main__":
    ensure_dev_seed_data()
