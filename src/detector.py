"""TFLite model wrapper — inference, result parsing, class filtering."""

import time
import numpy as np

import cv2
from .config import load_config, model_path
from .utils import load_coco_labels, class_to_category

try:
    from ai_edge_litert.interpreter import Interpreter as LiteRTInterpreter, OpResolverType
    HAS_LITERT = True
except ImportError:
    HAS_LITERT = False

import tensorflow.lite as tflite


class ObjectDetector:
    """Thread-safe TFLite object detector with COCO class mapping."""

    def __init__(self, model_name=None):
        cfg = load_config()
        self.model_name = model_name or cfg["model"]["active"]
        self.confidence_threshold = cfg["model"]["confidence_threshold"]
        self.max_detections = cfg["model"]["max_detections"]
        self.enabled_classes = set(cfg["detection"]["enabled_classes"])
        self.target_size = (cfg["detection"]["resize_width"],
                            cfg["detection"]["resize_height"])

        model_path_str = model_path(self.model_name)
        print(f"[detector] Loading model: {model_path_str}")

        if HAS_LITERT:
            self._interpreter = LiteRTInterpreter(
                model_path=model_path_str,
                num_threads=2,
                experimental_op_resolver_type=OpResolverType.AUTO,
            )
            print(f"[detector] Using backend: LiteRT")
        else:
            self._interpreter = tflite.Interpreter(model_path=model_path_str, num_threads=2)
            print(f"[detector] Using backend: TensorFlow TFLite")
        self._interpreter.allocate_tensors()

        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()

        for d in self._input_details:
            print(f"[detector] Input: {d['name']} shape={d['shape']} dtype={d['dtype']}")
        for d in self._output_details:
            print(f"[detector] Output: {d['name']} shape={d['shape']} dtype={d['dtype']}")

        input_shape = self._input_details[0]['shape']
        self._input_height = input_shape[1] if len(input_shape) > 1 else self.target_size[0]
        self._input_width = input_shape[2] if len(input_shape) > 2 else self.target_size[1]
        print(f"[detector] Model input size: {self._input_width}x{self._input_height}")

        self._labels = load_coco_labels()
        self._inference_time = 0.0
        self._inference_count = 0

        print(f"[detector] Model '{self.model_name}' loaded. "
              f"Enabled classes: {self.enabled_classes}")

    def preprocess(self, frame):
        """Resize and normalize frame for model input."""
        img = cv2.resize(frame, (self._input_width, self._input_height))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        input_data = np.expand_dims(img, axis=0).astype(np.uint8)
        return input_data

    def detect(self, frame):
        """Run detection on a frame. Returns list of detection dicts."""
        h, w = frame.shape[:2]

        input_data = self.preprocess(frame)

        t0 = time.time()
        self._interpreter.set_tensor(self._input_details[0]['index'], input_data)
        self._interpreter.invoke()
        t1 = time.time()

        self._inference_time += (t1 - t0)
        self._inference_count += 1

        outputs = []
        boxes = self._interpreter.get_tensor(self._output_details[0]['index'])[0]
        classes = self._interpreter.get_tensor(self._output_details[1]['index'])[0]
        scores = self._interpreter.get_tensor(self._output_details[2]['index'])[0]
        num_detections = int(self._interpreter.get_tensor(
            self._output_details[3]['index'])[0])

        num_detections = min(num_detections, self.max_detections)

        for i in range(num_detections):
            score = float(scores[i])
            if score < self.confidence_threshold:
                continue

            class_id = int(classes[i])
            class_name = self._labels.get(class_id, f"class_{class_id}")
            category = class_to_category(class_name)

            if category not in self.enabled_classes and category != "other":
                pass
            if category == "other":
                continue

            ymin, xmin, ymax, xmax = boxes[i]
            x1 = int(xmin * w)
            y1 = int(ymin * h)
            x2 = int(xmax * w)
            y2 = int(ymax * h)

            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            outputs.append({
                "class_name": class_name,
                "category": category,
                "confidence": score,
                "bbox": (x1, y1, x2, y2),
                "class_id": class_id,
            })

        return outputs

    def detect_batch(self, frames):
        """Run detection on multiple frames. Returns list of results."""
        return [self.detect(f) for f in frames]

    @property
    def avg_inference_time(self):
        if self._inference_count == 0:
            return 0.0
        return self._inference_time / self._inference_count

    @property
    def stats(self):
        return {
            "model": self.model_name,
            "avg_inference_ms": round(self.avg_inference_time * 1000, 1),
            "total_inferences": self._inference_count,
            "threshold": self.confidence_threshold,
        }