# roadway-observer - System Overview

## Purpose

Production-grade roadway observation system. Processes RTSP camera
feeds through TFLite object detection on CPU, stores data in SQLite,
and provides a real-time web dashboard.

## Design Principles

1. Local Only - Zero cloud dependencies
2. Resilient - Auto-reconnect, frame timeout, rotating logs
3. Efficient - CPU-optimized models, configurable frame skip
4. Observable - Real-time dashboard with live video and stats
5. Configurable - YAML configuration with sensible defaults

## Data Flow

Camera (RTSP) -> Capture (OpenCV) -> Detector (TFLite) -> Tracker (IOU) -> Database (SQLite)
Audio (Device) -> Sound (FFT) -> Database (SQLite)
Database (SQLite) -> Dashboard (Flask Web)

## Performance Targets

- Frame processing: 5-10 FPS (CPU-only)
- Inference latency: <100ms (EfficientDet-Lite0)
- Stream reconnect: <5s automatic
- Dashboard refresh: 1s poll interval
- DB retention: 90 days, auto-purge

## Dependencies

- Python 3.12, TensorFlow 2.21, OpenCV 5.0, Flask 3.1
- ffmpeg 6.1+, sounddevice, soundfile, PyYAML, numpy, sqlite3

## Project Files

- `requirements.txt` - Python dependencies
- `pyproject.toml` - Build configuration and metadata
- `.gitignore` - Git exclusions for venv, logs, data, etc.
- `setup.sh` - Automated setup script
- `verify.sh` - File verification script
