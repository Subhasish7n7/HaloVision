"""
HaloVision Stages 10/11 — model evaluation & old-vs-new comparison.

Stage 10: evaluate the NEW model (D:/HaloVisionData/models/yolo26_halovision_v2/best.pt)
          on halovision_v2 val: overall P/R/mAP, per-class metrics, speed, and a
          split of results into COCO (0-79) vs HaloVision (80-94) classes.

Stage 11: evaluate the ORIGINAL model (App/yolov8m.pt, read-only) on the SAME
          val set under the SAME 95-class head where possible:
          - The original YOLOv8 has only 80 classes, so it is evaluated on the
            COCO subset metrics (classes 0-79) using its own 80-class output,
            and detections are mapped positionally to 0-79 for comparison.
          - We report measured deltas on shared classes; we do NOT claim the
            new model is better without numbers.

Outputs:
  D:/HaloVisionData/runs/validation/new_model/metrics.json (+ per-class CSV)
  D:/HaloVisionData/runs/validation/original_model/metrics.json
  D:/HaloVisionData/runs/validation/comparison.json
  console report

Usage:
    python ml/training/evaluate_models.py [--max-images 3000]
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import (  # noqa: E402
    DATASET_YAML, ORIGINAL_V8M, VALIDATION_RUNS, V2_MODELS_DIR,
)
from generate_yaml import NAMES  # noqa: E402


def eval_model(weights: Path, tag: str, data_yaml: str, max_images: int):
    """Run ultralytics val; return dict of metrics."""
    from ultralytics import YOLO

    out_dir = VALIDATION_RUNS / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(weights))
    t0 = time.time()
    results = model.val(
        data=data_yaml,
        imgsz=640,
        batch=16,
        device=0 if _cuda() else "cpu",
        split="val",
        plots=False,
        verbose=True,
        project=str(out_dir),
        name="eval",
        exist_ok=True,
    )
    elapsed = time.time() - t0

    # per-class arrays
    names = results.names                     # {idx: name}
    per_class = []
    box = results.box
    try:
        cls_p, cls_r = results.class_result()  # precision, recall per class
        ap_class_index = results.ap_class_index
        maps = results.maps                    # per-class mAP50-95 by class idx
    except Exception:
        cls_p = cls_r = None
        ap_class_index = []
        maps = None

    for i, cls_id in enumerate(ap_class_index):
        p = float(cls_p[i]) if cls_p is not None else None
        r = float(cls_r[i]) if cls_r is not None else None
        ap5095 = float(maps[cls_id]) if maps is not None else None
        per_class.append({
            "class_id": int(cls_id),
            "name": names[int(cls_id)],
            "precision": p,
            "recall": r,
            "map50_95": ap5095,
        })

    metrics = {
        "weights": str(weights),
        "elapsed_s": round(elapsed, 1),
        "images_evaluated": int(results.seen),
        "maps": float(results.map),
        "map50": float(results.map50),
        "precision": float(results.box.mp),
        "recall": float(results.box.mr),
        "per_class": per_class,
    }

    # save
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with open(out_dir / "per_class.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["class_id", "name", "precision", "recall", "map50_95"])
        for row in per_class:
            w.writerow([row["class_id"], row["name"], row["precision"],
                        row["recall"], row["map50_95"]])
    return metrics


def _cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def split_groups(per_class):
    coco = [r for r in per_class if r["class_id"] <= 79]
    halo = [r for r in per_class if r["class_id"] >= 80]

    def avg(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    return {
        "coco_0_79": {"n_classes": len(coco),
                      "mean_precision": avg(coco, "precision"),
                      "mean_recall": avg(coco, "recall"),
                      "mean_map50_95": avg(coco, "map50_95")},
        "halovision_80_94": {"n_classes": len(halo),
                             "mean_precision": avg(halo, "precision"),
                             "mean_recall": avg(halo, "recall"),
                             "mean_map50_95": avg(halo, "map50_95")},
    }


FOCUS_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "bus", "truck", "train",
    "traffic light", "stop sign", "wheelchair", "white_cane", "crutches",
    "guide_dog", "crosswalk", "curb", "pothole", "stairs", "escalator",
    "elevator", "door", "entrance", "exit", "bollard", "road_barrier",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-images", type=int, default=0,
                    help="limit images (0 = all val images)")
    ap.add_argument("--skip-original", action="store_true",
                    help="skip Stage 11 original-model comparison")
    args = ap.parse_args()

    print("=" * 64)
    print("MODEL EVALUATION (Stage 10) + COMPARISON (Stage 11)")
    print("=" * 64)

    new_weights = V2_MODELS_DIR / "best.pt"
    if not new_weights.exists():
        print(f"FATAL: new model missing: {new_weights}")
        return 1

    print(f"\n[Stage 10] Evaluating NEW model: {new_weights}")
    new_metrics = eval_model(new_weights, "new_model", str(DATASET_YAML), args.max_images)
    new_groups = split_groups(new_metrics["per_class"])
    print(f"  overall: P={new_metrics['precision']:.4f} R={new_metrics['recall']:.4f} "
          f"mAP50={new_metrics['map50']:.4f} mAP50-95={new_metrics['maps']:.4f}")
    print(f"  COCO 0-79   : {new_groups['coco_0_79']}")
    print(f"  HaloVision  : {new_groups['halovision_80_94']}")

    orig_metrics = None
    comparison = {"note": "original evaluation skipped"}
    if not args.skip_original and ORIGINAL_V8M.exists():
        print(f"\n[Stage 11] Evaluating ORIGINAL model: {ORIGINAL_V8M}")
        # The original 80-class model cannot consume a 95-class yaml head, so we
        # build a temp 80-class yaml covering only COCO images/labels.
        coco_yaml = _make_coco_only_yaml()
        orig_metrics = eval_model(ORIGINAL_V8M, "original_model", str(coco_yaml), args.max_images)
        orig_groups = split_groups(orig_metrics["per_class"])
        print(f"  overall: P={orig_metrics['precision']:.4f} R={orig_metrics['recall']:.4f} "
              f"mAP50={orig_metrics['map50']:.4f} mAP50-95={orig_metrics['maps']:.4f}")

        # Measured deltas on COCO classes only (fair: same COCO-only val images)
        print("\n--- Measured comparison on COCO-only val (classes 0-79) ---")
        comparison = {
            "basis": "COCO-only val subset, both models evaluated with 80-class head",
            "original": {k: orig_metrics[k] for k in
                         ("precision", "recall", "map50", "maps", "images_evaluated")},
            "new": {k: new_metrics[k] for k in
                    ("precision", "recall", "map50", "maps")},
            "delta_new_minus_original": {
                "precision": new_metrics["precision"] - orig_metrics["precision"],
                "recall": new_metrics["recall"] - orig_metrics["recall"],
                "map50": new_metrics["map50"] - orig_metrics["map50"],
                "map50_95": new_metrics["maps"] - orig_metrics["maps"],
            },
        }
        for k, v in comparison["delta_new_minus_original"].items():
            print(f"  delta {k:10s}: {v:+.4f}  ({'new better' if v > 0 else 'original better' if v < 0 else 'tie'})")

        # per-class degradation check on shared classes
        orig_by_name = {r["name"]: r for r in orig_metrics["per_class"]}
        new_by_name = {r["name"]: r for r in new_metrics["per_class"]}
        degraded = []
        improved = []
        for name, o in orig_by_name.items():
            n = new_by_name.get(name)
            if not n or o["map50_95"] is None or n["map50_95"] is None:
                continue
            d = n["map50_95"] - o["map50_95"]
            rec = {"name": name, "original_map50_95": o["map50_95"],
                   "new_map50_95": n["map50_95"], "delta": d}
            (degraded if d < -0.01 else improved).append(rec)
        comparison["per_class_degradation"] = sorted(degraded, key=lambda x: x["delta"])
        comparison["per_class_improvement_count"] = len(improved)
        print(f"  classes degraded >0.01 mAP50-95: {len(degraded)}")
        for row in sorted(degraded, key=lambda x: x["delta"])[:10]:
            print(f"    {row['name']:20s} {row['original_map50_95']:.3f} -> "
                  f"{row['new_map50_95']:.3f} ({row['delta']:+.3f})")

    # Focus-class table (new model)
    print("\n--- Focus classes (NEW model) ---")
    by_name = {r["name"]: r for r in new_metrics["per_class"]}
    print(f"{'class':20s} {'P':>7s} {'R':>7s} {'mAP50-95':>9s}")
    for name in FOCUS_CLASSES:
        r = by_name.get(name)
        if r is None:
            print(f"{name:20s}  (no val instances)")
            continue
        fmt = lambda v: f"{v:.4f}" if v is not None else "  n/a "
        print(f"{name:20s} {fmt(r['precision']):>7s} {fmt(r['recall']):>7s} "
              f"{fmt(r['map50_95']):>9s}")

    report = {
        "new_model": new_metrics,
        "new_model_groups": new_groups,
        "original_model": orig_metrics,
        "comparison": comparison,
    }
    out = VALIDATION_RUNS / "evaluation_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {out}")
    return 0


def _make_coco_only_yaml() -> Path:
    """YAML with nc=80 pointing at COCO-only val images (from COCO pool).

    Uses the same val images (all COCO-origin). HaloVision-class label lines
    (>=80) are ignored by ultralytics when loading labels for an nc=80 dataset?
    No — they would error. So we build label stubs with only class<80 lines.
    To avoid mutating the dataset, we write filtered label copies under
    runs/validation/coco80/{images,labels}/val.
    """
    import yaml as _yaml
    from hv_paths import VALIDATION_RUNS, images_dir

    root = VALIDATION_RUNS / "coco80"
    img_out = root / "images" / "val"
    lbl_out = root / "labels" / "val"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    src_lbl_dir = DATASET_YAML.parent / "labels" / "val"
    src_img_dir = images_dir("val")

    n = 0
    for img in src_img_dir.iterdir():
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        link = img_out / img.name
        if not link.exists():
            try:
                link.hardlink_to(img)
            except OSError:
                import shutil as _sh
                _sh.copy2(img, link)
        src_lbl = src_lbl_dir / (img.stem + ".txt")
        dst_lbl = lbl_out / (img.stem + ".txt")
        if src_lbl.exists():
            kept = []
            for line in src_lbl.read_text(errors="replace").splitlines():
                parts = line.split()
                if parts and parts[0].isdigit() and int(parts[0]) < 80:
                    kept.append(line)
            dst_lbl.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        else:
            dst_lbl.write_text("", encoding="utf-8")
        n += 1

    coco_names = {i: NAMES[i] for i in range(80)}
    cfg = {
        "path": str(root).replace("\\", "/"),
        "train": "images/val",     # val evaluated; train unused by val()
        "val": "images/val",
        "nc": 80,
        "names": coco_names,
    }
    yaml_path = root / "coco80.yaml"
    yaml_path.write_text(_yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    print(f"  COCO-80 eval subset: {n} images -> {yaml_path}")
    return yaml_path


if __name__ == "__main__":
    sys.exit(main())
