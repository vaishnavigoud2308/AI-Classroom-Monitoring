"""
Production-grade Audio Monitoring Module for AI-Powered Classroom Monitoring.

Features:
- Captures real-time microphone stream via sounddevice in short memory-only chunks.
- Computes calibrated Decibel SPL sound levels with exponential smoothing.
- Detects human voice activity using WebRTC VAD with spectral/energy fallback.
- Detects continuous excessive classroom noise (> threshold for sustained duration).
- Tracks discrete speech episodes over time via TalkingTracker (5 episodes rule).
- Integrates cleanly with AlertEngine and Supabase classroom_alerts table.
- Gracefully handles missing microphone, permission errors, and audio interruptions.
- Never records or permanently stores raw classroom audio, strictly preserving privacy.
- Fully testable with mock audio frames, simulated chunks, and headless environments.
"""

from __future__ import annotations

import datetime
import math
import os
import queue
import sys
import threading
import time
from typing import Any, Optional, Tuple

import numpy as np

# Ensure module pathing
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for p in (current_dir, parent_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from monitoring_config import MonitoringConfig
from talking_tracker import TalkingTracker

# Optional WebRTC VAD
try:
    import webrtcvad
    WEBRTC_VAD_AVAILABLE = True
except Exception:
    webrtcvad = None
    WEBRTC_VAD_AVAILABLE = False

# Optional Sounddevice
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except Exception:
    sd = None
    SOUNDDEVICE_AVAILABLE = False


class AudioMonitor:
    """
    Dedicated classroom audio monitor.
    Operates in short in-memory frames without permanent audio recording.
    """

    def __init__(
        self,
        config: Optional[MonitoringConfig] = None,
        alert_engine: Optional[Any] = None,
        audio_hook: Optional[Any] = None,
        session_manager: Optional[Any] = None,
        sample_rate: Optional[int] = None,
        chunk_duration: Optional[float] = None,
    ):
        self.config = config or MonitoringConfig()
        self.alert_engine = alert_engine
        self.audio_hook = audio_hook
        self.session_manager = session_manager

        self.sample_rate = int(sample_rate or getattr(self.config, "audio_sample_rate", 16000))
        self.chunk_duration = float(chunk_duration or getattr(self.config, "audio_chunk_duration", 0.5))
        self.chunk_samples = max(160, int(self.sample_rate * self.chunk_duration))

        self.session_id: Optional[str] = None
        self.talking_tracker = TalkingTracker(self.config)

        # Lifecycle & Status: "stopped" | "starting" | "active" | "unavailable" | "error"
        self.audio_status = "stopped"
        self.audio_error: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stream: Optional[Any] = None
        self._lifecycle_lock = threading.Lock()
        self._audio_queue: queue.Queue = queue.Queue(maxsize=50)

        # Real-time metrics
        self.current_sound_level_db = 0.0
        self.smoothed_sound_level_db = 0.0
        self._is_speech_active = False
        self._confidence = 0.0
        self._sustained_noise_start: Optional[float] = None

        # VAD Engine
        self.vad = None
        if WEBRTC_VAD_AVAILABLE and webrtcvad is not None:
            try:
                # Mode 2 is a balanced VAD aggressiveness for classroom acoustics
                self.vad = webrtcvad.Vad(2)
            except Exception as e:
                print(f"[AudioMonitor] Could not initialize WebRTC VAD: {e}")
                self.vad = None

    # -------------------------------------------------------------------------
    # Core Audio Math & Analysis
    # -------------------------------------------------------------------------

    def _calculate_db(self, samples: np.ndarray) -> float:
        """
        Calculates calibrated Decibel SPL equivalent from float audio in [-1.0, 1.0].
        Standard reference: silence floor ~ 30-35 dB, typical speech ~ 55-65 dB, loud > 70 dB.
        """
        if len(samples) == 0:
            return 30.0
        rms = float(np.sqrt(np.mean(np.square(samples))))
        if rms <= 1e-6:
            return 30.0
        db = 20.0 * math.log10(rms) + 90.0
        return float(min(110.0, max(30.0, db)))

    def _detect_speech_in_chunk(
        self, samples_int16: np.ndarray, samples_float: np.ndarray
    ) -> Tuple[bool, float]:
        """
        Detects whether the chunk contains human speech activity.
        Uses WebRTC VAD on 30ms sub-frames (480 samples at 16kHz) when available,
        with spectral/energy heuristic fallback.
        """
        if len(samples_int16) == 0:
            return False, 0.0

        # Sub-frame duration for WebRTC VAD: 30ms (at 16kHz = 480 samples = 960 bytes)
        frame_len = int(self.sample_rate * 0.03)  # 480 samples
        frame_bytes_len = frame_len * 2  # 16-bit PCM = 2 bytes per sample

        total_frames = 0
        speech_frames = 0

        raw_bytes = samples_int16.tobytes()

        if self.vad is not None and self.sample_rate in (8000, 16000, 32000, 48000):
            # WebRTC VAD Analysis
            for offset in range(0, len(raw_bytes) - frame_bytes_len + 1, frame_bytes_len):
                frame_chunk = raw_bytes[offset : offset + frame_bytes_len]
                total_frames += 1
                try:
                    if self.vad.is_speech(frame_chunk, self.sample_rate):
                        speech_frames += 1
                except Exception:
                    pass
        else:
            # Fallback Energy + Zero-Crossing Rate VAD
            # Human speech typically has ZCR between 0.04 and 0.45 and energy above silence floor
            for offset in range(0, len(samples_float) - frame_len + 1, frame_len):
                sub = samples_float[offset : offset + frame_len]
                total_frames += 1
                rms = float(np.sqrt(np.mean(np.square(sub))))
                zero_crossings = np.sum(np.diff(sub > 0) != 0) / float(frame_len)
                if rms > 0.015 and (0.04 <= zero_crossings <= 0.45):
                    speech_frames += 1

        if total_frames == 0:
            return False, 0.0

        speech_ratio = speech_frames / float(total_frames)

        # Spectral filter: Speech energy concentrated in 300-3400 Hz
        # Check frequency band ratio to reject electrical hum (<200Hz) or high hiss (>4000Hz)
        try:
            fft_mag = np.abs(np.fft.rfft(samples_float))
            freqs = np.fft.rfftfreq(len(samples_float), 1.0 / self.sample_rate)
            speech_band_mask = (freqs >= 300) & (freqs <= 3400)
            speech_energy = float(np.sum(fft_mag[speech_band_mask]))
            total_energy = float(np.sum(fft_mag)) + 1e-6
            band_ratio = speech_energy / total_energy
        except Exception:
            band_ratio = 0.5

        # Qualifying speech chunk: >= 35% speech frames and sound level >= 45 dB
        current_db = self._calculate_db(samples_float)
        is_speech = (speech_ratio >= 0.35) and (band_ratio >= 0.25) and (current_db >= 45.0)
        confidence = float(min(1.0, max(0.0, speech_ratio * 1.2))) if is_speech else 0.0

        return is_speech, confidence

    def process_audio_chunk(
        self, audio_data: np.ndarray, current_time: Optional[float] = None
    ) -> dict:
        """
        Processes a single in-memory audio chunk.
        Calculates decibel levels, updates exponential smoothing,
        evaluates sustained excessive noise alerts, runs speech VAD,
        and feeds TalkingTracker for prolonged discussion alerts.
        """
        if current_time is None:
            current_time = time.time()

        # Convert to float array in [-1.0, 1.0] and int16 array in [-32768, 32767]
        if audio_data.dtype == np.int16:
            samples_int16 = audio_data.flatten()
            samples_float = (samples_int16.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
        else:
            samples_float = audio_data.astype(np.float32).flatten().clip(-1.0, 1.0)
            samples_int16 = (samples_float * 32767.0).astype(np.int16)

        # 1. Sound level (dB) & smoothing
        raw_db = self._calculate_db(samples_float)
        alpha = float(getattr(self.config, "audio_smoothing_factor", 0.3))
        if self.smoothed_sound_level_db <= 1.0:
            self.smoothed_sound_level_db = raw_db
        else:
            self.smoothed_sound_level_db = (1.0 - alpha) * self.smoothed_sound_level_db + alpha * raw_db
        self.current_sound_level_db = raw_db

        # 2. Excessive Noise Detection (> noise threshold sustained for duration)
        noise_threshold = float(getattr(self.config, "audio_noise_threshold_db", 70.0))
        noise_duration = float(getattr(self.config, "audio_sustained_duration_seconds", 2.0))
        noise_enabled = bool(getattr(self.config, "audio_monitoring_enabled", True))

        if noise_enabled and self.smoothed_sound_level_db >= noise_threshold:
            if self._sustained_noise_start is None:
                self._sustained_noise_start = current_time
            elif (current_time - self._sustained_noise_start) >= noise_duration:
                # Trigger classroom-wide Excessive Noise alert
                self._emit_alert(
                    activity="excessive_noise",
                    confidence=self.smoothed_sound_level_db,
                    current_time=current_time,
                    details={
                        "sound_level_db": round(self.smoothed_sound_level_db, 1),
                        "threshold_db": noise_threshold,
                        "duration_seconds": round(current_time - self._sustained_noise_start, 1),
                    },
                )
        else:
            self._sustained_noise_start = None

        # 3. Voice Activity Detection (VAD)
        is_speech, confidence = self._detect_speech_in_chunk(samples_int16, samples_float)
        self._is_speech_active = is_speech
        self._confidence = confidence

        # Update AudioActivityHook for multi-modal combination (e.g. ActivityDetector)
        if self.audio_hook is not None and hasattr(self.audio_hook, "set_speech_state"):
            self.audio_hook.set_speech_state(is_speech, confidence)

        # 4. Episode Tracking & Repeated-Speech Rule
        talking_enabled = bool(getattr(self.config, "talking_detection_enabled", True))
        if talking_enabled:
            tracker_alert = self.talking_tracker.process_audio_visual_state(
                is_speech, current_time=current_time
            )
            if tracker_alert:
                # Trigger Prolonged Discussion alert (5 qualifying episodes rule)
                self._emit_alert(
                    activity="prolonged_discussion",
                    confidence=round(confidence * 100.0, 1) if confidence > 0 else 90.0,
                    current_time=current_time,
                    details={
                        "rule": f"{self.config.talking_event_threshold} qualifying speech episodes within {self.config.talking_window_seconds}s",
                        "event": tracker_alert,
                    },
                )

        return {
            "is_speech": is_speech,
            "confidence": confidence,
            "sound_level_db": self.current_sound_level_db,
            "smoothed_db": self.smoothed_sound_level_db,
            "episodes": len(self.talking_tracker.event_history),
        }

    def _emit_alert(
        self,
        activity: str,
        confidence: float,
        current_time: float,
        details: Optional[dict] = None,
    ) -> bool:
        """Emits an alert via the existing AlertEngine for the active session."""
        session_id = self.session_id
        if not session_id and self.session_manager:
            session_id = getattr(self.session_manager, "session_id", None)

        if not session_id or session_id in ("offline-fallback-session", "test-mock-session", None):
            return False

        if not self.alert_engine:
            return False

        payload = {
            "student_id": None,  # Room-wide alert
            "activity": activity,
            "confidence": float(confidence),
            "details": details or {},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        try:
            return bool(
                self.alert_engine.process_activity_event(
                    session_id=session_id,
                    event_payload=payload,
                    current_time=current_time,
                )
            )
        except Exception as e:
            print(f"[AudioMonitor] Alert emission error: {e}")
            return False

    # -------------------------------------------------------------------------
    # Lifecycle & Background Microphone Capture
    # -------------------------------------------------------------------------

    def start_monitoring(self, session_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Starts live microphone capture and audio processing in a background worker.
        Idempotent: safe to call multiple times.
        Returns (success: bool, error_message: str | None).
        """
        with self._lifecycle_lock:
            # If already running for this session, return immediately
            if self._running and self.audio_status == "active" and self.session_id == session_id:
                return True, None

            # If switching sessions or restarting, clean up previous worker
            if self._thread and self._thread.is_alive():
                self._running = False
                self._thread.join(timeout=2.0)

            # Update session context and reset episode counters for fresh session
            self.session_id = session_id
            self.talking_tracker = TalkingTracker(self.config)
            self._sustained_noise_start = None
            self.current_sound_level_db = 0.0
            self.smoothed_sound_level_db = 0.0

            if not getattr(self.config, "audio_monitoring_enabled", True) and not getattr(
                self.config, "talking_detection_enabled", True
            ):
                self.audio_status = "disabled"
                self.audio_error = None
                return True, None

            self._running = True
            self.audio_status = "starting"
            self.audio_error = None

            # Empty queue
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except Exception:
                    break

            self._thread = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name="classroom-audio-monitor",
            )
            self._thread.start()

        # Wait briefly up to 1.5s for audio device to acquire
        deadline = time.time() + 1.5
        while time.time() < deadline:
            if self.audio_status in ("active", "unavailable", "error"):
                break
            time.sleep(0.1)

        if self.audio_status == "error":
            return False, self.audio_error
        # Note: unavailable (no mic hardware) is non-fatal for session start
        return True, None

    def stop_monitoring(self) -> bool:
        """
        Stops live microphone capture and releases audio hardware cleanly.
        Idempotent: safe to call multiple times.
        """
        with self._lifecycle_lock:
            self._running = False
            thread = self._thread
            stream = self._stream

        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            self._stream = None

        if thread and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lifecycle_lock:
            self._thread = None
            self.audio_status = "stopped"
            self.audio_error = None
            self._is_speech_active = False
            self._confidence = 0.0
            self.current_sound_level_db = 0.0
            self.smoothed_sound_level_db = 0.0
            self._sustained_noise_start = None
            if self.audio_hook is not None and hasattr(self.audio_hook, "set_speech_state"):
                self.audio_hook.set_speech_state(False, 0.0)

        return True

    def _audio_callback(self, indata, frames, time_info, status):
        """Sounddevice stream input callback; enqueues raw audio chunks."""
        if status:
            pass  # Overflow/underflow: non-fatal in classroom monitoring
        if self._running:
            try:
                # Copy audio slice to prevent buffer corruption
                self._audio_queue.put_nowait(indata.copy())
            except queue.Full:
                pass

    def _worker_loop(self):
        """Background thread worker managing stream lifecycle and processing."""
        if not SOUNDDEVICE_AVAILABLE or sd is None:
            self.audio_status = "unavailable"
            self.audio_error = "sounddevice library unavailable in environment"
            return

        try:
            # Check for input audio devices
            devices = sd.query_devices()
            input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
            if not input_devices:
                self.audio_status = "unavailable"
                self.audio_error = "No microphone input device found"
                return

            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.chunk_samples,
                callback=self._audio_callback,
            )
            self._stream = stream
            stream.start()
            self.audio_status = "active"
            self.audio_error = None
        except Exception as e:
            self.audio_status = "unavailable"
            self.audio_error = f"Microphone access error: {e}"
            self._running = False
            return

        try:
            while self._running:
                try:
                    chunk = self._audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if not self._running:
                    break

                self.process_audio_chunk(chunk)
        except Exception as e:
            if self._running:
                self.audio_status = "error"
                self.audio_error = f"Audio processing error: {e}"
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                self._stream = None
            if self.audio_status == "active":
                self.audio_status = "stopped"

    # -------------------------------------------------------------------------
    # Status & Simulation / Backward-Compatibility API
    # -------------------------------------------------------------------------

    def get_status(self) -> dict:
        """Returns comprehensive audio monitoring status for dashboard & API."""
        return {
            "audio_status": self.audio_status,
            "audio_error": self.audio_error,
            "is_monitoring": self.audio_status == "active",
            "current_sound_level_db": round(float(self.current_sound_level_db), 1),
            "smoothed_sound_level_db": round(float(self.smoothed_sound_level_db), 1),
            "speech_detected": bool(self._is_speech_active),
            "confidence": round(float(self._confidence), 2),
            "episodes_in_window": len(self.talking_tracker.event_history) if self.talking_tracker else 0,
            "session_id": self.session_id,
        }

    def set_simulation_state(
        self,
        is_speech: bool,
        confidence: float = 0.0,
        sound_level_db: float = 50.0,
    ):
        """Allows test suites and simulation without live hardware input."""
        self._is_speech_active = is_speech
        self._confidence = confidence
        self.current_sound_level_db = sound_level_db
        self.smoothed_sound_level_db = sound_level_db
        if self.audio_hook is not None and hasattr(self.audio_hook, "set_speech_state"):
            self.audio_hook.set_speech_state(is_speech, confidence)

    def detect_speech_activity(self) -> Tuple[bool, float]:
        """Backward-compatible interface for earlier simulated tests."""
        return self._is_speech_active, self._confidence
