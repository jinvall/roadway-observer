# Project State - roadway-observer

## Recent Changes (v1.2.0)

### WiFi Sniffer Fixes
- Device path corrected from `/dev/ttyUSB1` to `/dev/ttyUSB0` (ESP32 enumeration after reset)
- Baud rate corrected from 9600 to 115200 (ESP32 default)
- Added 1-second stabilization delay after opening USB serial device
- Improved JSONL parsing for ESP32 promiscuous mode output

### BLE Device Sniffer
- Added `ble_sniffer.py` using bleak library for BLE scanning
- BLE device correlation for detecting phones, wearables, IoT devices
- Dashboard badge shows active BLE device count
- Separate WiFi and BLE device lists on dashboard
- Shared ignore list (`config/static_ignore.json`) for both WiFi and BLE

### API Endpoints Added
- `/api/ble_events` - Recent BLE device events
- `/api/ble_status` - BLE sniffer status and device count
- `/api/ble/calibrate` - Reload BLE ignore list

### Sound Event Audio Sources
- `host_audio` - Direct microphone via sounddevice
- `video_stream` - Extract audio from RTSP (requires ffmpeg)
- `ip_stream` - Receive audio from HTTP stream
- Configurable via `sound_events.source`, `rtsp_url`, `ip_audio_url`

### Photo Capture Overlay
- WiFi devices displayed in cyan with SSID
- BLE devices displayed in green with device name
- Both filtered by shared ignore list
- Separate sections for WiFi and BLE devices on captured images

## Dashboard Updates
- BLE badge in video controls showing device count
- BLE Device Correlation panel with device list and calibrate button
- WiFi and BLE calibration buttons in their respective panels
- WiFi overlay toggle for live feed display

## Config Changes
- `ble_sniffer.enabled` - Enable BLE sniffer
- `ble_sniffer.dwell_time` - Display duration per device (default: 10s)
- `ble_sniffer.duty_cycle` - Scan interval (default: 10s)
- `sound_events.source` - Audio source type (host_audio/video_stream/ip_stream)
- `sound_events.rtsp_url` - RTSP URL for video stream audio extraction
- `sound_events.ip_audio_url` - HTTP audio stream URL

## Dependencies Added
- `pyserial>=3.5` - WiFi sniffer serial communication
- `bleak>=0.22.0` - BLE device scanning

## Performance Notes
- WiFi + BLE scanning runs in separate threads
- BLE uses async event loop with configurable duty cycle
- Inference ~600ms - consider smaller model for better performance

## Commands
```bash
# Run the application
python3 src/main.py

# Test WiFi sniffer
python3 -c "from src.wifi_sniffer import WiFiSniffer; print(WiFiSniffer().read_line())"

# Run calibration
python3 src/rf_double_sieve.py /dev/ttyUSB0

# Check BLE devices (if bleak installed)
python3 -c "from src.ble_sniffer import BleSniffer; b = BleSniffer(); b.start(); import time; time.sleep(3); b.stop()"
```