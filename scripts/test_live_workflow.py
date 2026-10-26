"""
Comprehensive Test Script for LIVE CLASSROOM SESSION + ATTENDANCE WORKFLOW.
Tests all 9 requirements from User Prompt:
 TEST 1: Teacher auth
 TEST 2: Start session -> creates session, active session_id, activates webcam monitoring
 TEST 3: Enrolled student face recognition -> student marked PRESENT for active session
 TEST 4: Multiple frames with same student -> no duplicate attendance records
 TEST 5: Activity detection -> alert generated with current session_id, toggle respected
 TEST 6: Stop session -> webcam stops, camera released, undetected become ABSENT
 TEST 7: Teacher edits attendance record (Absent -> Present)
 TEST 8: Teacher clicks Submit Attendance -> attendance finalized, edits locked
 TEST 9: Start second session -> new session_id, previous attendance intact
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add paths
ROOT = Path(__file__).resolve().parents[1]
AI_SERVICES = ROOT / "ai-services"
sys.path.insert(0, str(AI_SERVICES / "api"))
sys.path.insert(0, str(AI_SERVICES))
sys.path.insert(0, str(AI_SERVICES / "attention-monitoring"))
sys.path.insert(0, str(AI_SERVICES / "alert-engine"))
sys.path.insert(0, str(AI_SERVICES / "face-recognition"))

import cv2
import numpy as np
from fastapi.testclient import TestClient

from main import app
from dependencies import get_db, GLOBAL_SESSION_MANAGER, GLOBAL_CONFIG
import runtime as runtime_state
from face_registry import rebuild_recognizer

client = TestClient(app)
db = get_db()


def run_tests():
    print("=================================================================")
    print("STARTING TEST SUITE: LIVE CLASSROOM SESSION + ATTENDANCE WORKFLOW")
    print("=================================================================")

    # Ensure enrolled faces are trained into recognizer
    app = runtime_state.get_or_init_webcam_app()
    students_rows = db.table("students").select("*").execute().data or []
    if app and getattr(app, "recognizer", None):
        rebuild_info = rebuild_recognizer(app.recognizer, students_rows)
        print(f"[Setup] Rebuilt recognizer with students: {rebuild_info}")

    created_sessions = []

    try:
        # -------------------------------------------------------------
        # TEST 1: Teacher Auth
        # -------------------------------------------------------------
        print("\n--- TEST 1: Teacher Auth Verification ---")
        teachers = db.table("teachers").select("*").limit(1).execute().data
        assert teachers and len(teachers) > 0, "At least one teacher must exist"
        teacher_name = teachers[0]["name"]
        print(f"[PASS] Teacher verified: {teacher_name} ({teachers[0]['email']})")

        # -------------------------------------------------------------
        # TEST 2: Start Session
        # -------------------------------------------------------------
        print("\n--- TEST 2: Teacher clicks Start Session ---")
        start_payload = {
            "teacher_name": teacher_name,
            "subject": "Automated Test Session",
            "classroom": "Room-Test-101",
        }
        res = client.post("/api/sessions/start", json=start_payload)
        assert res.status_code == 201, f"Start session failed: {res.text}"
        data = res.json()
        session_id_1 = data["session_id"]
        created_sessions.append(session_id_1)
        assert session_id_1 and len(session_id_1) > 10, "session_id must be valid UUID"
        assert GLOBAL_SESSION_MANAGER.session_id == session_id_1, "session_manager active id must match"
        
        # Verify webcam monitoring is active
        time.sleep(1.0)
        assert runtime_state.is_monitoring_active(), "Webcam monitoring pipeline must become active"
        print(f"[PASS] Session 1 created: {session_id_1}")
        print(f"[PASS] Active session_id matches in SessionManager: {GLOBAL_SESSION_MANAGER.session_id}")
        print(f"[PASS] Webcam monitoring pipeline is ACTIVE (thread alive={runtime_state.is_monitoring_active()})")

        # Verify live attendance sheet before any detection:
        sheet_res = client.get(f"/api/attendance/{session_id_1}/sheet")
        assert sheet_res.status_code == 200
        sheet_data = sheet_res.json()
        assert sheet_data["session_active"] is True
        assert sheet_data["attendance_finalized"] is False
        # Undetected students must be "Not Yet Detected", detected students are "Present", NEVER "Absent"
        for rec in sheet_data["records"]:
            assert rec["status"] in ("Present", "Not Yet Detected"), f"Expected Present or Not Yet Detected during live session, got {rec['status']}"
            assert rec["status"] != "Absent", "Undetected students must not be called Absent while session is running"
        print(f"[PASS] Live sheet verified: {sheet_data['present_count']} Present, {sheet_data['not_detected_count']} Not Yet Detected, 0 Absent")

        # -------------------------------------------------------------
        # TEST 3: Enrolled Student Face Recognition -> Present
        # -------------------------------------------------------------
        print("\n--- TEST 3: Show an enrolled student's face to the webcam ---")
        # Find a student that has a real enrolled image on disk
        enrolled_student = None
        face_img = None
        faces_dir = AI_SERVICES / "data" / "faces"
        for s in students_rows:
            img_path = faces_dir / f"{s['id']}.jpg"
            if img_path.exists():
                test_img = cv2.imread(str(img_path))
                if test_img is not None:
                    enrolled_student = s
                    face_img = test_img
                    break

        assert enrolled_student is not None, "At least one enrolled student with face image must exist"
        print(f"[Setup] Using enrolled student for face recognition: {enrolled_student['name']} ({enrolled_student['roll_number']})")

        # Run face recognition on the student face
        rec_app = runtime_state.webcam_app
        match_data, face_conf = rec_app.recognizer.recognize_test_face(test_frame=face_img)
        assert match_data != "Unknown" and match_data is not None, "Student face should be recognized"
        assert match_data["student_id"] == enrolled_student["id"], "Recognized student_id should match enrolled student"
        print(f"[Face Recognizer] Recognized {match_data['name']} with confidence {face_conf:.1f}%")

        # Mark attendance via AttendanceService for this active session
        marked_ok, mark_res = rec_app.attendance_service.record_face_recognition_attendance(
            match_data, face_conf, session_id_1
        )
        assert marked_ok is True, f"Failed to mark attendance: {mark_res}"

        # Verify in database
        att_db = db.table("attendance").select("*").eq("session_id", session_id_1).eq("student_id", enrolled_student["id"]).execute().data
        assert att_db and len(att_db) == 1, "Attendance record must exist in Supabase for active session"
        assert att_db[0]["status"] == "Present", f"Student must be Present, got {att_db[0]['status']}"
        print(f"[PASS] Student {enrolled_student['name']} is PRESENT for session {session_id_1} (confidence={att_db[0]['confidence']}%)")

        # -------------------------------------------------------------
        # TEST 4: Multiple Frames with Same Student -> No Duplicates
        # -------------------------------------------------------------
        print("\n--- TEST 4: Keep student in front of camera for many frames (Duplicate Prevention) ---")
        for frame_idx in range(10):
            marked_again, msg = rec_app.attendance_service.record_face_recognition_attendance(
                match_data, face_conf, session_id_1
            )
            assert marked_again is False, f"Frame {frame_idx}: duplicate attendance was allowed!"
            assert "already" in msg.lower(), f"Expected already marked notice, got {msg}"

        # Verify DB still has exactly 1 record
        att_all = db.table("attendance").select("*").eq("session_id", session_id_1).eq("student_id", enrolled_student["id"]).execute().data
        assert len(att_all) == 1, f"Expected exactly 1 attendance record, found {len(att_all)}"
        print(f"[PASS] Verified: Exactly 1 attendance record exists in Supabase. Duplicates completely prevented.")

        # -------------------------------------------------------------
        # TEST 5: Activity Detection & Alert Generation
        # -------------------------------------------------------------
        print("\n--- TEST 5: Trigger activity detection alert ---")
        GLOBAL_CONFIG.phone_detection_enabled = True
        test_event = {
            "student_id": enrolled_student["id"],
            "activity": "phone_usage",
            "confidence": 92.5,
            "details": {"phone_detected": True},
        }
        alert_created = rec_app.alert_engine.process_activity_event(session_id_1, test_event, current_time=time.time())
        assert alert_created is True, "Alert should be created when toggle is enabled"

        # Check in DB
        alerts_db = db.table("classroom_alerts").select("*").eq("session_id", session_id_1).execute().data
        assert alerts_db and len(alerts_db) > 0, "Alert must be stored in Supabase with session_id"
        assert alerts_db[0]["alert_type"] == "phone_usage"
        print(f"[PASS] Alert created in Supabase for session {session_id_1}: {alerts_db[0]['alert_type']} ({alerts_db[0]['description']})")

        # Test toggle off -> no alert
        GLOBAL_CONFIG.phone_detection_enabled = False
        alert_suppressed = rec_app.alert_engine.process_activity_event(
            session_id_1,
            {"student_id": "other-student", "activity": "phone_usage", "confidence": 90.0},
            current_time=time.time() + 100,
        )
        assert alert_suppressed is False, "Alert must be suppressed when toggle is OFF"
        GLOBAL_CONFIG.phone_detection_enabled = True
        print("[PASS] Independent toggle verified: disabled activity does not generate alerts.")

        # -------------------------------------------------------------
        # TEST 6: Teacher Stops the Session
        # -------------------------------------------------------------
        print("\n--- TEST 6: Teacher stops the session ---")
        stop_res = client.post(f"/api/sessions/{session_id_1}/stop")
        assert stop_res.status_code == 200, f"Stop session failed: {stop_res.text}"
        stop_data = stop_res.json()
        assert stop_data["status"] == "stopped"

        # Verify webcam monitoring is stopped and camera released
        time.sleep(0.5)
        assert not runtime_state.is_monitoring_active(), "Webcam monitoring must be stopped and inactive"
        assert GLOBAL_SESSION_MANAGER.session_id is None, "session_manager session_id must be cleared"
        print("[PASS] Live monitoring stopped and camera resource released.")

        # Verify attendance sheet now has Present for detected and Absent for undetected
        sheet_after_stop = client.get(f"/api/attendance/{session_id_1}/sheet").json()
        assert sheet_after_stop["session_active"] is False
        assert sheet_after_stop["present_count"] >= 1, "Detected student must remain Present"
        assert sheet_after_stop["absent_count"] >= 1, "Undetected students must be marked Absent"
        detected_rec = next(r for r in sheet_after_stop["records"] if r["student_id"] == enrolled_student["id"])
        assert detected_rec["status"] == "Present", "Enrolled student recognized must be Present"
        assert sheet_after_stop["present_count"] + sheet_after_stop["absent_count"] == sheet_after_stop["total_registered"]
        for rec in sheet_after_stop["records"]:
            assert rec["status"] in ("Present", "Absent"), f"Invalid status {rec['status']} after session stopped"
        print(f"[PASS] Final attendance sheet generated: {sheet_after_stop['present_count']} Present, {sheet_after_stop['absent_count']} Absent")

        # -------------------------------------------------------------
        # TEST 7: Teacher Edits One Attendance Record (Absent -> Present)
        # -------------------------------------------------------------
        print("\n--- TEST 7: Teacher edits attendance record (Absent -> Present) ---")
        absent_record = next(r for r in sheet_after_stop["records"] if r["status"] == "Absent")
        absent_att_id = absent_record["attendance_id"]
        assert absent_att_id is not None, "Absent record must have an attendance_id in Supabase"

        edit_res = client.patch(f"/api/attendance/item/{absent_att_id}", json={"status": "Present"})
        assert edit_res.status_code == 200, f"Edit failed: {edit_res.text}"
        edited_att = edit_res.json()
        assert edited_att["status"] == "Present"
        assert edited_att["manually_corrected"] is True
        print(f"[PASS] Successfully changed {absent_record['name']} from Absent -> Present (manually_corrected=True)")

        # -------------------------------------------------------------
        # TEST 8: Teacher Clicks Submit Attendance
        # -------------------------------------------------------------
        print("\n--- TEST 8: Teacher clicks Submit Attendance ---")
        submit_res = client.post(f"/api/attendance/{session_id_1}/submit")
        assert submit_res.status_code == 200, f"Submit failed: {submit_res.text}"
        submit_data = submit_res.json()
        assert submit_data["status"] == "submitted"
        assert submit_data["attendance_finalized"] is True
        assert GLOBAL_SESSION_MANAGER.is_session_finalized(session_id_1) is True
        print(f"[PASS] Session attendance submitted and finalized at {submit_data.get('submitted_at')}")

        # Verify editing is now locked/disabled
        edit_after_submit = client.patch(f"/api/attendance/item/{absent_att_id}", json={"status": "Absent"})
        assert edit_after_submit.status_code == 400, "Editing after submit must be rejected with 400"
        print("[PASS] Normal editing is disabled after final submission.")

        # Verify duplicate submission is rejected/handled
        dup_submit = client.post(f"/api/attendance/{session_id_1}/submit")
        assert dup_submit.json().get("status") == "already_submitted"
        print("[PASS] Duplicate submission correctly prevented.")

        # -------------------------------------------------------------
        # TEST 9: Start Second Session (Isolation Test)
        # -------------------------------------------------------------
        print("\n--- TEST 9: Start a second session (Session Isolation) ---")
        start_res_2 = client.post("/api/sessions/start", json={
            "teacher_name": teacher_name,
            "subject": "Second Classroom Session",
            "classroom": "Room-Test-102"
        })
        assert start_res_2.status_code == 201
        session_id_2 = start_res_2.json()["session_id"]
        created_sessions.append(session_id_2)
        assert session_id_2 != session_id_1, "New session must have a unique session_id"
        assert GLOBAL_SESSION_MANAGER.session_id == session_id_2

        # Verify previous session records are completely unchanged
        sess1_sheet = client.get(f"/api/attendance/{session_id_1}/sheet").json()
        assert sess1_sheet["attendance_finalized"] is True
        assert sess1_sheet["present_count"] == sheet_after_stop["present_count"] + 1 # 1 from AI + 1 edited

        # Verify new session has attendance records belonging ONLY to session 2
        sess2_sheet = client.get(f"/api/attendance/{session_id_2}/sheet").json()
        assert sess2_sheet["session_active"] is True
        assert sess2_sheet["attendance_finalized"] is False
        sess2_att = db.table("attendance").select("*").eq("session_id", session_id_2).execute().data
        for a in sess2_att:
            assert a["session_id"] == session_id_2, "All new records must belong to session 2"
            assert a["session_id"] != session_id_1, "New records must not belong to session 1"
        print(f"[PASS] Session 2 started with fresh ID: {session_id_2}")
        print(f"[PASS] Session 1 attendance remained unchanged in Supabase.")
        print(f"[PASS] Session 2 attendance belongs only to session 2 (isolation verified).")

        # Clean up session 2
        client.post(f"/api/sessions/{session_id_2}/stop")

        print("\n=================================================================")
        print("ALL 9 WORKFLOW TESTS PASSED PERFECTLY!")
        print("=================================================================")

    finally:
        # Stop any running pipeline
        runtime_state.stop_monitoring_pipeline()
        # Clean up test sessions in database
        for sid in created_sessions:
            try:
                db.table("class_sessions").delete().eq("id", sid).execute()
            except Exception as e:
                print(f"[Cleanup] Error deleting test session {sid}: {e}")
        print("[Cleanup] Completed cleanup of test sessions.")


if __name__ == "__main__":
    run_tests()
