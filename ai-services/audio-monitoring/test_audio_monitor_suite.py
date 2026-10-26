"""
Comprehensive Test Suite for Audio Monitoring Module and AlertEngine Integration.

Covers all 12 core testing requirements from User Prompt:
1. Silence and ambient background noise.
2. Brief speech that should not trigger an alert (< minimum duration).
3. Sustained speech activity (>= minimum duration).
4. Five qualifying speech episodes triggering the configured repeated-event rule.
5. Cooldown and duplicate-alert prevention.
6. Audio monitoring disabled by the teacher (feature toggles).
7. Missing microphone or microphone permission failure gracefully handled.
8. Start and stop requests repeated multiple times (idempotency).
9. Classroom session changes and session termination (counter reset and scoping).
10. AlertEngine integration and correct session_id association.
11. Supabase persistence using existing classroom_alerts schema.
12. FastAPI audio monitoring endpoints (/api/monitoring/audio/*).
"""

from __future__ import annotations

import datetime
import math
import os
import sys
import time
from pathlib import Path

# Path setup
ROOT = Path(__file__).resolve().parents[2]
AI_SERVICES = ROOT / "ai-services"
sys.path.insert(0, str(AI_SERVICES / "api"))
sys.path.insert(0, str(AI_SERVICES))
sys.path.insert(0, str(AI_SERVICES / "audio-monitoring"))
sys.path.insert(0, str(AI_SERVICES / "alert-engine"))
sys.path.insert(0, str(AI_SERVICES / "attention-monitoring"))

import numpy as np
import pytest

from audio_monitor import AudioMonitor
from talking_tracker import TalkingTracker
from monitoring_config import MonitoringConfig
from alert_engine import AlertEngine
from audio_hook import AudioActivityHook


class MockSupabaseClient:
    """Mock Supabase client recording inserted rows into classroom_alerts."""

    def __init__(self):
        self.inserted_rows = []
        self.current_table = None

    def table(self, table_name: str):
        self.current_table = table_name
        return self

    def insert(self, row: dict):
        self.pending_row = row
        return self

    def execute(self):
        self.inserted_rows.append((self.current_table, self.pending_row))
        return type("MockResponse", (), {"data": [self.pending_row]})


def generate_synthetic_audio(
    duration_sec: float,
    sample_rate: int = 16000,
    audio_type: str = "silence",
    amplitude: float = 0.5,
) -> np.ndarray:
    """
    Generates synthetic 16kHz audio samples for automated headless testing:
    - silence: very low amplitude noise (around 32 dB)
    - noise: high amplitude white noise (above 75 dB)
    - speech: simulated voice harmonics (fundamental 200Hz + formants 800Hz, 1500Hz, 2500Hz)
    """
    num_samples = int(duration_sec * sample_rate)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False)

    if audio_type == "silence":
        # Pure quiet room noise (~32 dB)
        samples = np.random.normal(0, 0.0005, num_samples).astype(np.float32)
    elif audio_type == "noise":
        # Heavy classroom background noise (> 75 dB)
        samples = np.random.normal(0, 0.25, num_samples).astype(np.float32)
    elif audio_type == "speech":
        # Synthetic speech-like harmonic signal in human vocal range (300-3400 Hz)
        f0 = 220.0
        wave = (
            0.5 * np.sin(2 * np.pi * f0 * t)
            + 0.3 * np.sin(2 * np.pi * (f0 * 3) * t)
            + 0.2 * np.sin(2 * np.pi * 1200.0 * t)
            + 0.1 * np.sin(2 * np.pi * 2400.0 * t)
        )
        # Apply amplitude modulation to simulate syllables (3-4 syllables per second)
        envelope = 0.5 * (1.0 + np.sin(2 * np.pi * 3.5 * t))
        samples = (wave * envelope * amplitude).astype(np.float32)
    else:
        samples = np.zeros(num_samples, dtype=np.float32)

    return samples.clip(-1.0, 1.0)


# =============================================================================
# TEST 1: Silence and Ambient Background Noise
# =============================================================================
def test_1_silence_and_ambient_noise():
    print("\n--- TEST 1: Silence and Ambient Background Noise ---")
    config = MonitoringConfig()
    mock_db = MockSupabaseClient()
    alert_engine = AlertEngine(config=config, supabase_client=mock_db)
    monitor = AudioMonitor(config=config, alert_engine=alert_engine)
    monitor.session_id = "test-session-silence"

    silence = generate_synthetic_audio(0.5, audio_type="silence")
    result = monitor.process_audio_chunk(silence, current_time=0.0)

    # Decibels should be low (~30-40 dB), no speech detected, no alerts generated
    assert result["sound_level_db"] < 45.0, f"Expected quiet ambient level, got {result['sound_level_db']} dB"
    assert result["is_speech"] is False, "Silence must not be detected as speech"
    assert len(mock_db.inserted_rows) == 0, "No alerts should be triggered on ambient silence"
    print(f"PASS: Ambient silence measured at {result['sound_level_db']:.1f} dB (No speech/alerts)")


# =============================================================================
# TEST 2: Brief Speech Activity (< Minimum Duration)
# =============================================================================
def test_2_brief_speech_below_minimum_duration():
    print("\n--- TEST 2: Brief Speech (< minimum duration) ---")
    config = MonitoringConfig()
    config.talking_min_duration_seconds = 2.0
    config.talking_silence_gap_seconds = 2.0
    tracker = TalkingTracker(config)

    t = 0.0
    # Simulate 0.8s of speech (less than 2.0s threshold)
    for _ in range(8):
        tracker.process_audio_visual_state(True, current_time=t)
        t += 0.1

    # Follow with 3.0s of silence
    alert = None
    for _ in range(30):
        alert = tracker.process_audio_visual_state(False, current_time=t)
        t += 0.1

    assert len(tracker.event_history) == 0, "Brief speech < 2.0s must not count as a qualifying episode"
    assert alert is None, "Brief speech must not trigger an alert"
    print("PASS: Brief speech discarded; 0 episodes registered.")


# =============================================================================
# TEST 3: Sustained Speech Activity (>= Minimum Duration)
# =============================================================================
def test_3_sustained_speech_qualifies_episode():
    print("\n--- TEST 3: Sustained Speech (>= minimum duration) ---")
    config = MonitoringConfig()
    config.talking_min_duration_seconds = 2.0
    config.talking_silence_gap_seconds = 2.0
    tracker = TalkingTracker(config)

    t = 0.0
    # 2.5s of continuous speech
    for _ in range(25):
        tracker.process_audio_visual_state(True, current_time=t)
        t += 0.1

    # 2.5s silence gap to finalize the episode
    for _ in range(25):
        tracker.process_audio_visual_state(False, current_time=t)
        t += 0.1

    assert len(tracker.event_history) == 1, f"Expected exactly 1 episode, got {len(tracker.event_history)}"
    print("PASS: Sustained speech of 2.5s successfully registered 1 qualifying episode.")


# =============================================================================
# TEST 4: Five Qualifying Episodes Trigger Repeated-Speech Rule
# =============================================================================
def test_4_five_episodes_trigger_prolonged_discussion():
    print("\n--- TEST 4: Five Qualifying Episodes Rule ---")
    config = MonitoringConfig()
    config.talking_event_threshold = 5
    config.talking_window_seconds = 300.0
    config.talking_min_duration_seconds = 2.0
    config.talking_silence_gap_seconds = 2.0
    mock_db = MockSupabaseClient()
    alert_engine = AlertEngine(config=config, supabase_client=mock_db)
    monitor = AudioMonitor(config=config, alert_engine=alert_engine)
    session_id = "test-session-episodes"
    monitor.session_id = session_id

    speech_chunk = generate_synthetic_audio(0.5, audio_type="speech", amplitude=0.7)
    silence_chunk = generate_synthetic_audio(0.5, audio_type="silence")

    current_t = 100.0
    for episode_idx in range(5):
        # 2.5s speech (5 chunks of 0.5s)
        for _ in range(5):
            monitor.process_audio_chunk(speech_chunk, current_time=current_t)
            current_t += 0.5
        # 2.5s silence gap (5 chunks of 0.5s)
        for _ in range(5):
            monitor.process_audio_chunk(silence_chunk, current_time=current_t)
            current_t += 0.5

    # Verify that an alert was stored in Supabase with correct alert_type and session_id
    prolonged_alerts = [r[1] for r in mock_db.inserted_rows if r[1]["alert_type"] == "prolonged_discussion"]
    assert len(prolonged_alerts) == 1, f"Expected 1 prolonged_discussion alert, found {len(prolonged_alerts)}"
    assert prolonged_alerts[0]["session_id"] == session_id
    assert prolonged_alerts[0]["description"] == "Possible Prolonged Discussion"
    print(f"PASS: 5 qualifying episodes triggered alert in Supabase for session {session_id}.")


# =============================================================================
# TEST 5: Cooldown and Duplicate-Alert Prevention
# =============================================================================
def test_5_cooldown_prevents_duplicate_alerts():
    print("\n--- TEST 5: Cooldown and Duplicate-Alert Prevention ---")
    config = MonitoringConfig()
    config.cooldown_prolonged_discussion = 300.0
    mock_db = MockSupabaseClient()
    alert_engine = AlertEngine(config=config, supabase_client=mock_db)
    session_id = "test-cooldown-session"

    payload = {
        "student_id": None,
        "activity": "prolonged_discussion",
        "confidence": 95.0,
        "details": {},
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    # First alert should succeed
    ok_1 = alert_engine.process_activity_event(session_id, payload, current_time=100.0)
    assert ok_1 is True, "First alert should be processed"
    assert len(mock_db.inserted_rows) == 1

    # Second alert 30s later (within 300s cooldown) should be suppressed
    ok_2 = alert_engine.process_activity_event(session_id, payload, current_time=130.0)
    assert ok_2 is False, "Duplicate alert within cooldown must be suppressed"
    assert len(mock_db.inserted_rows) == 1

    # Third alert after cooldown expires (350s later) should succeed
    ok_3 = alert_engine.process_activity_event(session_id, payload, current_time=450.0)
    assert ok_3 is True, "Alert after cooldown expiration should be processed"
    assert len(mock_db.inserted_rows) == 2
    print("PASS: Cooldown successfully suppressed duplicate alerts within 300 seconds.")


# =============================================================================
# TEST 6: Audio Monitoring Disabled by Teacher (Toggles)
# =============================================================================
def test_6_disabled_toggle_suppresses_audio_alerts():
    print("\n--- TEST 6: Feature Toggles Respected ---")
    config = MonitoringConfig()
    config.audio_monitoring_enabled = False
    config.talking_detection_enabled = False

    mock_db = MockSupabaseClient()
    alert_engine = AlertEngine(config=config, supabase_client=mock_db)
    monitor = AudioMonitor(config=config, alert_engine=alert_engine)
    monitor.session_id = "test-disabled-session"

    loud_noise = generate_synthetic_audio(0.5, audio_type="noise")
    speech = generate_synthetic_audio(0.5, audio_type="speech")

    t = 0.0
    for _ in range(10):
        monitor.process_audio_chunk(loud_noise, current_time=t)
        t += 0.5
    for _ in range(10):
        monitor.process_audio_chunk(speech, current_time=t)
        t += 0.5

    assert len(mock_db.inserted_rows) == 0, "No audio alerts allowed when toggles are disabled"
    print("PASS: Audio monitoring disabled by teacher; all alerts suppressed.")


# =============================================================================
# TEST 7: Missing Microphone / Permission Failure Handled Gracefully
# =============================================================================
def test_7_missing_microphone_handled_gracefully(monkeypatch):
    print("\n--- TEST 7: Missing Microphone Graceful Fallback ---")
    config = MonitoringConfig()
    monitor = AudioMonitor(config=config)

    # Simulate environment where no input devices exist
    import sounddevice as sd

    def mock_query_devices():
        # Only output speakers, no input mics
        return [{"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2}]

    monkeypatch.setattr(sd, "query_devices", mock_query_devices)

    ok, err = monitor.start_monitoring(session_id="no-mic-session")
    # Non-fatal start: system doesn't crash, status reflects unavailable
    status = monitor.get_status()
    assert status["audio_status"] in ("unavailable", "stopped", "disabled")
    assert status["audio_error"] is not None
    print(f"PASS: Handled missing microphone cleanly (status={status['audio_status']}, error={status['audio_error']})")


# =============================================================================
# TEST 8: Repeated Start and Stop Requests (Idempotency)
# =============================================================================
def test_8_start_stop_idempotency():
    print("\n--- TEST 8: Start and Stop Idempotency ---")
    config = MonitoringConfig()
    monitor = AudioMonitor(config=config)
    session_id = "test-idempotency-session"

    # Repeated starts
    res1, _ = monitor.start_monitoring(session_id=session_id)
    res2, _ = monitor.start_monitoring(session_id=session_id)
    res3, _ = monitor.start_monitoring(session_id=session_id)
    assert res1 is True and res2 is True and res3 is True

    # Repeated stops
    stop1 = monitor.stop_monitoring()
    stop2 = monitor.stop_monitoring()
    stop3 = monitor.stop_monitoring()
    assert stop1 is True and stop2 is True and stop3 is True
    assert monitor.audio_status == "stopped"
    print("PASS: Repeated start and stop calls execute idempotently without leak or error.")


# =============================================================================
# TEST 9: Session Changes and Termination Reset Episode History
# =============================================================================
def test_9_session_change_resets_episodes():
    print("\n--- TEST 9: Session Changes and Counter Reset ---")
    config = MonitoringConfig()
    monitor = AudioMonitor(config=config)

    # Start Session A and record 3 episodes
    monitor.start_monitoring(session_id="session-AAA")
    for _ in range(3):
        monitor.talking_tracker.event_history.append((time.time(), 2.5))
    assert len(monitor.talking_tracker.event_history) == 3

    # Switch to Session B
    monitor.start_monitoring(session_id="session-BBB")
    assert monitor.session_id == "session-BBB"
    assert len(monitor.talking_tracker.event_history) == 0, "Episode history must reset on new session"

    # Stop session
    monitor.stop_monitoring()
    assert monitor.audio_status == "stopped"
    assert len(monitor.talking_tracker.event_history) == 0
    print("PASS: Session changes and termination successfully reset episode counters and scope.")


# =============================================================================
# TEST 10 & 11: AlertEngine Schema and Supabase Persistence
# =============================================================================
def test_10_and_11_alert_engine_supabase_schema():
    print("\n--- TEST 10 & 11: AlertEngine Schema and Supabase Persistence ---")
    config = MonitoringConfig()
    mock_db = MockSupabaseClient()
    alert_engine = AlertEngine(config=config, supabase_client=mock_db)

    # 1. Test excessive_noise schema
    noise_event = {
        "student_id": None,
        "activity": "excessive_noise",
        "confidence": 78.5,
        "details": {"db": 78.5},
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    alert_engine.process_activity_event("session-123", noise_event, current_time=100.0)

    # 2. Test prolonged_discussion schema
    talking_event = {
        "student_id": None,
        "activity": "prolonged_discussion",
        "confidence": 95.0,
        "details": {"episodes": 5},
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    alert_engine.process_activity_event("session-123", talking_event, current_time=100.0)

    assert len(mock_db.inserted_rows) == 2
    for table_name, row in mock_db.inserted_rows:
        assert table_name == "classroom_alerts", "Alerts must insert into public.classroom_alerts"
        # Validate columns against existing schema
        assert "session_id" in row and row["session_id"] == "session-123"
        assert "alert_type" in row and row["alert_type"] in ("excessive_noise", "prolonged_discussion")
        assert "description" in row and isinstance(row["description"], str)
        assert "status" in row and row["status"] == "New"
        assert "created_at" in row and isinstance(row["created_at"], str)
        assert row["student_id"] is None  # Classroom-wide audio alerts have None for student_id

    print("PASS: Schema and Supabase persistence verified for classroom_alerts.")


# =============================================================================
# TEST 12: FastAPI Audio Endpoints Integration
# =============================================================================
def test_12_fastapi_audio_endpoints():
    print("\n--- TEST 12: FastAPI Audio Endpoints (/api/monitoring/audio/*) ---")
    from fastapi.testclient import TestClient
    from main import app
    from dependencies import GLOBAL_SESSION_MANAGER, GLOBAL_CONFIG
    import runtime as runtime_state

    client = TestClient(app)

    # 1. Check audio status endpoint
    res_status = client.get("/api/monitoring/audio/status")
    assert res_status.status_code == 200
    stat_data = res_status.json()
    assert "audio_status" in stat_data
    assert "current_sound_level_db" in stat_data

    # 2. Attempt start without active session -> HTTP 400
    orig_sess = GLOBAL_SESSION_MANAGER.session_id
    GLOBAL_SESSION_MANAGER.session_id = None
    res_start_no_sess = client.post("/api/monitoring/audio/start")
    assert res_start_no_sess.status_code == 400

    # 3. Start with active session
    GLOBAL_SESSION_MANAGER.session_id = "test-api-session-uuid"
    res_start = client.post("/api/monitoring/audio/start")
    assert res_start.status_code == 200
    start_data = res_start.json()
    assert start_data["ok"] is True
    assert start_data["session_id"] == "test-api-session-uuid"

    # 4. Stop audio monitoring
    res_stop = client.post("/api/monitoring/audio/stop")
    assert res_stop.status_code == 200
    stop_data = res_stop.json()
    assert stop_data["ok"] is True
    assert stop_data["audio_status"] == "stopped"

    # Restore session
    GLOBAL_SESSION_MANAGER.session_id = orig_sess
    print("PASS: FastAPI audio monitoring endpoints verified.")


if __name__ == "__main__":
    print("=================================================================")
    print("RUNNING COMPREHENSIVE AUDIO MONITORING TEST SUITE")
    print("=================================================================")
    test_1_silence_and_ambient_noise()
    test_2_brief_speech_below_minimum_duration()
    test_3_sustained_speech_qualifies_episode()
    test_4_five_episodes_trigger_prolonged_discussion()
    test_5_cooldown_prevents_duplicate_alerts()
    test_6_disabled_toggle_suppresses_audio_alerts()
    # Mock monkeypatch for direct test
    class SimpleMonkeyPatch:
        def setattr(self, target, name, val):
            setattr(target, name, val)
    test_7_missing_microphone_handled_gracefully(SimpleMonkeyPatch())
    test_8_start_stop_idempotency()
    test_9_session_change_resets_episodes()
    test_10_and_11_alert_engine_supabase_schema()
    test_12_fastapi_audio_endpoints()
    print("\n[ALL 12 AUDIO MONITORING TESTS PASSED PERFECTLY]")
