from talking_tracker import TalkingTracker
from monitoring_config import MonitoringConfig

config = MonitoringConfig()
config.talking_min_duration_seconds = 0.5
tracker = TalkingTracker(config)

events = [
    (True, 0.0), (False, 1.0), (False, 4.0),
    (True, 5.0), (True, 6.0), (False, 9.0),
    (True, 10.0), (True, 11.0), (False, 14.0),
    (True, 15.0), (True, 16.0), (False, 19.0),
    (True, 20.0), (True, 21.0)
]

for state, t in events:
    alert = tracker.process_audio_visual_state(state, current_time=t)
    print(f"t={t:<4} state={str(state):<5} | is_talking={tracker.is_currently_talking:<5} last_speech={tracker.last_speech_time:<4} events={len(tracker.event_history)}")
    if alert:
        print(f"  >>> ALERT! {alert} at t={t}")
