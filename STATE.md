# Project State - roadway-observer

## Recent Changes (v1.1.4)

### WiFi Calibration
- Added `rf_double_sieve.py` - runs two 30s scans to detect static MACs
- Calibration button runs external Python process
- MACs in both scans added to `config/static_ignore.json`
- Debug logging added to calibration function

### WiFi Overlay Toggle
- Added toggle button in video controls
- API endpoint `/api/wifi/overlay` to enable/disable
- WiFi sniffer filters ignored MACs from display

### Inference Threshold
- Configurable via `model.inference_threshold_ms` (default: 200ms)
- Added to Settings page under "Detection Model"
- Added to API config response

### Bug Fixes
- Added error handling to maintenance loop
- Fixed operator precedence in resolution display
- Added None checks in tracker calc_direction
- Removed duplicate WiFi code
- Added `FF:FF:FF:FF:FF:FF` to ignore list

## Config Changes
- Removed `inference_threshold_ms: null` from config.yaml
- Added inference_threshold_ms to API config endpoint
- WiFi sniffer enabled by default

## Known Issues
- None currently - restart performs graceful shutdown with proper cleanup

## Commands
```bash
# Run the application
python3 src/main.py

# Run calibration
python3 src/rf_double_sieve.py /dev/ttyUSB1
```