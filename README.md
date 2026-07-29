# roadway-observer

Production-grade roadway observation system. Processes RTSP camera feeds through
TensorFlow Lite object detection on CPU, stores structured data in SQLite, and
provides a real-time web dashboard.

## Features

- **Object Detection** — EfficientDet-Lite0 or MobileNet SSD v2 (config-switchable)
- **Multi-class Tracking** — Vehicles, pedestrians, animals, cyclists
- **Direction & Speed** — IOU-based cross-frame tracking with direction vectors
- **Sound Events** — Local FFT-based detection of sirens, horns, barking
- **Real-time Dashboard** — Flask web UI with MJPEG live feed and stats
- **24/7 Operation** — Auto-reconnect, frame timeout handling, log rotation
- **Local Only** — No cloud dependencies, all processing on-device

## Requirements

- Ubuntu Linux (x86_64)
- Python 3.12+
- RTSP camera feed
- 16GB RAM (recommended)
- 4GB free disk

## Quick Start

```bash
cd ~/roadway-observer
bash setup.sh
. venv/bin/activate
python3 src/main.py
```

Open http://localhost:8080 in your browser.

## Configuration

Edit `config/config.yaml` to set:

| Key | Default | Description |
|---|---|---|
| `rtsp.url` | `rtsp://...` | Camera RTSP URL |
| `model.active` | `efficientdet_lite0_320_ptq` | Model to use |
| `model.inference_threshold_ms` | `200` | Buffer purge threshold in ms |
| `detection.enabled_classes` | `[vehicle, pedestrian, animal, cyclist]` | Tracked classes |
| `dashboard.port` | `8080` | Web UI port |
| `database.retention_days` | `90` | Event retention |

### WiFi MAC Correlation

Set `wifi_sniffer.enabled: true` to enable WiFi MAC correlation for vehicle detection.

| Key | Default | Description |
|---|---|---|
| `wifi_sniffer.enabled` | `false` | Enable WiFi sniffer |
| `wifi_sniffer.device` | `/dev/ttyUSB1` | USB sniffer device |
| `wifi_sniffer.history_window` | `3600` | MAC history window in seconds |

Use `config/static_ignore.json` to ignore specific MAC addresses.

## Architecture

```
RTSP Stream → ffmpeg → OpenCV → TFLite → Tracker → SQLite → Flask Dashboard
                          ↓
                    SoundDevice → FFT Analysis → SQLite
```

## Modules

| Module | Purpose |
|---|---|
| `src/main.py` | Orchestrator — frame loop, scheduler, health monitor |
| `src/capture.py` | RTSP frame reader with auto-reconnect |
| `src/detector.py` | TFLite model wrapper — inference, result parsing |
| `src/tracker.py` | IOU-based cross-frame tracking with direction |
| `src/database.py` | SQLite schema, events, stats, retention |
| `src/sound_events.py` | Audio analysis for siren/horn/bark |
| `src/dashboard.py` | Flask web UI with MJPEG stream |
| `src/config.py` | YAML config loader with defaults |
| `src/utils.py` | Logging, COCO labels, helpers |

## License

MIT
