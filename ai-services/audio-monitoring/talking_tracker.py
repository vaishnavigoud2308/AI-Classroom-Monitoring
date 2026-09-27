import time
from collections import deque

class TalkingTracker:
    def __init__(self, config):
        """
        config: instance of MonitoringConfig
        """
        self.config = config
        
        # State tracking for the CURRENT continuous talking event
        self.is_currently_talking = False
        self.current_talk_start = 0.0
        self.last_speech_time = 0.0
        
        # History of VALIDATED discrete talking events (tuple: (start_time, duration))
        self.event_history = deque()
        
        # Cooldown state
        self.last_alert_time = -self.config.cooldown_prolonged_discussion - 1.0

    def process_audio_visual_state(self, is_speech_active, current_time=None):
        """
        Takes real-time raw speech state (True/False) from Audio/Video hooks
        and updates the stateful talking event tracker. 
        Returns an Alert String if threshold met, else None.
        """
        if current_time is None:
            current_time = time.time()
            
        if not self.config.talking_detection_enabled:
            # If disabled, do not track or alert
            self._reset_current_talk()
            self.event_history.clear()
            return None
            
        # 1. Manage continuous speech buffer (Start/Stop with Silence Gap)
        if is_speech_active:
            if not self.is_currently_talking:
                # Started talking
                self.is_currently_talking = True
                self.current_talk_start = current_time
            self.last_speech_time = current_time
        else:
            if self.is_currently_talking:
                # They are quiet. Have they been quiet long enough to end the continuous event?
                time_since_speech = current_time - self.last_speech_time
                if time_since_speech > self.config.talking_silence_gap_seconds:
                    # The speech event has ended.
                    duration = self.last_speech_time - self.current_talk_start
                    self._finalize_event(self.current_talk_start, duration)
                    self._reset_current_talk()
                    
        # 2. Evaluate if we should trigger an alert (Threshold + Window + Cooldown)
        return self._evaluate_alert_state(current_time)

    def _reset_current_talk(self):
        self.is_currently_talking = False
        self.current_talk_start = 0.0
        self.last_speech_time = 0.0

    def _finalize_event(self, start_time, duration):
        """Validates if the continuous talking lasted long enough to be an 'Event'"""
        if duration >= self.config.talking_min_duration_seconds:
            self.event_history.append((start_time, duration))

    def _evaluate_alert_state(self, current_time):
        # Clean up events outside the monitoring window
        window_start = current_time - self.config.talking_window_seconds
        while self.event_history and self.event_history[0][0] < window_start:
            self.event_history.popleft()
            
        # Optional: Include the currently ongoing talking if it exceeds MIN duration
        ongoing_counts = 0
        if self.is_currently_talking:
            ongoing_duration = current_time - self.current_talk_start
            if ongoing_duration >= self.config.talking_min_duration_seconds:
                ongoing_counts = 1

        total_events = len(self.event_history) + ongoing_counts

        # Check threshold
        if total_events >= self.config.talking_event_threshold:
            # Check cooldown
            if (current_time - self.last_alert_time) > self.config.cooldown_prolonged_discussion:
                # Trigger Alert
                self.last_alert_time = current_time
                self.event_history.clear() # Optional: Clear history after an alert so we start fresh
                self._reset_current_talk()
                return "Possible Prolonged Discussion"
                
        return None
