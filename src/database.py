"""SQLite database — schema, events, stats, retention."""

import sqlite3
import time
import threading
from pathlib import Path

from .config import db_path, load_config


class RoadwayDB:
    """Thread-safe SQLite wrapper for detection events."""

    def __init__(self, path=None):
        self.path = Path(path or db_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()
        print(f"[database] DB at {self.path}")

    def _get_conn(self):
        """Get thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.path))
            self._local.conn.execute("PRAGMA journal_mode=DELETE")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                track_id INTEGER,
                class_name TEXT NOT NULL,
                category TEXT NOT NULL,
                confidence REAL NOT NULL,
                x1 REAL, y1 REAL, x2 REAL, y2 REAL,
                direction TEXT,
                speed REAL
            );
            CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections(timestamp);
            CREATE INDEX IF NOT EXISTS idx_detections_cat ON detections(category);

            CREATE TABLE IF NOT EXISTS sound_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                duration REAL,
                peak_freq REAL
            );
            CREATE INDEX IF NOT EXISTS idx_sound_ts ON sound_events(timestamp);

            CREATE TABLE IF NOT EXISTS stats_hourly (
                hour INTEGER PRIMARY KEY,
                vehicle_count INTEGER DEFAULT 0,
                pedestrian_count INTEGER DEFAULT 0,
                animal_count INTEGER DEFAULT 0,
                cyclist_count INTEGER DEFAULT 0,
                sound_count INTEGER DEFAULT 0,
                peak_objects INTEGER DEFAULT 0,
                avg_confidence REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT,
                data TEXT
            );
        """)
        conn.commit()
        print("[database] Schema initialized")

    # --- Detection writes ---

    def insert_detection(self, track_id, class_name, category, confidence,
                         bbox=None, direction=None, speed=None):
        """Insert a single detection event."""
        ts = time.time()
        x1 = y1 = x2 = y2 = None
        if bbox:
            x1, y1, x2, y2 = bbox
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO detections
                   (timestamp, track_id, class_name, category, confidence,
                    x1, y1, x2, y2, direction, speed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, track_id, class_name, category, confidence,
                 x1, y1, x2, y2, direction, speed),
            )
            conn.commit()

    def insert_batch_detections(self, detections):
        """Insert multiple detections in one transaction."""
        ts = time.time()
        rows = []
        for d in detections:
            bbox = d.get("bbox") or (None, None, None, None)
            rows.append((
                ts, d.get("track_id"), d.get("class_name"), d.get("category"),
                d.get("confidence", 0.0), bbox[0], bbox[1], bbox[2], bbox[3],
                d.get("direction"), d.get("speed"),
            ))
        with self._lock:
            conn = self._get_conn()
            conn.executemany(
                """INSERT INTO detections
                   (timestamp, track_id, class_name, category, confidence,
                    x1, y1, x2, y2, direction, speed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
            conn.commit()

    # --- Sound events ---

    def insert_sound_event(self, event_type, confidence, duration=None, peak_freq=None):
        ts = time.time()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO sound_events
                   (timestamp, event_type, confidence, duration, peak_freq)
                   VALUES (?, ?, ?, ?, ?)""",
                (ts, event_type, confidence, duration, peak_freq),
            )
            conn.commit()

    # --- System events ---

    def log_system_event(self, event_type, message, data=None):
        ts = time.time()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO system_events (timestamp, event_type, message, data)
                   VALUES (?, ?, ?, ?)""",
                (ts, event_type, message, str(data) if data else None),
            )
            conn.commit()

    # --- Stats queries ---

    def get_recent_detections(self, limit=100):
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM detections ORDER BY timestamp DESC LIMIT ?", (limit,))
        return cur.fetchall()

    def get_detection_count(self, category=None, since=None):
        conn = self._get_conn()
        if category and since:
            cur = conn.execute(
                "SELECT COUNT(*) FROM detections WHERE category=? AND timestamp>=?",
                (category, since))
        elif category:
            cur = conn.execute(
                "SELECT COUNT(*) FROM detections WHERE category=?", (category,))
        elif since:
            cur = conn.execute(
                "SELECT COUNT(*) FROM detections WHERE timestamp>=?", (since,))
        else:
            cur = conn.execute("SELECT COUNT(*) FROM detections")
        return cur.fetchone()[0]

    def get_todays_counts(self):
        """Return dict of today's unique tracks per category.
        
        Counts unique track_id-minute combinations to prevent
        the same vehicle from being counted 100+ times.
        """
        today_start = int(time.time() - (time.time() % 86400))
        conn = self._get_conn()
        categories = ["vehicle", "pedestrian", "animal", "cyclist"]
        result = {}
        for cat in categories:
            # Count unique track_id per minute window
            cur = conn.execute(
                """SELECT COUNT(DISTINCT CAST(track_id AS TEXT) || '_' || CAST(CAST(timestamp AS INTEGER) / 60 AS TEXT))
                   FROM detections
                   WHERE category=? AND timestamp>=?""",
                (cat, today_start))
            result[cat] = cur.fetchone()[0]
        conn.commit()
        return result


    def get_sound_event_count(self, category=None, since=None):
        """Count sound events, optionally filtered by type and time."""
        conn = self._get_conn()
        if category and since:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sound_events WHERE event_type=? AND timestamp>=?",
                (category, since))
        elif category:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sound_events WHERE event_type=?", (category,))
        elif since:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sound_events WHERE timestamp>=?", (since,))
        else:
            cur = conn.execute("SELECT COUNT(*) FROM sound_events")
        return cur.fetchone()[0]

    def get_recent_sound_events(self, limit=50):
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM sound_events ORDER BY timestamp DESC LIMIT ?", (limit,))
        return cur.fetchall()

    def get_system_events(self, limit=50):
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM system_events ORDER BY timestamp DESC LIMIT ?", (limit,))
        return cur.fetchall()

    # --- Retention ---

    def purge_old_events(self):
        """Remove events older than retention_days."""
        cfg = load_config()
        days = cfg["database"]["retention_days"]
        cutoff = time.time() - (days * 86400)
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM detections WHERE timestamp<?", (cutoff,))
            conn.execute("DELETE FROM sound_events WHERE timestamp<?", (cutoff,))
            conn.execute("DELETE FROM system_events WHERE timestamp<?", (cutoff,))
            conn.commit()
            print(f"[database] Purged events older than {days} days")

    def vacuum(self):
        with self._lock:
            conn = self._get_conn()
            conn.execute("VACUUM")
            conn.commit()
            print("[database] VACUUM completed")
