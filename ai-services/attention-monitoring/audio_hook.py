"""
Audio Activity Hook Interface.
Allows audio analysis services (decibel levels, speech detection, voice activity detection)
to seamlessly provide talking/murmuring evidence to the Classroom Activity Detector.
"""

class AudioActivityHook:
    def __init__(self):
        self._is_speech_detected = False
        self._speech_confidence = 0.0

    def set_speech_state(self, is_talking: bool, confidence: float = 0.0):
        """Called by audio monitoring service when speech/talking is detected."""
        self._is_speech_detected = is_talking
        self._speech_confidence = confidence

    def is_talking_detected(self) -> tuple[bool, float]:
        """Returns tuple of (is_talking_detected, confidence)."""
        return self._is_speech_detected, self._speech_confidence
