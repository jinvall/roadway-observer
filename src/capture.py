"""RTSP stream capture with auto-reconnect and frame buffer."""

import time
import cv2
import threading
from queue import Queue, Empty

from .config import load_config


class RTSPSource:
    """Reads frames from an RTSP stream with automatic reconnection."""

    def __init__(self, url=None, reconnect_delay=None, max_reconnects=None,
                 frame_timeout=None, buffer_size=2):
        cfg = load_config()
        self.url = url or cfg["rtsp"]["url"]
        self.reconnect_delay = reconnect_delay or cfg["rtsp"]["reconnect_delay"]
        self.max_reconnects = max_reconnects or cfg["rtsp"]["max_reconnects"]
        self.frame_timeout = frame_timeout or cfg["rtsp"]["frame_timeout"]
        self.buffer_size = buffer_size

        self._cap = None
        self._frame_queue = Queue(maxsize=buffer_size)
        self._running = False
        self._thread = None
        self._reconnect_count = 0
        self._last_frame_time = 0
        self._frame_count = 0
        self._fps = 0.0
        self._width = 0
        self._height = 0
        self._lock = threading.Lock()

        print(f"[capture] RTSP source: {self.url}")

    def _open_stream(self):
        """Open RTSP stream with retry."""
        print(f"[capture] Opening stream...")
        self._cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not self._cap.isOpened():
            raise RuntimeError(f"Failed to open RTSP stream: {self.url}")

        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._fps = self._cap.get(cv2.CAP_PROP_FPS)
        print(f"[capture] Stream opened: {self._width}x{self._height} @ {self._fps:.1f} FPS")

    def _reader_thread(self):
        """Background thread that reads frames continuously."""
        while self._running:
            try:
                if self._cap is None or not self._cap.isOpened():
                    self._reconnect()
                    continue

                ret, frame = self._cap.read()
                if not ret or frame is None:
                    print(f"[capture] Frame read failed, reconnecting...")
                    self._cap.release()
                    self._cap = None
                    continue

                self._frame_count += 1
                self._last_frame_time = time.time()

                # Non-blocking queue put (drop oldest if full)
                if self._frame_queue.full():
                    try:
                        self._frame_queue.get_nowait()
                    except Empty:
                        pass
                self._frame_queue.put(frame)

            except Exception as e:
                print(f"[capture] Reader error: {e}")
                time.sleep(self.reconnect_delay)

        # Cleanup
        if self._cap:
            self._cap.release()
            self._cap = None
        print("[capture] Reader thread stopped")

    def _reconnect(self):
        """Attempt reconnection up to max_reconnects times."""
        if self.max_reconnects > 0 and self._reconnect_count >= self.max_reconnects:
            raise RuntimeError(f"Max reconnects ({self.max_reconnects}) reached")

        self._reconnect_count += 1
        print(f"[capture] Reconnect attempt {self._reconnect_count}...")
        time.sleep(self.reconnect_delay)

        try:
            self._open_stream()
            self._reconnect_count = 0
        except Exception as e:
            print(f"[capture] Reconnect failed: {e}")

    def start(self):
        """Start the reader thread."""
        if self._running:
            return
        self._running = True
        self._open_stream()
        self._thread = threading.Thread(target=self._reader_thread, daemon=True)
        self._thread.start()
        print(f"[capture] Reader thread started")

    def stop(self):
        """Stop the reader thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._cap:
            self._cap.release()
            self._cap = None
        print(f"[capture] Stopped")

    def get_frame(self, timeout=5.0):
        """Get latest frame from queue. Blocks until available."""
        try:
            return self._frame_queue.get(timeout=timeout)
        except Empty:
            print(f"[capture] Frame timeout ({timeout}s)")
            return None

    def get_frame_nowait(self):
        """Get latest frame or None."""
        try:
            return self._frame_queue.get_nowait()
        except Empty:
            return None

    @property
    def is_alive(self):
        """Check if stream is producing frames."""
        if not self._running:
            return False
        if time.time() - self._last_frame_time > self.frame_timeout:
            return False
        return True

    @property
    def stats(self):
        return {
            "frame_count": self._frame_count,
            "reconnects": self._reconnect_count,
            "alive": self.is_alive,
            "width": self._width,
            "height": self._height,
            "fps": self._fps,
        }
