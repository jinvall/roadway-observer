#!/usr/bin/env bash
echo "=== roadway-observer File Verification ==="
echo ""
EXPECTED=( 
  "setup.sh" "config/config.yaml" "src/__init__.py"
  "src/config.py" "src/utils.py" "src/database.py"
  "src/capture.py" "src/detector.py" "src/tracker.py"
  "src/sound_events.py" "src/dashboard.py" "src/main.py"
  "templates/index.html" "static/css/dashboard.css"
  "static/js/dashboard.js" "README.md" "MANUAL.md"
  "CHANGELOG.md" "OVERVIEW.md" "TODO.md" "KAKI.md"
  "models/efficientdet_lite0_320_ptq.tflite"
  "models/ssd_mobilenet_v2_coco_quant_postprocess.tflite"
  "models/coco_labels.txt"
)
MISSING=0
for f in "${EXPECTED[@]}"; do
  FPATH="$HOME/roadway-observer/$f"
  if [ -f "$FPATH" ]; then
    SIZE=$(stat -c%s "$FPATH" 2>/dev/null)
    echo "  OK  $f ($SIZE bytes)"
  else
    echo "  MISSING: $f"
    MISSING=$((MISSING + 1))
  fi
done
echo ""
echo "=== Summary ==="
echo "Files found: $(( ${#EXPECTED[@]} - MISSING )) / ${#EXPECTED[@]}"
if [ $MISSING -eq 0 ]; then
  echo "All files present. Ready to launch!"
else
  echo "$MISSING file(s) missing."
fi
