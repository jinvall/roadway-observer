#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$HOME/roadway-observer"
cd "$PROJECT_DIR"

echo "=== Creating project structure ==="
mkdir -p src models config static/css static/js templates data logs sounds

echo "=== Creating Python virtual environment ==="
python3 -m venv venv
. venv/bin/activate

echo "=== Installing dependencies (this may take a few minutes) ==="
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "=== Verifying core dependencies ==="
python3 -c "
import tensorflow.lite as tflite
import cv2, flask, numpy, sqlite3, yaml
print('TFLite:', tflite.__version__ if hasattr(tflite, '__version__') else 'built-in')
print('OpenCV:', cv2.__version__)
print('Flask:', flask.__version__ if hasattr(flask, '__version__') else 'OK')
print('NumPy:', numpy.__version__)
print('SQLite: OK')
print('PyYAML: OK')
print('ALL DEPENDENCIES OK')
"

echo "=== Downloading models ==="
curl -sL -o models/efficientdet_lite0_320_ptq.tflite \
  "https://github.com/google-coral/test_data/raw/master/efficientdet_lite0_320_ptq.tflite"
curl -sL -o models/ssd_mobilenet_v2_coco_quant_postprocess.tflite \
  "https://github.com/google-coral/test_data/raw/master/ssd_mobilenet_v2_coco_quant_postprocess.tflite"
curl -sL -o models/coco_labels.txt \
  "https://github.com/google-coral/test_data/raw/master/coco_labels.txt"

echo "=== Verifying models ==="
python3 -c "
import os
for f in ['models/efficientdet_lite0_320_ptq.tflite', 'models/ssd_mobilenet_v2_coco_quant_postprocess.tflite', 'models/coco_labels.txt']:
    sz = os.path.getsize(f)
    print(f'{f}: {sz} bytes -- {\"OK\" if sz > 1000 else \"TOO SMALL\"}')"

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo "Run the observer:"
echo "  cd ~/roadway-observer"
echo "  . venv/bin/activate"
echo "  python3 src/main.py"
