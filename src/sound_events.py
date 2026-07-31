"""Audio stream analysis for siren, horn, and bark detection."""

import time
import threading
import queue
import numpy as np

from .config import load_config


class SoundDetector:
    """Analyzes audio chunks for siren/horn/bark signatures using FFT analysis.

    All local — no cloud dependencies. Uses spectral energy distribution
    and peak frequency tracking to identify sound events.
    
    Supported audio sources:
    - host_audio: Direct microphone input via sounddevice
    - video_stream: Extract audio from RTSP video stream
    - ip_stream: Receive audio from IP audio stream (HTTP/RTP)
    """

    SOURCE_HOST_AUDIO = "host_audio"
    SOURCE_VIDEO_STREAM = "video_stream"
    SOURCE_IP_STREAM = "ip_stream"

    def __init__(self, db=None):
        cfg = load_config()
        self.enabled = cfg["sound_events"]["enabled"]
        self.sample_rate = cfg["sound_events"]["sample_rate"]
        self.chunk_duration = cfg["sound_events"]["chunk_duration"]
        self.siren_threshold = cfg["sound_events"]["siren_threshold"]
        self.horn_threshold = cfg["sound_events"]["horn_threshold"]
        self.bark_threshold = cfg["sound_events"]["bark_threshold"]
        self.input_device = cfg["sound_events"]["input_device"]
        
        # Audio source configuration
        self.source = cfg["sound_events"].get("source", self.SOURCE_HOST_AUDIO)
        self.rtsp_url = cfg["sound_events"].get("rtsp_url", "")
        self.ip_audio_url = cfg["sound_events"].get("ip_audio_url", "")
        
        self.db = db

        self._running = False
        self._thread = None
        self._audio_queue = queue.Queue(maxsize=10)
        self._last_event_time = 0
        self._event_cooldown = 2.0  # seconds between same-type events
        self._events = []
        self._ffmpeg_process = None

        if self.enabled:
            print(f"[sound] Sound detection enabled "
                  f"(SR={self.sample_rate}Hz, chunk={self.chunk_duration}s, source={self.source})")
        else:
            print("[sound] Sound detection disabled")

    def _analyze_chunk(self, audio_data):
        """Analyze audio chunk for sound events. Returns (event_type, confidence, peak_freq) or None."""
        if len(audio_data) == 0:
            return None

        # Compute FFT
        fft = np.fft.rfft(audio_data)
        freqs = np.fft.rfftfreq(len(audio_data), 1.0 / self.sample_rate)
        magnitude = np.abs(fft)

        # Total energy
        total_energy = np.sum(magnitude ** 2)

        # Find dominant frequency
        peak_idx = np.argmax(magnitude)
        peak_freq = freqs[peak_idx] if peak_idx < len(freqs) else 0

        # Energy ratios in frequency bands
        # Siren: sweeping 500-2000Hz, modulated
        siren_band = (freqs >= 500) & (freqs <= 2000)
        siren_energy = np.sum(magnitude[siren_band] ** 2) if np.any(siren_band) else 0

        # Horn: concentrated 200-800Hz
        horn_band = (freqs >= 200) & (freqs <= 800)
        horn_energy = np.sum(magnitude[horn_band] ** 2) if np.any(horn_band) else 0

        # Bark: 400-1200Hz, short duration bursts
        bark_band = (freqs >= 400) & (freqs <= 1200)
        bark_energy = np.sum(magnitude[bark_band] ** 2) if np.any(bark_band) else 0

        if total_energy == 0:
            return None

        siren_ratio = siren_energy / total_energy if total_energy > 0 else 0
        horn_ratio = horn_energy / total_energy if total_energy > 0 else 0
        bark_ratio = bark_energy / total_energy if total_energy > 0 else 0

        # Detect events
        now = time.time()
        if siren_ratio > self.siren_threshold and (now - self._last_event_time) > self._event_cooldown:
            self._last_event_time = now
            return ("siren", float(siren_ratio), float(peak_freq))

        if horn_ratio > self.horn_threshold and (now - self._last_event_time) > self._event_cooldown:
            self._last_event_time = now
            return ("horn", float(horn_ratio), float(peak_freq))

        if bark_ratio > self.bark_threshold and (now - self._last_event_time) > self._event_cooldown:
            self._last_event_time = now
            return ("bark", float(bark_ratio), float(peak_freq))

        return None

    def _audio_capture_host(self):
        """Capture audio from host microphone via sounddevice."""
        try:
            import sounddevice as sd
            
            chunk_samples = int(self.sample_rate * self.chunk_duration)

            def audio_callback(indata, frames, time_info, status):
                if status:
                    print(f"[sound] Audio callback status: {status}")
                if self._audio_queue.full():
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        pass
                # Convert to mono if stereo
                audio = indata[:, 0] if indata.ndim > 1 else indata
                self._audio_queue.put(audio.copy())

            print(f"[sound] Starting host audio capture (device={self.input_device})...")
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                device=self.input_device,
                callback=audio_callback,
                blocksize=chunk_samples,
            ):
                while self._running:
                    time.sleep(0.1)

        except ImportError:
            print("[sound] sounddevice not available — host audio capture disabled")
        except Exception as e:
            print(f"[sound] Host audio capture error: {e}")

    def _audio_capture_video_stream(self):
        """Capture audio from RTSP video stream using ffmpeg."""
        try:
            import subprocess
            import numpy as np
            
            if not self.rtsp_url:
                print("[sound] No RTSP URL configured for video stream audio")
                return

            # Use ffmpeg to extract audio from RTSP stream
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", self.rtsp_url,
                "-f", "s16le",
                "-acodec", "pcm_s16le",
                "-ac", "1",
                "-ar", str(self.sample_rate),
                "-vn",
                "pipe:1"
            ]

            print(f"[sound] Starting video stream audio capture from {self.rtsp_url}...")
            
            self._ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            chunk_samples = int(self.sample_rate * self.chunk_duration)
            
            while self._running and self._ffmpeg_process.poll() is None:
                try:
                    raw_audio = self._ffmpeg_process.stdout.read(chunk_samples * 2)
                    if len(raw_audio) < chunk_samples * 2:
                        continue
                    
                    # Convert bytes to numpy array
                    audio = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
                    audio = audio / 32768.0  # Normalize to -1 to 1
                    
                    if self._audio_queue.full():
                        try:
                            self._audio_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self._audio_queue.put(audio.copy())
                    
                    time.sleep(0.01)
                except Exception as e:
                    print(f"[sound] Video stream audio read error: {e}")
                    break

            if self._ffmpeg_process:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process = None

        except ImportError:
            print("[sound] subprocess not available")
        except FileNotFoundError:
            print("[sound] ffmpeg not found — install ffmpeg for video stream audio capture")
        except Exception as e:
            print(f"[sound] Video stream audio capture error: {e}")

    def _audio_capture_ip_stream(self):
        """Capture audio from IP audio stream."""
        try:
            import urllib.request
            import numpy as np

            if not self.ip_audio_url:
                print("[sound] No IP audio URL configured")
                return

            print(f"[sound] Starting IP audio stream capture from {self.ip_audio_url}...")
            chunk_samples = int(self.sample_rate * self.chunk_duration)

            while self._running:
                try:
                    with urllib.request.urlopen(self.ip_audio_url, timeout=5) as response:
                        raw_audio = response.read(chunk_samples * 2)
                        if len(raw_audio) < chunk_samples * 2:
                            continue
                        
                        audio = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
                        audio = audio / 32768.0
                        
                        if self._audio_queue.full():
                            try:
                                self._audio_queue.get_nowait()
                            except queue.Empty:
                                pass
                        self._audio_queue.put(audio.copy())
                except Exception as e:
                    print(f"[sound] IP audio stream read error: {e}")
                    time.sleep(1)

        except Exception as e:
            print(f"[sound] IP audio stream capture error: {e}")

    def _audio_processing_thread(self):
        """Background thread that processes audio chunks."""
        while self._running:
            try:
                audio_data = self._audio_queue.get(timeout=0.5)
                result = self._analyze_chunk(audio_data)
                if result:
                    event_type, confidence, peak_freq = result
                    print(f"[sound] DETECTED: {event_type} (confidence={confidence:.2f}, "
                          f"peak_freq={peak_freq:.0f}Hz)")
                    if self.db:
                        self.db.insert_sound_event(event_type, confidence, peak_freq=peak_freq)
                    self._events.append({
                        "timestamp": time.time(),
                        "event_type": event_type,
                        "confidence": confidence,
                        "peak_freq": peak_freq,
                    })
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[sound] Processing error: {e}")

    def start(self):
        """Start the sound detector with configured audio source."""
        if not self.enabled:
            print("[sound] Sound detection disabled, not starting")
            return
        
        self._running = True
        
        # Start audio capture thread based on source
        if self.source == self.SOURCE_HOST_AUDIO:
            capture_thread = threading.Thread(target=self._audio_capture_host, daemon=True)
        elif self.source == self.SOURCE_VIDEO_STREAM:
            capture_thread = threading.Thread(target=self._audio_capture_video_stream, daemon=True)
        elif self.source == self.SOURCE_IP_STREAM:
            capture_thread = threading.Thread(target=self._audio_capture_ip_stream, daemon=True)
        else:
            print(f"[sound] Unknown audio source: {self.source}, defaulting to host_audio")
            capture_thread = threading.Thread(target=self._audio_capture_host, daemon=True)
        
        # Start processing thread
        process_thread = threading.Thread(target=self._audio_processing_thread, daemon=True)
        
        capture_thread.start()
        process_thread.start()
        print("[sound] Sound detector started")

    def stop(self):
        """Stop the sound detector and release resources."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._ffmpeg_process:
            self._ffmpeg_process.terminate()
            self._ffmpeg_process = None
        print("[sound] Sound detector stopped")

    def process_audio_chunk(self, audio_data):
        """Process an audio chunk and return event if detected."""
        result = self._analyze_chunk(audio_data)
        if result:
            event_type, confidence, peak_freq = result
            print(f"[sound] DETECTED: {event_type} (confidence={confidence:.2f}, "
                  f"peak_freq={peak_freq:.0f}Hz)")
            if self.db:
                self.db.insert_sound_event(event_type, confidence, peak_freq=peak_freq)
            self._events.append({
                "timestamp": time.time(),
                "event_type": event_type,
                "confidence": confidence,
                "peak_freq": peak_freq,
            })
            return result
        return None

    def get_recent_events(self, limit=10):
        return self._events[-limit:]

    @property
    def stats(self):
        return {
            "enabled": self.enabled,
            "running": self._running,
            "events_this_session": len(self._events),
            "sample_rate": self.sample_rate,
            "source": self.source,
        }