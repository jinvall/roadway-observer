"""IOU-based cross-frame tracking with direction vectors."""

import time
import math
from collections import defaultdict

from .config import load_config


class TrackedObject:
    """Represents a tracked object across frames."""

    def __init__(self, track_id, detection):
        cfg = load_config()
        self.track_id = track_id
        self.class_name = detection["class_name"]
        self.category = detection["category"]
        self.bbox = detection["bbox"]
        self.confidence = detection["confidence"]
        self.first_seen = time.time()
        self.last_seen = time.time()
        self.disappeared = 0
        self.positions = [self._center()]
        self.direction = "unknown"
        self.speed = 0.0
        self._max_positions = cfg["tracking"].get("direction_window", 30) * 2

    def _center(self):
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def update(self, detection):
        self.bbox = detection["bbox"]
        self.confidence = detection["confidence"]
        self.last_seen = time.time()
        self.disappeared = 0
        self.positions.append(self._center())
        if len(self.positions) > self._max_positions:
            self.positions = self.positions[-self._max_positions:]

    def calc_direction(self, window=30):
        """Calculate direction from recent positions."""
        positions = self.positions[-window:]
        if len(positions) < 5:
            self.direction = "unknown"
            return "unknown"

        # Average x and y movement over the window
        dx = positions[-1][0] - positions[0][0]
        dy = positions[-1][1] - positions[0][1]

        # Determine direction
        if abs(dx) < 10 and abs(dy) < 10:
            self.direction = "stationary"
        elif abs(dx) > abs(dy):
            self.direction = "right" if dx > 0 else "left"
        else:
            self.direction = "down" if dy > 0 else "up"

        # Calculate speed (pixels per second)
        elapsed = self.last_seen - self.first_seen
        if elapsed > 0:
            distance = math.sqrt(dx ** 2 + dy ** 2)
            self.speed = distance / elapsed

        return self.direction

    @property
    def age(self):
        return time.time() - self.first_seen


def iou(box_a, box_b):
    """Intersection-over-Union between two bounding boxes."""
    x1_a, y1_a, x2_a, y2_a = box_a
    x1_b, y1_b, x2_b, y2_b = box_b

    xi1 = max(x1_a, x1_b)
    yi1 = max(y1_a, y1_b)
    xi2 = min(x2_a, x2_b)
    yi2 = min(y2_a, y2_b)

    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    if inter_area == 0:
        return 0.0

    box_a_area = (x2_a - x1_a) * (y2_a - y1_a)
    box_b_area = (x2_b - x1_b) * (y2_b - y1_b)
    union_area = box_a_area + box_b_area - inter_area

    return inter_area / union_area if union_area > 0 else 0.0


class ObjectTracker:
    """Cross-frame tracker using IOU matching."""

    def __init__(self):
        cfg = load_config()
        self.iou_threshold = cfg["tracking"]["iou_threshold"]
        self.max_disappeared = cfg["tracking"]["max_disappeared"]
        self.direction_window = cfg["tracking"]["direction_window"]
        self._next_id = 0
        self._objects = {}  # track_id -> TrackedObject
        print(f"[tracker] Initialized (IOU={self.iou_threshold}, "
              f"max_disappeared={self.max_disappeared})")

    def update(self, detections):
        """Match detections to existing tracks or create new ones."""
        # Mark all as disappeared
        for obj in self._objects.values():
            obj.disappeared += 1

        if not detections:
            # No detections — just prune
            self._prune()
            return list(self._objects.values())

        if not self._objects:
            for det in detections:
                obj = TrackedObject(self._next_id, det)
                self._objects[self._next_id] = obj
                self._next_id += 1
        else:
            matched_detections = set()
            matched_tracks = set()

            for track_id, obj in sorted(self._objects.items()):
                if obj.disappeared >= self.max_disappeared:
                    continue
                best_iou = 0
                best_det = -1
                for i, det in enumerate(detections):
                    if i in matched_detections:
                        continue
                    overlap = iou(obj.bbox, det["bbox"])
                    if overlap > best_iou:
                        best_iou = overlap
                        best_det = i

                if best_iou >= self.iou_threshold and best_det >= 0:
                    matched_detections.add(best_det)
                    matched_tracks.add(track_id)
                    obj.update(detections[best_det])

            # Create new tracks for unmatched detections
            for i, det in enumerate(detections):
                if i not in matched_detections:
                    obj = TrackedObject(self._next_id, det)
                    self._objects[self._next_id] = obj
                    self._next_id += 1

        # Update directions and prune
        for obj in self._objects.values():
            obj.calc_direction(self.direction_window)
        self._prune()

        return list(self._objects.values())

    def _prune(self):
        """Remove objects that have disappeared for too long."""
        to_remove = []
        for track_id, obj in self._objects.items():
            if obj.disappeared > self.max_disappeared:
                to_remove.append(track_id)
        for track_id in to_remove:
            del self._objects[track_id]

    def get_active_objects(self):
        """Return objects that are currently visible."""
        return [obj for obj in self._objects.values() if obj.disappeared == 0]

    def reset(self):
        self._objects.clear()
        self._next_id = 0

    @property
    def stats(self):
        return {
            "active_tracks": len(self.get_active_objects()),
            "total_tracks": self._next_id,
            "current_tracks": len(self._objects),
        }
