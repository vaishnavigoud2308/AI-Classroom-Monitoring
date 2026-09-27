import os
import sys
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from alert_engine import AlertEngine
from monitoring_config import MonitoringConfig

class MockSupabase:
    def __init__(self):
        self.inserted_rows = []
        
    def table(self, table_name):
        self.current_table = table_name
        return self
        
    def insert(self, row):
        # We simulate Supabase insert format
        self.pending_row = row
        return self
        
    def execute(self):
        self.inserted_rows.append((self.current_table, self.pending_row))
        return type('obj', (object,), {'data': [self.pending_row]})

def create_event(activity, student_id="TEST_STUDENT"):
    return {
        "student_id": student_id,
        "activity": activity,
        "confidence": 99.0,
        "details": {},
        "timestamp": "test_time"
    }

def run_tests():
    print("==================================================")
    print("      Alert Engine Local Test Execution           ")
    print("==================================================\n")

    config = MonitoringConfig()
    # Reset all cooldowns to 60s for easier testing predictability, except talking
    config.cooldown_phone_usage = 60.0
    config.cooldown_prolonged_discussion = 300.0
    mock_db = MockSupabase()
    
    engine = AlertEngine(config=config, supabase_client=mock_db)
    session_id = "test-session-uuid"

    print("--- Test 1: Enabled phone detection creates an alert ---")
    config.phone_detection_enabled = True
    result = engine.process_activity_event(session_id, create_event("phone_usage"), current_time=100.0)
    assert result == True
    assert len(mock_db.inserted_rows) == 1
    recent_row = mock_db.inserted_rows[-1][1]
    assert recent_row["alert_type"] == "phone_usage"
    assert recent_row["description"] == "Phone Usage Detected"
    print("PASS")

    print("\n--- Test 2: Duplicate alerts within cooldown are suppressed ---")
    # Same student, same alert type, 10 seconds later (within 60s cooldown)
    result = engine.process_activity_event(session_id, create_event("phone_usage"), current_time=110.0)
    assert result == False
    assert len(mock_db.inserted_rows) == 1 # still 1
    print("PASS")
    
    print("\n--- Test 3: Same alert type passes AFTER cooldown expires ---")
    result = engine.process_activity_event(session_id, create_event("phone_usage"), current_time=170.1) # 100.0 + 60.0 cooldown + 0.1
    assert result == True
    assert len(mock_db.inserted_rows) == 2
    print("PASS")

    print("\n--- Test 4: Disabled phone detection creates NO alert ---")
    config.phone_detection_enabled = False
    # Use time far in the future
    result = engine.process_activity_event(session_id, create_event("phone_usage"), current_time=500.0)
    assert result == False
    assert len(mock_db.inserted_rows) == 2 # still 2
    print("PASS")

    print("\n--- Test 5: Prolonged discussion creates an alert ---")
    config.talking_detection_enabled = True
    result = engine.process_activity_event(session_id, create_event("prolonged_discussion"), current_time=500.0)
    assert result == True
    assert len(mock_db.inserted_rows) == 3
    recent_row = mock_db.inserted_rows[-1][1]
    assert recent_row["description"] == "Possible Prolonged Discussion"
    print("PASS")

    print("\n--- Test 6: Disabled talking detection creates NO alert ---")
    config.talking_detection_enabled = False
    result = engine.process_activity_event(session_id, create_event("prolonged_discussion"), current_time=900.0) # past cooldown
    assert result == False
    assert len(mock_db.inserted_rows) == 3 # still 3
    print("PASS")
    
    print("\n--- Test 7: Different enabled features generate alerts independently (No cross-cooldown) ---")
    config.sleeping_detection_enabled = True
    config.unnecessary_activity_enabled = True
    # At t=1000, trigger sleep.
    res1 = engine.process_activity_event(session_id, create_event("sleeping"), current_time=1000.0)
    # At t=1005 (within sleep cooldown), trigger unnecessary activity.
    res2 = engine.process_activity_event(session_id, create_event("unnecessary_activity"), current_time=1005.0)
    assert res1 == True
    assert res2 == True
    assert len(mock_db.inserted_rows) == 5
    print("PASS")

    print("\n--- Test 8: Alert contains all required fields ---")
    target_row = mock_db.inserted_rows[-1][1]
    required_keys = ["session_id", "student_id", "alert_type", "description", "confidence", "status", "created_at"]
    for key in required_keys:
        assert key in target_row, f"Missing {key} in DB row"
    assert target_row["status"] == "New"
    assert target_row["student_id"] == "TEST_STUDENT"
    assert target_row["session_id"] == "test-session-uuid"
    print("PASS")

    print("\n[SUCCESS] ALL ALERT ENGINE TESTS PASSED PERFECTLY.")

if __name__ == "__main__":
    run_tests()
