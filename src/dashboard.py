"""Flask web dashboard with MJPEG stream, real-time stats, and historical views."""

import threading
import time

import cv2
from flask import Flask, Response, jsonify, render_template, request

from .config import load_config


class Dashboard:
    """Flask-based web dashboard for roadway observer."""

    def __init__(self, db=None):
        cfg = load_config()
        self.host = cfg["dashboard"]["host"]
        self.port = cfg["dashboard"]["port"]
        self.update_interval = cfg["dashboard"]["update_interval"]
        self.mjpeg_quality = cfg["dashboard"]["mjpeg_quality"]
        self.mjpeg_scale = cfg["dashboard"].get("mjpeg_scale", 640)
        self.debug = cfg["dashboard"]["debug"]
        self.db = db

        self.app = Flask(
            __name__,
            template_folder=str(cfg.get("_template_dir", "../templates")),
            static_folder=str(cfg.get("_static_dir", "../static")),
        )
        self._setup_routes()

        # Shared state updated by main loop
        self._frame = None
        self._frame_lock = threading.Lock()
        self._stats = {
            "fps": 0.0,
            "inference_ms": 0.0,
            "active_tracks": 0,
            "total_detections": 0,
            "vehicles_today": 0,
            "pedestrians_today": 0,
            "animals_today": 0,
            "cyclists_today": 0,
            "sound_events_today": 0,
            "uptime_seconds": 0,
            "stream_alive": False,
            "model_name": "unknown",
            "frame_width": 0,
            "frame_height": 0,
        }
        self._start_time = time.time()
        self._detections_buffer = []
        self._sound_events_buffer = []
        self._wifi_events_buffer = []
        self._buffer_lock = threading.Lock()

        print(f"[dashboard] UI at http://{self.host}:{self.port}")

    def _setup_routes(self):
        app = self.app

        @app.route("/")
        def index():
            return render_template("index.html")

        @app.route("/api/stats")
        def api_stats():
            self._refresh_stats_from_db()
            return jsonify(self._stats)

        @app.route("/api/detections")
        def api_detections():
            limit = request.args.get("limit", 50, type=int)
            with self._buffer_lock:
                dets = self._detections_buffer[-limit:]
            return jsonify(dets)

        @app.route("/api/sound_events")
        def api_sound_events():
            limit = request.args.get("limit", 20, type=int)
            with self._buffer_lock:
                events = self._sound_events_buffer[-limit:]
            return jsonify(events)

        @app.route("/api/wifi_events")
        def api_wifi_events():
            limit = request.args.get("limit", 50, type=int)
            with self._buffer_lock:
                events = (
                    self._wifi_events_buffer[-limit:]
                    if hasattr(self, "_wifi_events_buffer")
                    else []
                )
            return jsonify(events)

        @app.route("/video_feed")
        def video_feed():
            return Response(
                self._generate_mjpeg(),
                mimetype="multipart/x-mixed-replace; boundary=frame",
            )

        @app.route("/api/capture", methods=["POST"])
        def api_capture():
            """Capture current frame with WiFi overlay."""
            import base64
            import os
            from datetime import datetime
            
            with self._frame_lock:
                if self._frame is None:
                    return jsonify({"status": "error", "message": "No frame available"}), 404
                frame = self._frame.copy()

            wifi_info = self._get_wifi_info()
            if wifi_info:
                y_offset = 20
                for info in wifi_info[:3]:
                    label = f"WiFi: {info}"
                    cv2.putText(frame, label, (10, y_offset),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                    y_offset += 20

            ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.mjpeg_quality])
            if not ret:
                return jsonify({"status": "error", "message": "Failed to encode image"}), 500

            saved_path = None
            try:
                cfg = load_config()
                photos_cfg = cfg.get("photos", {})
                if photos_cfg.get("enabled", True):
                    photos_path = photos_cfg.get("path", "data/photos")
                    max_files = photos_cfg.get("max_files", 100)
                    
                    os.makedirs(photos_path, exist_ok=True)
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    saved_path = os.path.join(photos_path, f"capture_{timestamp}.jpg")
                    with open(saved_path, "wb") as f:
                        f.write(jpeg.tobytes())
                    
                    existing = sorted([f for f in os.listdir(photos_path) if f.startswith("capture_")])
                    if len(existing) > max_files:
                        for old_file in existing[:-max_files]:
                            os.remove(os.path.join(photos_path, old_file))
            except Exception as e:
                print(f"[capture] Save error: {e}")

            result = {
                "status": "ok",
                "image": base64.b64encode(jpeg.tobytes()).decode("utf-8"),
                "saved_path": saved_path,
            }
            return jsonify(result)

        @app.route("/api/config")
        def api_config_get():
            """Return current full config."""
            from .config import load_config
            cfg = load_config()
            safe = {
                "rtsp": {"url": cfg["rtsp"]["url"]},
                "model": {
                    "active": cfg["model"]["active"],
                    "available": cfg["model"]["available"],
                    "confidence_threshold": cfg["model"]["confidence_threshold"],
                    "max_detections": cfg["model"]["max_detections"],
                    "backend": cfg["model"].get("backend", "local"),
                    "cloud_provider": cfg["model"].get("cloud_provider", "huggingface"),
                    "cloud_model_id": cfg["model"].get("cloud_model_id", "microsoft/dit-base-beta"),
                },
                "detection": {"enabled_classes": cfg["detection"]["enabled_classes"],
                              "frame_skip": cfg["detection"]["frame_skip"]},
                "tracking": {"enabled": cfg["tracking"]["enabled"],
                             "iou_threshold": cfg["tracking"]["iou_threshold"],
                             "max_disappeared": cfg["tracking"]["max_disappeared"]},
                "sound_events": {"enabled": cfg["sound_events"]["enabled"],
                                 "siren_threshold": cfg["sound_events"]["siren_threshold"],
                                 "horn_threshold": cfg["sound_events"]["horn_threshold"],
                                 "bark_threshold": cfg["sound_events"]["bark_threshold"]},
                "dashboard": {"host": cfg["dashboard"]["host"],
                              "port": cfg["dashboard"]["port"],
                              "mjpeg_scale": cfg["dashboard"]["mjpeg_scale"],
                              "mjpeg_quality": cfg["dashboard"]["mjpeg_quality"]},
                "wifi_sniffer": {"enabled": cfg["wifi_sniffer"]["enabled"],
                                 "device": cfg["wifi_sniffer"]["device"],
                                 "history_window": cfg["wifi_sniffer"]["history_window"]},
            }
            return jsonify(safe)

        @app.route("/api/config", methods=["POST"])
        def api_config_set():
            """Update config values. Returns dict of applied / requires_restart."""
            from .config import load_config, save_config
            data = request.get_json(force=True)
            cfg = load_config()
            requires_restart = []
            applied = []

            # Walk the nested keys
            for key, value in data.items():
                if key in cfg:
                    if isinstance(value, dict):
                        for subkey, subval in value.items():
                            if subkey in cfg[key]:
                                cfg[key][subkey] = subval
                                applied.append(f"{key}.{subkey}")
                            else:
                                # Check if it's nested one more level
                                if isinstance(cfg[key], dict):
                                    for sk in cfg[key]:
                                        if subkey in cfg[key][sk]:
                                            cfg[key][sk][subkey] = subval
                                            applied.append(f"{key}.{sk}.{subkey}")
                                            break
                    else:
                        cfg[key] = value
                        applied.append(key)

            save_config(cfg)
            restart_keys = [
                "rtsp.url", "model.active", "model.available", "model.backend",
                "wifi_sniffer.enabled", "wifi_sniffer.device",
            ]
            for k in restart_keys:
                parts = k.split(".")
                val = data
                for p in parts:
                    if isinstance(val, dict) and p in val:
                        val = val[p]
                    else:
                        val = None
                        break
                if val is not None:
                    requires_restart.append(k)

            return jsonify({
                "status": "ok",
                "applied": applied,
                "requires_restart": requires_restart,
                "message": "Restart required for: " + ", ".join(requires_restart)
                if requires_restart else "All changes applied live",
            })

        @app.route("/api/config/reload")
        def api_config_reload():
            """Reload config from disk."""
            from .config import reload_config
            reload_config()
            return jsonify({"status": "ok", "message": "Config reloaded from disk"})

        @app.route("/api/restart", methods=["POST"])
        def api_restart():
            """Restart the application."""
            import os
            import signal
            pid = os.getpid()
            os.kill(pid, signal.SIGTERM)
            return jsonify({"status": "ok", "message": "Restart initiated"})

        @app.route("/settings")
        def settings_page():
            return render_template("settings.html")

        @app.route("/api/health")
        def api_health():
            self._refresh_stats_from_db()
            return jsonify({
                "status": "ok" if self._stats["stream_alive"] else "degraded",
                "uptime": round(time.time() - self._start_time),
                **self._stats,
            })

    def _generate_mjpeg(self):
        """MJPEG generator - never sleep while holding lock."""
        while True:
            # Snapshot the current frame under the lock (fast)
            with self._frame_lock:
                current = self._frame.copy() if self._frame is not None else None

            if current is None:
                time.sleep(0.1)
                continue

            # Downscale and encode OUTSIDE the lock
            h, w = current.shape[:2]
            if w > self.mjpeg_scale:
                scale = self.mjpeg_scale / w
                new_w, new_h = self.mjpeg_scale, int(h * scale)
                display = cv2.resize(current, (new_w, new_h))
            else:
                display = current

            ret, jpeg = cv2.imencode(
                ".jpg", display,
                [cv2.IMWRITE_JPEG_QUALITY, self.mjpeg_quality],
            )
            if not ret:
                time.sleep(0.1)
                continue

            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                   + jpeg.tobytes() + b"\r\n")
            time.sleep(0.01)

    def _get_wifi_info(self):
        """Get WiFi info from sniffer buffer."""
        if not self._wifi_events_buffer:
            return []

        info = []
        seen_macs = set()
        for event in self._wifi_events_buffer[-50:]:
            mac = event.get("mac", "")
            if mac and mac not in seen_macs:
                seen_macs.add(mac)
                mac_type = "static" if event.get("is_static") else "dynamic"
                info.append(f"{mac[:8]}... ({mac_type})")
        return info
    def _refresh_stats_from_db(self):
        """Pull fresh stats from database."""
        if self.db:
            try:
                today = self.db.get_todays_counts()
                self._stats["vehicles_today"] = today.get("vehicle", 0)
                self._stats["pedestrians_today"] = today.get("pedestrian", 0)
                self._stats["animals_today"] = today.get("animal", 0)
                self._stats["cyclists_today"] = today.get("cyclist", 0)
                total = sum(today.values())
                self._stats["total_detections"] = total

                today_start = int(time.time() - (time.time() % 86400))
                self._stats["sound_events_today"] = self.db.get_sound_event_count(since=today_start)
            except Exception as e:
                print(f"[dashboard] DB refresh error: {e}")

    def update_frame(self, frame, detections=None):
        """Update the current frame (with optional drawn annotations)."""
        if detections:
            annotated = frame.copy()
            for d in detections:
                x1, y1, x2, y2 = d.get("bbox", (0, 0, 0, 0))
                label = f"{d.get('class_name', '?')} {d.get('confidence', 0):.2f}"
                track_id = d.get("track_id")
                if track_id is not None:
                    label = f"#{track_id} {label}"

                # Color by category
                cat = d.get("category", "other")
                color_map = {
                    "vehicle": (0, 255, 0),     # green
                    "pedestrian": (255, 0, 0),   # blue
                    "animal": (0, 0, 255),       # red
                    "cyclist": (255, 255, 0),    # cyan
                }
                color = color_map.get(cat, (255, 255, 255))

                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated, label, (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # Draw overlay info
            info_y = 20
            for key, val in [
                ("FPS", f"{self._stats['fps']:.1f}"),
                ("Inference", f"{self._stats['inference_ms']:.0f}ms"),
                ("Tracks", str(self._stats['active_tracks'])),
                ("Vehicles", str(self._stats['vehicles_today'])),
                ("Pedestrians", str(self._stats['pedestrians_today'])),
            ]:
                text = f"{key}: {val}"
                cv2.putText(annotated, text, (10, info_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                info_y += 20

            with self._frame_lock:
                self._frame = annotated
        else:
            with self._frame_lock:
                self._frame = frame

    def update_stats(self, stats_dict):
        """Update dashboard stats from main loop."""
        self._stats.update(stats_dict)
        self._stats["uptime_seconds"] = round(time.time() - self._start_time)

    def add_detections(self, detections):
        """Add detections to the rolling buffer."""
        with self._buffer_lock:
            for d in detections:
                d["timestamp"] = time.time()
                self._detections_buffer.append(d)
            # Keep buffer bounded
            if len(self._detections_buffer) > 1000:
                self._detections_buffer = self._detections_buffer[-500:]

    def add_sound_event(self, event):
        """Add sound event to the rolling buffer."""
        with self._buffer_lock:
            self._sound_events_buffer.append(event)
            if len(self._sound_events_buffer) > 200:
                self._sound_events_buffer = self._sound_events_buffer[-100:]

    def add_wifi_event(self, event):
        """Add WiFi event to the rolling buffer."""
        with self._buffer_lock:
            self._wifi_events_buffer.append(event)
            if len(self._wifi_events_buffer) > 500:
                self._wifi_events_buffer = self._wifi_events_buffer[-250:]

    def run(self, threaded=True):
        """Start the Flask server."""
        print(f"[dashboard] Starting server on {self.host}:{self.port}")
        self.app.run(
            host=self.host,
            port=self.port,
            debug=self.debug,
            threaded=threaded,
            use_reloader=False,
        )
