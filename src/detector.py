"""Model wrapper — supports TFLite local and cloud backends."""

import os
import time
import base64
import json
import numpy as np
import requests
import cv2
from .config import load_config, model_path
from .utils import load_coco_labels, class_to_category

try:
    from ai_edge_litert.interpreter import Interpreter as LiteRTInterpreter, OpResolverType
    HAS_LITERT = True
except ImportError:
    HAS_LITERT = False

import tensorflow.lite as tflite


class CloudDetector:
    """Cloud-based object detector using Hugging Face Inference API."""
    
    COCO_LABELS = {
        0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
        5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
        10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
        14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
        20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack",
        25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
        30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite", 34: "baseball bat",
        35: "baseball glove", 36: "skateboard", 37: "surfboard", 38: "tennis racket",
        39: "bottle", 40: "wine glass", 41: "cup", 42: "fork", 43: "knife", 44: "spoon",
        45: "bowl", 46: "banana", 47: "apple", 48: "sandwich", 49: "orange",
        50: "broccoli", 51: "carrot", 52: "hot dog", 53: "pizza", 54: "donut",
        55: "cake", 56: "chair", 57: "couch", 58: "potted plant", 59: "bed",
        60: "dining table", 61: "toilet", 62: "tv", 63: "laptop", 64: "mouse",
        65: "remote", 66: "keyboard", 67: "cell phone", 68: "microwave", 69: "oven",
        70: "toaster", 71: "sink", 72: "refrigerator", 73: "book", 74: "clock",
        75: "vase", 76: "scissors", 77: "teddy bear", 78: "hair drier", 79: "toothbrush",
    }

    def __init__(self, api_key=None, model_id="microsoft/dit-base-beta"):
        self.api_key = api_key or os.environ.get("HF_API_KEY")
        self.model_id = model_id
        self.endpoint = f"https://api-inference.huggingface.co/models/{model_id}"
        self.headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        print(f"[cloud] Initialized with model: {model_id}")

    def infer(self, frame):
        """Run cloud inference. Returns detections list."""
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        img_bytes = buffer.tobytes()
        
        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                data=img_bytes,
                timeout=10
            )
            response.raise_for_status()
            results = response.json()
            return self._parse_results(results)
        except Exception as e:
            return []

    def _parse_results(self, results):
        """Parse cloud API results to detection format."""
        detections = []
        if isinstance(results, list):
            for r in results:
                if 'bbox' in r and 'label' in r and 'score' in r:
                    detections.append({
                        'class_name': r['label'],
                        'category': self._label_to_category(r['label']),
                        'confidence': float(r['score']),
                        'bbox': tuple(r['bbox']),
                    })
        return detections

    def _label_to_category(self, label):
        label_lower = label.lower()
        vehicles = {"car", "truck", "bus", "motorcycle", "airplane", "train", "boat"}
        pedestrians = {"person"}
        animals = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant",
                   "bear", "zebra", "giraffe"}
        cyclists = {"bicycle", "motorcycle"}
        
        if label_lower in vehicles:
            return "vehicle"
        if label_lower in pedestrians:
            return "pedestrian"
        if label_lower in animals:
            return "animal"
        if label_lower in cyclists:
            return "cyclist"
        return "other"


class ObjectDetector:
    """Hybrid detector with local TFLite and cloud backends."""
    
    def __init__(self, model_name=None):
        cfg = load_config()
        self.model_name = model_name or cfg["model"]["active"]
        self.confidence_threshold = cfg["model"]["confidence_threshold"]
        self.max_detections = cfg["model"]["max_detections"]
        self.enabled_classes = set(cfg["detection"]["enabled_classes"])
        self.target_size = (cfg["detection"]["resize_width"],
                            cfg["detection"]["resize_height"])
        self.backend = cfg["model"].get("backend", "local")
        
        model_path_str = model_path(self.model_name)
        print(f"[detector] Loading model: {model_path_str}")
        print(f"[detector] Backend: {self.backend}")

        if self.backend == "cloud":
            cloud_cfg = cfg["model"]
            api_key = cloud_cfg.get("cloud_api_key")
            model_id = cloud_cfg.get("cloud_model_id", "microsoft/dit-base-beta")
            self._cloud = CloudDetector(api_key=api_key, model_id=model_id)
            self._is_cloud = True
        else:
            if HAS_LITERT:
                import os
                num_threads = int(os.environ.get("OMP_NUM_THREADS", "4"))
                self._interpreter = LiteRTInterpreter(
                    model_path=model_path_str,
                    num_threads=num_threads,
                    experimental_op_resolver_type=OpResolverType.AUTO,
                )
                print(f"[detector] Using backend: LiteRT ({num_threads} threads)")
            else:
                num_threads = 2
                self._interpreter = tflite.Interpreter(model_path=model_path_str, num_threads=num_threads)
                print(f"[detector] Using backend: TensorFlow TFLite ({num_threads} threads)")
            self._interpreter.allocate_tensors()
            
            self._input_details = self._interpreter.get_input_details()
            self._output_details = self._interpreter.get_output_details()
            
            input_shape = self._input_details[0]['shape']
            self._input_height = input_shape[1] if len(input_shape) > 1 else self.target_size[0]
            self._input_width = input_shape[2] if len(input_shape) > 2 else self.target_size[1]
            print(f"[detector] Model input size: {self._input_width}x{self._input_height}")
            self._is_cloud = False
        
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
        
        t0 = time.time()
        
        if self._is_cloud:
            results = self._cloud.infer(frame)
            if not results and not self._is_cloud:
                print("[detector] Cloud failed, no fallback available")
        else:
            input_data = self.preprocess(frame)
            self._interpreter.set_tensor(self._input_details[0]['index'], input_data)
            self._interpreter.invoke()
            
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
                
                if category == "other":
                    continue
                
                ymin, xmin, ymax, xmax = boxes[i]
                x1 = int(xmin * w)
                y1 = int(ymin * h)
                x2 = int(xmax * w)
                y2 = int(ymax * h)
                
                outputs.append({
                    "class_name": class_name,
                    "category": category,
                    "confidence": score,
                    "bbox": (x1, y1, x2, y2),
                    "class_id": class_id,
                })
            results = outputs

        t1 = time.time()
        self._inference_time += (t1 - t0)
        self._inference_count += 1

        filtered = []
        for r in results:
            if r.get("category") in self.enabled_classes and r.get("confidence", 0) >= self.confidence_threshold:
                filtered.append(r)
            elif r.get("category") == "other":
                continue
        
        return filtered[:self.max_detections]

    def detect_batch(self, frames):
        """Run detection on multiple frames."""
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
            "backend": "cloud" if self._is_cloud else "local",
        }