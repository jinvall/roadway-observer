# Changelog

## [1.2.0] - 2026-07-31

### Added

- BLE (Bluetooth Low Energy) device sniffer using bleak library
- BLE device correlation for tracking phones, wearables, and IoT devices
- API endpoint `/api/ble_events` for BLE device events
- API endpoint `/api/ble_status` for BLE sniffer status
- API endpoint `/api/ble/calibrate` to reload BLE ignore list
- BLE device count and names display on dashboard badge
- `ble_sniffer` configuration section with enable, dwell_time, duty_cycle settings
- Configurable audio sources for sound events:
  - `host_audio`: Direct microphone input via sounddevice
  - `video_stream`: Extract audio from RTSP video stream (requires ffmpeg)
  - `ip_stream`: Receive audio from HTTP stream
- `sound_events.source`, `sound_events.rtsp_url`, `sound_events.ip_audio_url` configuration options
- WiFi and BLE device overlay on photo captures
  - WiFi devices displayed in cyan with SSID
  - BLE devices displayed in green with device name
  - Both filtered by shared ignore list (config/static_ignore.json)
- Added `pyserial>=3.5` dependency for WiFi sniffer serial communication
- Added `bleak>=0.22.0` dependency for BLE scanning

### Fixed

- WiFi sniffer device path corrected from `/dev/ttyUSB1` to `/dev/ttyUSB0` (ESP32 enumeration after reset)
- WiFi sniffer baud rate corrected from 9600 to 115200 (ESP32 default)
- Added 1-second stabilization delay after opening USB serial device
- Improved JSONL parsing to properly handle ESP32 promiscuous mode output
- Fixed hardcoded output path in calibration scripts to use project-relative paths
- BLE sniffer imports `load_ignore_list` from correct module (wifi_sniffer)

## [1.1.4] - 2026-07-28

### Added

- WiFi overlay toggle button in video controls
- `rf_double_sieve.py` calibration script with automatic ignore list update
- API endpoint `/api/wifi/overlay` for toggling WiFi overlay
- API endpoint `/api/wifi/calibrate` runs external calibration script
- Broadcast MAC `FF:FF:FF:FF:FF:FF` added to default ignore list
- Frame dropping when inference exceeds threshold to prevent buffer buildup

### Fixed

- Maintenance loop error handling to prevent silent failures
- Overlay stats resolution display operator precedence bug
- Removed duplicate/unreachable WiFi code in dashboard.js
- WiFi sniffer now filters ignored MACs from overlay display

### Changed

- WiFi sniffer loads ignore list from `config/static_ignore.json`
- Calibration now runs as external Python process with subprocess
- WiFi badge shows "WiFi Overlay: On/Off" toggle button
- Added `model.inference_threshold_ms` config option (default: 200ms)

## [1.1.3] - 2026-07-28

### Added

- WiFi MAC correlation for vehicle detection with USB sniffer support
- Calibration mode: 30s + 30s wait + 30s to detect static MACs
- Dynamic (transient) MAC display on capture images with SSID overlay

### Changed

- WiFi sniffer now uses non-blocking file reads to prevent dashboard hangs
- Simplified WiFi status: shows count of transient devices only
- Removed threading from WiFi sniffer for reliable synchronous updates

## [1.1.2] - 2026-07-27

### Added

- ai-edge-litert package for optimized TFLite CPU inference
- LiteRT interpreter as preferred TFLite backend (fallback to TensorFlow)

### Changed

- Updated `detector.py` to use ai-edge-litert (faster CPU inference)
- Updated `requirements.txt` with ai-edge-litert dependency
- Updated `pyproject.toml` with ai-edge-litert dependency
- Inference time reduced from ~284ms to ~124ms average (Intel N100 CPU)

## [1.1.1] - 2026-07-27

### Added

- SRP CSS theme integration with dark/light theme toggle
- Theme toggle button in header for switching themes
- Theme preference saved in localStorage

### Changed

- Updated `dashboard.css` with CSS variables and theme support
- Updated `dashboard.js` with SRP theme toggle functionality
- Updated `index.html` with theme toggle button

## [1.1.0] - 2026-07-27

### Added

- `requirements.txt` - Python dependency declaration
- `pyproject.toml` - Build configuration and project metadata
- `.gitignore` - Git exclusions for venv, logs, data, etc.
- `roadway-observer.service` - systemd service file for production deployment

### Changed

- Updated `setup.sh` to use `requirements.txt` for dependency installation
- Updated `OVERVIEW.md` with project files section

## [1.0.0] - 2026-07-27

### Initial Release

- RTSP Capture with auto-reconnect and configurable timeout
- Object Detection with EfficientDet-Lite0 and MobileNet SSD v2
- COCO 80-class label map with category mapping
- Cross-frame IOU tracking with direction vectors and speed
- Sound Event Detection via FFT for sirens, horns, barking
- SQLite database with 90-day retention and auto-vacuum
- Flask web dashboard with MJPEG stream and real-time stats
- YAML configuration with full defaults
- Rotating file logs with console output
- Python 3.12, TensorFlow 2.21, OpenCV 5.0, Flask 3.1
