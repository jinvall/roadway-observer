# KAKI.md - Notes and Decisions

## 2026-07-27 - Initial Build

### Decisions Made

Model choice: TensorFlow 2.21 full (not tflite-runtime) because PyPI's
tflite-runtime lacks Python 3.12 wheels. Full TF is ~500MB but works.

Models: Coral's efficientdet_lite0_320_ptq.tflite (4.3MB) and
ssd_mobilenet_v2_coco_quant_postprocess.tflite (18MB) from google-coral/test_data.

Sound detection: Simple FFT-based band energy analysis. No ML for sound.
Bands: siren (500-2000Hz), horn (200-800Hz), bark (400-1200Hz).

Dashboard: Poll-based (2s interval) rather than WebSocket. MJPEG for video.

Database: WAL mode, thread-local connections, 90-day retention, hourly VACUUM.

RTSP URL: rtsp://Bouncy:BallZach@10.0.0.153/live

### Environment

- Host: silver (10.0.0.147), Ubuntu 24.04
- Python 3.12.3, Disk: 34G free, RAM: 16GB

### Questions

1. Test RTSP stream - confirm camera accessible?
2. Any areas of the frame to mask?
3. Alerts needed (email, SMS, desktop)?
4. Night vision support?
5. Multiple cameras?
