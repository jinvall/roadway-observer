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

## WiFi MAC Correlation

Enable WiFi MAC correlation for vehicle detection by setting `wifi_sniffer.enabled: true` in `config/config.yaml`.

### WiFi Calibration

1. Open the WiFi MAC panel on the dashboard
2. Click "Calibrate MACs" button
3. The system runs two 30-second scans with a 30-second wait period
4. MACs appearing in both scans are added to `config/static_ignore.json`
5. These MACs are filtered from the overlay display

### WiFi Overlay Toggle

- **Capture button**: Takes a single frame with WiFi MAC overlay
- **WiFi Overlay toggle**: Enables/disables WiFi MAC display on live feed
- Only transient (non-ignored) MACs are displayed

### Ignored MACs

Edit `config/static_ignore.json` to manually add MACs that should not appear in overlays:

```json
{
  "ignore_macs": [
    "FF:FF:FF:FF:FF:FF",
    "00:11:22:33:44:55"
  ]
}
```

## Inference Threshold

When inference time exceeds `model.inference_threshold_ms` (default: 200ms), the detection buffer is purged to prevent memory buildup:

```yaml
model:
  inference_threshold_ms: 200
```

## Troubleshooting

- No video? Check RTSP URL, ping camera, test with ffplay
- No detections? Check confidence threshold, verify model files
- Dashboard not loading? Check port, firewall, try different port
- High CPU? Increase frame_skip, use EfficientDet-Lite0

## Graceful Shutdown

Press Ctrl+C. System stops capture, sound, DB, and exits cleanly.
