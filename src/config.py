"""Configuration loader — reads config/config.yaml with defaults."""

import os
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "rtsp": {
        "url": "rtsp://Bouncy:BallZach@10.0.0.153/live",
        "reconnect_delay": 5,
        "max_reconnects": 0,
        "frame_timeout": 10,
    },
    "model": {
        "active": "efficientdet_lite0_320_ptq.tflite",
        "available": [
            "efficientdet_lite0_320_ptq.tflite",
            "ssd_mobilenet_v2_coco_quant_postprocess.tflite",
        ],
        "model_dir": "models",
        "confidence_threshold": 0.5,
        "max_detections": 100,
        "inference_threshold_ms": 200,
    },
    "detection": {
        "enabled_classes": ["vehicle", "pedestrian", "animal", "cyclist"],
        "frame_skip": 1,
        "resize_width": 320,
        "resize_height": 320,
    },
    "tracking": {
        "enabled": True,
        "iou_threshold": 0.15,
        "max_disappeared": 30,
        "direction_window": 30,
    },
    "database": {
        "path": "data/roadway.db",
        "retention_days": 90,
        "vacuum_interval": 3600,
    },
    "sound_events": {
        "enabled": True,
        "sample_rate": 16000,
        "chunk_duration": 1.0,
        "source": "host_audio",
        "rtsp_url": "",
        "ip_audio_url": "",
        "siren_threshold": 0.6,
        "horn_threshold": 0.5,
        "bark_threshold": 0.4,
        "input_device": None,
    },
    "dashboard": {
        "host": "0.0.0.0",
        "port": 8080,
        "update_interval": 1000,
        "mjpeg_scale": 640,
        "mjpeg_quality": 70,
        "debug": False,
    },
    "logging": {
        "level": "INFO",
        "file": "logs/observer.log",
        "max_size_mb": 10,
        "backup_count": 3,
    },
    "wifi_sniffer": {
        "enabled": False,
        "device": "/dev/ttyUSB0",
        "history_window": 3600,
        "dwell_time": 10,
    },
    "ble_sniffer": {
        "enabled": False,
        "history_window": 3600,
        "dwell_time": 10,
        "duty_cycle": 10.0,
    },
    "photos": {
        "enabled": True,
        "path": "data/photos",
        "max_files": 100,
    },
}

_config_cache = None


def deep_merge(base, override):
    """Recursively merge override dict into base dict."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(reload=False):
    """Load config from config/config.yaml, merging with defaults."""
    global _config_cache
    if _config_cache is not None and not reload:
        return _config_cache

    config_path = PROJECT_ROOT / "config" / "config.yaml"
    user_config = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            user_config = yaml.safe_load(f) or {}
        print(f"[config] Loaded config from {config_path}")
    else:
        print(f"[config] No config file at {config_path}, using defaults")

    cfg = deep_merge(DEFAULTS, user_config)
    _config_cache = cfg
    return cfg



def save_config(cfg):
    """Persist config back to config/config.yaml."""
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    print(f"[config] Saved config to {config_path}")


def reload_config():
    """Force reload config from disk."""
    global _config_cache
    _config_cache = None
    return load_config(reload=True)

def model_path(model_name=None):
    """Get absolute path to a model file."""
    cfg = load_config()
    name = model_name or cfg["model"]["active"]
    return str(PROJECT_ROOT / cfg["model"]["model_dir"] / name)


def db_path():
    """Get absolute path to the database."""
    cfg = load_config()
    return str(PROJECT_ROOT / cfg["database"]["path"])


def labels_path():
    """Get absolute path to COCO labels file."""
    return str(PROJECT_ROOT / "models" / "coco_labels.txt")
