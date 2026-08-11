from ultralytics import YOLO
import torch
import os

# HaloVision-tuned ByteTrack config (stable IDs across occlusion).
_TRACKER_YAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bytetrack_hv.yaml")


# =========================
# TRACK OBJECT STRUCTURE
# =========================
class Track:
    def __init__(self, track_id, bbox, cls, confidence, names):
        self.track_id = track_id
        self.bbox = bbox
        self.class_name = names[cls]
        self.confidence = confidence


# =========================
# OBJECT TRACKER
# =========================
class ObjectTracker:

    def __init__(self, model_name="yolov8n.pt", imgsz=480):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = YOLO(model_name)
        self.tracker_yaml = _TRACKER_YAML
        self.imgsz = imgsz

    def track(self, frame, conf=0.45):

        results = self.model.track(
            frame,
            persist=True,
            tracker=self.tracker_yaml,
            device=self.device,
            imgsz=self.imgsz,
            conf=conf,
            verbose=False
        )[0]

        tracks = []

        if results.boxes is None or results.boxes.id is None:
            return tracks, self.model.names

        boxes = results.boxes.xyxy.cpu().numpy()
        ids = results.boxes.id.cpu().numpy()
        classes = results.boxes.cls.cpu().numpy()
        confs = results.boxes.conf.cpu().numpy()

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