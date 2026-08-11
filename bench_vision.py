"""HaloVision inference benchmark (CPU).

Measures detection (YOLO track) and depth (MiDaS torch) latency on a sample
frame and prints a before/after comparison table. Run from the project root:
    .venv\\Scripts\\python.exe bench_vision.py
"""
import sys
import time

import cv2
import numpy as np


def benchmark_yolo(th_evaluator, frame, warmup=3, runs=6):
    for _ in range(warmup):
        th_evaluator(frame)
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        th_evaluator(frame)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return times[len(times) // 2], sum(times) / len(times)


def benchmark_depth(predict, frame, warmup=2, runs=4):
    for _ in range(warmup):
        predict(frame)
    times = []
    depth_mean = None
    for _ in range(runs):
        t0 = time.perf_counter()
        depth_mean = predict(frame)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return times[len(times) // 2], sum(times) / len(times), float(np.mean(depth_mean))


def main():
    from ultralytics import YOLO

    import torch
    print(f"torch={torch.__version__} cuda={torch.cuda.is_available()}")

    # Sample frame from the ultralytics bundle.
    import ultralytics
    import os
    frame_path = os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg")
    frame = cv2.imread(frame_path)
    if frame is None:
        print("No sample frame found; using synthetic 640x480")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

    print(f"\nframe={frame.shape[1]}x{frame.shape[0]}")

    rows = []

    def bench(name, fn):
        med, mean = fn()
        rows.append((name, med, mean))
        print(f"{name:32s} median={med:8.1f}ms  mean={mean:8.1f}ms")

    # ---------------- DETECTION ----------------
    import os
    tracker_yaml = os.path.join(
        os.path.dirname(__file__), "App", "Perception", "bytetrack_hv.yaml"
    )

    for imgsz in (640, 480):
        m = YOLO("yolov8n.pt")

        def det(frame, m=m, imgsz=imgsz, tracker_yaml=tracker_yaml):
            m.track(frame, persist=True, tracker=tracker_yaml, imgsz=imgsz, verbose=False)
        bench(f"YOLOv8n track imgsz={imgsz}", lambda: benchmark_yolo(det, frame))

    # ---------------- DEPTH (torch) ----------------
    from App.Perception.depth_estimator import MiDaSDepthEstimator

    hybrid = MiDaSDepthEstimator(model_type="DPT_Hybrid")
    med, mean, _ = benchmark_depth(hybrid.predict, frame)
    rows.append(("MiDaS DPT_Hybrid (torch, current)", med, mean))
    print(f"{'MiDaS DPT_Hybrid (torch, current)':32s} median={med:8.1f}ms  mean={mean:8.1f}ms")

    small = MiDaSDepthEstimator(model_type="MiDaS_small")
    med, mean, _ = benchmark_depth(small.predict, frame)
    rows.append(("MiDaS MiDaS_small (torch)", med, mean))
    print(f"{'MiDaS MiDaS_small (torch)':32s} median={med:8.1f}ms  mean={mean:8.1f}ms")

    print("\nrows: (model, median_ms, mean_ms)")


if __name__ == "__main__":
    main()