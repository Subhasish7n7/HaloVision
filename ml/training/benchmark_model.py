"""
HaloVision inference benchmark (Phase 10).

Measures single-image inference performance of a trained checkpoint on real
dataset images: latency (mean/p50/p95), throughput (FPS), device, and payload
size of the detection JSON the app would receive.

This script is deliberately SHORT-RUN by default (100 images, warmup 10).
Long benchmarks are opt-in via --images N — nothing here runs long unless the
operator asks for it.

Outputs:
  <runs>/benchmarks/benchmark_<weights-stem>_<timestamp>.json

Usage:
    python ml/training/benchmark_model.py [--weights PATH] [--images 100]
                                          [--warmup 10] [--imgsz 640]
                                          [--device auto|cpu|0]

Exit codes: 0 = completed, 1 = failed (missing weights / load / inference).
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import DATASET_YAML, V2_MODELS_DIR, RUNS_DIR, disk_free_gb  # noqa: E402

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def collect_images(n: int) -> list[Path]:
    imgs = []
    for split in ("val", "test", "train"):
        d = DATASET_YAML.parent / "images" / split
        if not d.exists():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in IMG_EXT:
                imgs.append(p)
                if len(imgs) >= n:
                    return imgs
    return imgs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", default=str(V2_MODELS_DIR / "best.pt"))
    ap.add_argument("--images", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    print("=" * 64)
    print("MODEL INFERENCE BENCHMARK (short run)")
    print("=" * 64)
    weights = Path(args.weights)
    print(f"Weights: {weights}")
    print(f"Free D:  {disk_free_gb():.1f} GB")

    if not weights.exists():
        print(f"FAIL: weights not found: {weights}")
        return 1

    from ultralytics import YOLO

    t0 = time.time()
    try:
        model = YOLO(str(weights))
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: could not load model: {e}")
        return 1
    load_s = time.time() - t0

    device = args.device
    if device == "auto":
        import torch
        device = "0" if torch.cuda.is_available() else "cpu"

    images = collect_images(args.images + args.warmup)
    if not images:
        print("FAIL: no dataset images found to benchmark against")
        return 1

    print(f"Device:  {device}   imgsz: {args.imgsz}")
    print(f"Images:  {min(len(images), args.images + args.warmup)} "
          f"(warmup {args.warmup}, timed {min(len(images), args.images)})")

    lat_ms = []
    counts = []
    try:
        for i, img in enumerate(images):
            t = time.time()
            r = model.predict(str(img), imgsz=args.imgsz, device=device,
                              verbose=False)[0]
            dt = (time.time() - t) * 1000
            if i >= args.warmup:
                lat_ms.append(dt)
                counts.append(len(r.boxes))
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: inference error: {e}")
        return 1

    if not lat_ms:
        print("FAIL: no timed measurements (reduce --warmup)")
        return 1

    lat_ms.sort()
    mean = statistics.fmean(lat_ms)
    p50 = statistics.median(lat_ms)
    p95 = lat_ms[int(len(lat_ms) * 0.95) - 1]
    fps = 1000.0 / mean if mean else 0.0

    result = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "weights": str(weights),
        "load_seconds": round(load_s, 2),
        "device": str(device),
        "imgsz": args.imgsz,
        "warmup": args.warmup,
        "timed_images": len(lat_ms),
        "latency_ms": {"mean": round(mean, 2), "p50": round(p50, 2),
                       "p95": round(p95, 2), "min": round(lat_ms[0], 2),
                       "max": round(lat_ms[-1], 2)},
        "fps_mean": round(fps, 1),
        "mean_detections_per_image": round(statistics.fmean(counts), 2),
    }

    out_dir = RUNS_DIR / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"benchmark_{weights.stem}_{stamp}.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print()
    print(f"  load:     {load_s:.2f}s")
    print(f"  latency:  mean {mean:.1f} ms | p50 {p50:.1f} ms | p95 {p95:.1f} ms")
    print(f"  fps:      {fps:.1f} (single-stream, {device})")
    print(f"  detects:  {result['mean_detections_per_image']} avg per image")
    print(f"wrote {out}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
