from ultralytics import YOLO
import torch

class ObjectTracker:

    def __init__(self, model_name="yolov8m.pt"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = YOLO(model_name)

    def track(self, frame):

        results = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            device=self.device,
            conf=0.25,
            verbose=False
        )[0]

        tracks = []

        # If no detections, return safely
        if results.boxes is None or results.boxes.id is None:
            return tracks, self.model.names

        boxes = results.boxes.xyxy.cpu().numpy()
        ids = results.boxes.id.cpu().numpy()
        classes = results.boxes.cls.cpu().numpy()

        for box, track_id, cls in zip(boxes, ids, classes):

            x1, y1, x2, y2 = box

            tracks.append([
                int(track_id),
                x1,
                y1,
                x2,
                y2,
                int(cls)
            ])

        return tracks, self.model.names