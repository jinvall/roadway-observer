"""Shared utilities: logging, timing, label loading."""

import os
import sys
import logging
import time
from logging.handlers import RotatingFileHandler

from .config import load_config, PROJECT_ROOT


def setup_logging(name="roadway"):
    """Configure rotating file logger + console handler."""
    cfg = load_config()
    level = getattr(logging, cfg["logging"]["level"].upper(), logging.INFO)
    log_path = PROJECT_ROOT / cfg["logging"]["file"]
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler with rotation
    fh = RotatingFileHandler(
        str(log_path),
        maxBytes=cfg["logging"]["max_size_mb"] * 1024 * 1024,
        backupCount=cfg["logging"]["backup_count"],
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    print(f"[utils] Logging to {log_path} at level {cfg['logging']['level']}")
    return logger


def load_coco_labels(path=None):
    """Load COCO class labels from text file."""
    if path is None:
        from .config import labels_path
        path = labels_path()
    labels = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    labels[i] = line
        print(f"[utils] Loaded {len(labels)} COCO labels from {path}")
    else:
        # COCO 80-class fallback
        labels = {
            0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
            5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
            10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
            14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
            20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack",
            25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
            30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite", 34: "baseball bat",
            35: "baseball glove", 36: "skateboard", 37: "surfboard", 38: "tennis racket",
            39: "bottle", 40: "wine glass", 41: "cup", 42: "fork", 43: "knife", 44: "spoon",
            45: "bowl", 46: "banana", 47: "apple", 48: "sandwich", 49: "orange",
            50: "broccoli", 51: "carrot", 52: "hot dog", 53: "pizza", 54: "donut",
            55: "cake", 56: "chair", 57: "couch", 58: "potted plant", 59: "bed",
            60: "dining table", 61: "toilet", 62: "tv", 63: "laptop", 64: "mouse",
            65: "remote", 66: "keyboard", 67: "cell phone", 68: "microwave", 69: "oven",
            70: "toaster", 71: "sink", 72: "refrigerator", 73: "book", 74: "clock",
            75: "vase", 76: "scissors", 77: "teddy bear", 78: "hair drier", 79: "toothbrush",
        }
        print(f"[utils] Using built-in COCO label map ({len(labels)} classes)")
    return labels


def class_to_category(class_name):
    """Map a COCO class name to our detection categories."""
    name = class_name.lower().strip()
    vehicles = {"car", "truck", "bus", "motorcycle", "airplane", "train", "boat"}
    pedestrians = {"person"}
    animals = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant",
               "bear", "zebra", "giraffe"}
    cyclists = {"bicycle", "motorcycle"}

    if name in vehicles:
        return "vehicle"
    if name in pedestrians:
        return "pedestrian"
    if name in animals:
        return "animal"
    if name in cyclists:
        return "cyclist"
    return "other"


class FPSCounter:
    """Simple FPS counter for monitoring performance."""

    def __init__(self, window=30):
        self.times = []
        self.window = window

    def tick(self):
        now = time.time()
        self.times.append(now)
        if len(self.times) > self.window:
            self.times.pop(0)

    @property
    def fps(self):
        if len(self.times) < 2:
            return 0.0
        elapsed = self.times[-1] - self.times[0]
        return (len(self.times) - 1) / elapsed if elapsed > 0 else 0.0
