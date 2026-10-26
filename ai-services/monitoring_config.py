# backend monitoring configuration structure
class MonitoringConfig:
    def __init__(self):
        # Feature Toggles
        self.talking_detection_enabled = True
        self.audio_monitoring_enabled = True
        self.attendance_enabled = True
        self.phone_detection_enabled = True
        self.sleeping_detection_enabled = True
        self.looking_away_detection_enabled = True
        self.unnecessary_activity_enabled = True

        # Talking Thresholds
        self.talking_event_threshold = 5               # Alerts when reaching this number of distinct events
        self.talking_window_seconds = 300.0            # Count events within the last 5 minutes
        self.talking_min_duration_seconds = 2.0        # Speech must continuously last this long to be a single "event"
        self.talking_silence_gap_seconds = 2.0         # Allowed gap of silence before a continuous talk is split into a new event

        # Audio / Noise Thresholds
        self.audio_noise_threshold_db = 70.0           # Sustained classroom noise threshold (dB)
        self.audio_sustained_duration_seconds = 2.0    # Seconds of continuous excessive noise required
        self.audio_sample_rate = 16000                 # Standard microphone sampling rate (Hz)
        self.audio_chunk_duration = 0.5                # Segment duration for analysis (seconds)
        self.audio_smoothing_factor = 0.3              # Exponential smoothing weight for noise level

        # Alert Cooldowns
        self.cooldown_phone_usage = 60.0
        self.cooldown_sleeping = 120.0
        self.cooldown_looking_away = 60.0
        self.cooldown_unnecessary_activity = 60.0
        self.cooldown_prolonged_discussion = 300.0
        self.cooldown_excessive_noise = 60.0
    def update_setting(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
            return True
        return False
