import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from activity_detector import ClassroomActivityDetector
from audio_hook import AudioActivityHook

__all__ = ["ClassroomActivityDetector", "AudioActivityHook"]
