# =============================================================================
# FILE: App/Perception/tracker.py
# ROLE: Object detection and tracking — wraps YOLOv8 + ByteTrack.
#
# WHAT THIS FILE DOES:
#   1. Loads the YOLOv8 model (nano or medium weights)
#   2. Runs object detection + ByteTrack persistent tracking on each frame
#   3. Returns a list of Track objects (each with a stable track_id)
#
# WHO CALLS THIS:
#   PerceptionSystem.process_frame() in perception_system.py calls tracker.track()
#
# WHAT IT RETURNS:
#   A list of Track objects, each containing:
#     - track_id: stable identity across frames (ByteTrack maintains this)
#     - bbox: bounding box (x1, y1, x2, y2)
#     - class_name: e.g. "person", "car", "chair"
#     - confidence: detection confidence (0.0 to 1.0)
#
# WHERE THE RESULT GOES:
#   PerceptionSystem takes these Track objects and builds ObjectData instances
#   (adding depth, position, etc.) which then flow to the EventBus.
#
# KEY DESIGN DECISION:
#   The YOLO model is loaded ONCE at startup. Only the confidence threshold
#   changes between normal mode and search mode. This means starting a search
#   never restarts or reloads the detector.
# =============================================================================

from ultralytics import YOLO
import torch
import os

# Path to the ByteTrack configuration file tuned for HaloVision.
# This config controls how ByteTrack re-associates detections across frames
# (stable IDs during occlusion, etc.)
_TRACKER_YAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bytetrack_hv.yaml")


# =========================
# TRACK DATA STRUCTURE
# =========================
class Track:
    """Represents a single tracked object from one frame.

    This is the output format of ObjectTracker.track().
    It contains the raw detection result before any enrichment
    (depth, velocity, threat level — those are added by PerceptionSystem).
    """
    def __init__(self, track_id, bbox, cls, confidence, names):
        self.track_id = track_id       # ByteTrack-assigned persistent ID
        self.bbox = bbox               # (x1, y1, x2, y2) pixel coordinates
        self.class_name = names[cls]   # Human-readable class name from YOLO
        self.confidence = confidence   # Detection confidence score


# =========================
# OBJECT TRACKER
# =========================
class ObjectTracker:
    """Wraps YOLOv8 + ByteTrack for object detection and persistent tracking.

    Who creates this: main.py creates a single instance at startup.
    Who calls track(): PerceptionSystem.process_frame()

    The tracker is stateful — it maintains ByteTrack's internal state
    across frames, which is what gives objects stable identities (track_ids)
    even when they're briefly occluded.
    """

    def __init__(self, model_name=None, imgsz=480):
        # Auto-detect GPU (CUDA) or fall back to CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if model_name is None:
            model_name = self._default_model()
            print(f"[tracker] using model weights: {model_name}")
        # Load the YOLOv8 model — this loads weights into memory once
        self.model = YOLO(model_name)
        self.tracker_yaml = _TRACKER_YAML
        self.imgsz = imgsz  # Input image size for YOLO (smaller = faster)

    @staticmethod
    def _default_model():
        """Pick weights without breaking startup, in priority order:
        env HALOVISION_MODEL > trained HaloVision V2 best.pt (once it exists)
        > yolo26n.pt (spec default) > yolo26m.pt (legacy fallback)."""
        env = os.environ.get("HALOVISION_MODEL")
        if env:
            return env
        data_dir = os.environ.get("HALOVISION_DATA_DIR", "D:/HaloVisionData")
        best = os.path.join(data_dir, "models", "yolo26_halovision_v2", "best.pt")
        if os.path.exists(best):
            return best
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        nano = os.path.join(root, "yolo26n.pt")
        if os.path.exists(nano):
            return nano
        return "yolo26m.pt"

    def track(self, frame, conf=0.45):
        """Run detection + tracking on a single frame.

        Input:
            frame: OpenCV image (numpy array, BGR format)
            conf: confidence threshold (lower = more detections, more false positives)

        Output:
            (tracks, names) where:
                tracks: list of Track objects (detected + tracked objects)
                names: dict mapping class indices to names (e.g. {0: "person", 1: "bicycle"})

        Flow:
            frame (numpy BGR) → YOLOv8.track() → raw results
                → extract boxes, IDs, classes, confidences
                → wrap each into a Track object
                → return list of tracks

        The `persist=True` flag tells ByteTrack to maintain its internal
        track state across frames. This is what gives objects stable IDs.
        """

        # Run YOLOv8 detection + ByteTrack tracking in one call
        results = self.model.track(
            frame,
            persist=True,              # Maintain track IDs across frames
            tracker=self.tracker_yaml, # ByteTrack config file
            device=self.device,        # GPU or CPU
            imgsz=self.imgsz,          # Input resolution
            conf=conf,                 # Confidence threshold
            verbose=False              # Suppress YOLO console output
        )[0]  # [0] because we're processing a single frame (batch size 1)

        tracks = []

        # No detections in this frame
        if results.boxes is None or results.boxes.id is None:
            return tracks, self.model.names

        # Extract raw tensors from YOLO results and convert to numpy
        boxes = results.boxes.xyxy.cpu().numpy()   # Bounding boxes
        ids = results.boxes.id.cpu().numpy()        # ByteTrack track IDs
        classes = results.boxes.cls.cpu().numpy()   # Class indices
        confs = results.boxes.conf.cpu().numpy()    # Confidence scores

        # Wrap each detection into a Track object
        for box, track_id, cls, conf in zip(boxes, ids, classes, confs):
            x1, y1, x2, y2 = box

            tracks.append(
                Track(
                    track_id=int(track_id),
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                    cls=int(cls),
                    confidence=float(conf),
                    names=self.model.names
                )
            )

        return tracks, self.model.names
