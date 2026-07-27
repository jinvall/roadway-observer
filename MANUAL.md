# roadway-observer - Operation Manual

## Starting the System

```bash
cd ~/roadway-observer
. venv/bin/activate
python3 src/main.py
```

The system will:
1. Connect to the RTSP camera
2. Load the TFLite model
3. Start the Flask dashboard on port 8080
4. Begin processing frames and detecting objects

## Web Dashboard

Open http://localhost:8080 (or http://10.0.0.147:8080 from LAN)

### Dashboard Panels

| Panel | Description |
|---|---|
| Live Feed | MJPEG video stream with bounding boxes and overlay stats |
| Today's Counts | Vehicle, pedestrian, animal, cyclist counts for current day |
| System Stats | FPS, inference time, active tracks, model name |
| Recent Detections | Live scroll of detected objects with confidence |
| Sound Events | Siren, horn, bark detection events |

## API Endpoints

| Endpoint | Description |
|---|---|
| `/` | Dashboard HTML |
| `/video_feed` | MJPEG video stream |
| `/api/stats` | JSON stats |
| `/api/detections` | Recent detections |
| `/api/sound_events` | Recent sound events |
| `/api/health` | Health check with full stats |

## Configuration

Edit `config/config.yaml`:

### Changing the model

```yaml
model:
  active: "ssd_mobilenet_v2_coco_quant_postprocess.tflite"
```

### Changing detection classes

```yaml
detection:
  enabled_classes:
    - "vehicle"
    - "pedestrian"
```

### Frame processing rate

```yaml
detection:
  frame_skip: 2
```

### Sound detection thresholds

```yaml
sound_events:
  siren_threshold: 0.6
  horn_threshold: 0.5
  bark_threshold: 0.4
```

## Data Retention

Events auto-purged after 90 days (configurable). DB vacuumed hourly.

## Troubleshooting

- No video? Check RTSP URL, ping camera, test with ffplay
- No detections? Check confidence threshold, verify model files
- Dashboard not loading? Check port, firewall, try different port
- High CPU? Increase frame_skip, use EfficientDet-Lite0

## Graceful Shutdown

Press Ctrl+C. System stops capture, sound, DB, and exits cleanly.
