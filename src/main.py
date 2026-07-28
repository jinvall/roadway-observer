"""Master orchestrator — async pipeline for max FPS."""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from src.capture import RTSPSource
from src.config import PROJECT_ROOT, load_config
from src.dashboard import Dashboard
from src.database import RoadwayDB
from src.detector import ObjectDetector
from src.sound_events import SoundDetector
from src.tracker import ObjectTracker
from src.utils import FPSCounter, setup_logging
from src.wifi_sniffer import WiFiSniffer


class RoadwayObserver:
    def __init__(self):
        self.cfg = load_config()
        self.logger = setup_logging("roadway")
        print("=" * 60)
        print("  roadway-observer v1.1.0 (async pipeline)")
        print("=" * 60)
        print(f"  RTSP: {self.cfg['rtsp']['url']}")
        print(f"  Model: {self.cfg['model']['active']}")
        print(f"  Classes: {self.cfg['detection']['enabled_classes']}")
        print(f"  Dashboard: http://{self.cfg['dashboard']['host']}:{self.cfg['dashboard']['port']}")
        print("=" * 60)

        self.db = RoadwayDB()
        self.capture = RTSPSource()
        self.detector = ObjectDetector()
        self.tracker = ObjectTracker()
        self.sound = SoundDetector(db=self.db)
        self.dashboard = Dashboard(db=self.db)
        self.wifi = WiFiSniffer(dashboard=self.dashboard)

        self._running = False
        self._fps_counter = FPSCounter(window=30)
        self._frame_count = 0
        self._last_purge = time.time()
        self._last_inference_time = 0

        # Shared state between threads
        self._latest_frame = None
        self._latest_annotated = None
        self._frame_lock = threading.Lock()
        self._latest_results = []
        self._inference_fps = FPSCounter(window=30)

        self.dashboard.app.template_folder = str(PROJECT_ROOT / "templates")
        self.dashboard.app.static_folder = str(PROJECT_ROOT / "static")

    def _inference_loop(self):
        """Background thread: runs inference continuously on latest frame."""
        while self._running:
            with self._frame_lock:
                frame = self._latest_frame
            if frame is None:
                time.sleep(0.01)
                continue

            # Detect
            detections = self.detector.detect(frame)

            # Track
            tracked = self.tracker.update(detections)

            # Build results
            results = []
            for obj in tracked:
                results.append({
                    "track_id": obj.track_id,
                    "class_name": obj.class_name,
                    "category": obj.category,
                    "confidence": obj.confidence,
                    "bbox": obj.bbox,
                    "direction": obj.direction,
                    "speed": obj.speed,
                })

            # Store results for display thread
            self._latest_results = results
            self._inference_fps.tick()
            self._last_inference_time = self.detector.avg_inference_time

            # Batch insert to DB
            if results:
                self.db.insert_batch_detections(results)
                self.dashboard.add_detections(results)

            # Annotate frame
            if results:
                self._latest_annotated = self._draw_annotations(frame, results)
            else:
                self._latest_annotated = frame.copy()

    def _draw_annotations(self, frame, results):
        """Draw bounding boxes and labels on frame."""
        annotated = frame.copy()
        for d in results:
            x1, y1, x2, y2 = d.get("bbox", (0, 0, 0, 0))
            label = f"{d.get('class_name', '?')} {d.get('confidence', 0):.2f}"
            track_id = d.get("track_id")
            if track_id is not None:
                label = f"#{track_id} {label}"

            cat = d.get("category", "other")
            color_map = {
                "vehicle": (0, 255, 0),
                "pedestrian": (255, 0, 0),
                "animal": (0, 0, 255),
                "cyclist": (255, 255, 0),
            }
            color = color_map.get(cat, (255, 255, 255))
            cv2.putText(annotated, label, (x1, max(y1 - 5, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        # Overlay stats
        info_y = 20
        active_tracks = len([r for r in self._latest_results if r.get("track_id") is not None])
        for key, val in [
            ("FPS", f"{self._fps_counter.fps:.1f}"),
            ("Inf", f"{self._inference_fps.fps:.1f}"),
            ("Tracks", str(active_tracks)),
        ]:
            text = f"{key}: {val}"
            cv2.putText(annotated, text, (10, info_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            info_y += 20

        return annotated

    def _maintenance_loop(self):
        now = time.time()
        if now - self._last_purge > self.cfg["database"]["vacuum_interval"]:
            self.db.purge_old_events()
            self.db.vacuum()
            self._last_purge = now

    def run(self):
        self._running = True
        self.capture.start()
        self.sound.start()
        self.wifi.start()

        # Start inference thread
        inference_thread = threading.Thread(
            target=self._inference_loop, daemon=True, name="inference")
        inference_thread.start()

        # Start dashboard
        dashboard_thread = threading.Thread(
            target=self.dashboard.run, daemon=True, name="dashboard")
        dashboard_thread.start()

        print("[main] All modules started. Running...")

        try:
            while self._running:
                # Get latest frame (non-blocking)
                frame = self.capture.get_frame_nowait()
                if frame is None:
                    time.sleep(0.001)
                    continue

                self._frame_count += 1
                self._fps_counter.tick()

                # Store latest frame for inference thread
                with self._frame_lock:
                    self._latest_frame = frame

                # Show latest annotated frame in dashboard
                if self._latest_annotated is not None:
                    self.dashboard.update_frame(self._latest_annotated)
                else:
                    self.dashboard.update_frame(frame)

                # Update stats
                active_tracks = len(
                    [r for r in self._latest_results if r.get("track_id") is not None]
                )
                self.dashboard.update_stats({
                    "fps": self._fps_counter.fps,
                    "inference_ms": self._last_inference_time * 1000,
                    "active_tracks": active_tracks,
                    "model_name": self.detector.model_name,
                    "stream_alive": self.capture.is_alive,
                    "frame_width": self.capture.stats["width"],
                    "frame_height": self.capture.stats["height"],
                })

                self._maintenance_loop()

        except KeyboardInterrupt:
            print("[main] Keyboard interrupt")
        except Exception as e:
            print(f"[main] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop()

    def stop(self):
        print("[main] Shutting down...")
        self._running = False
        self.capture.stop()
        self.sound.stop()
        self.wifi.stop()
        print("[main] Shutdown complete")


def main():
    observer = RoadwayObserver()
    observer.run()


if __name__ == "__main__":
    main()
