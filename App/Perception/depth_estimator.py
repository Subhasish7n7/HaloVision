# perception/depth_estimator.py
from ultralytics import YOLO
import torch
import cv2
import numpy as np

class YOLODetector:
    def __init__(self, model_name="yolov8m.pt", conf=0.65):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = YOLO(model_name)
        self.conf = conf

    def detect(self, frame):

        results = self.model(frame, conf=self.conf, device=self.device)[0]

        detections = []

        if results.boxes is None:
            return detections

        for box in results.boxes.data.cpu().numpy():
            x1, y1, x2, y2, conf, cls = box
            detections.append([x1, y1, x2, y2, conf, int(cls)])

        return detections, self.model.names





class MiDaSDepthEstimator:

    def __init__(self, model_type="DPT_Hybrid"):

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.model = torch.hub.load("intel-isl/MiDaS", model_type)
        self.model.to(self.device)
        self.model.eval()

        transforms = torch.hub.load("intel-isl/MiDaS", "transforms")

        if model_type in ["DPT_Large", "DPT_Hybrid"]:
            self.transform = transforms.dpt_transform
        else:
            self.transform = transforms.small_transform


    def predict(self, frame):

        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        input_batch = self.transform(img).to(self.device)

        with torch.no_grad():
            prediction = self.model(input_batch)

            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        depth = prediction.cpu().numpy()

        depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-6)

        return depth