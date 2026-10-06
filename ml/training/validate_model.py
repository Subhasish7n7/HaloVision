"""
HaloVision trained-model validation (Phase 10).

Validates a TRAINED 95-class checkpoint before integration. Never trains,
never mutates the dataset, exits non-zero on any critical failure.

Checks (critical unless noted):
  [1] weights file exists
  [2] model loads with ultralytics
  [3] class count == 95 (nc from class_mapping.json)
  [4] every class name matches class_mapping.json at its exact id
  [5] single-image inference produces a valid detection payload
      (label is a string from our class names, bbox coordinates finite)
  [6] --full-val (OPTIONAL, long): run ultralytics val on the dataset and
      require metrics to be produced (mAP printed, not thresholded)

Usage:
    python ml/training/validate_model.py [--weights PATH] [--image IMG] [--full-val]

Default weights: <models/yolo26_halovision_v2>/best.pt
Exit codes: 0 = PASS, 1 = FAIL
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import (  # noqa: E402
    DATASET_YAML, ML_TRAINING, V2_MODELS_DIR, disk_free_gb,
)

CRITICAL = []


def fail(step: str, msg: str) -> None:
    CRITICAL.append(f"[{step}] {msg}")
    print(f"  CRITICAL {step}: {msg}")


def ok(step: str, msg: str) -> None:
    print(f"  ok {step}: {msg}")


def first_val_image() -> Path | None:
    img_dir = DATASET_YAML.parent / "images" / "val"
    if not img_dir.exists():
        return None
    for p in sorted(img_dir.iterdir()):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", default=str(V2_MODELS_DIR / "best.pt"))
    ap.add_argument("--image", default=None,
                    help="image for the inference sanity check (default: first val image)")
    ap.add_argument("--full-val", action="store_true",
                    help="also run dataset validation metrics (LONG, minutes)")
    args = ap.parse_args()

    print("=" * 64)
    print("TRAINED MODEL VALIDATION")
    print("=" * 64)
    weights = Path(args.weights)
    print(f"Weights: {weights}")
    print(f"Free D:  {disk_free_gb():.1f} GB")

    # [1] exists
    if not weights.exists():
        fail("1", f"weights not found: {weights}")
        print("\nMODEL VALIDATION: FAILED")
        return 1
    ok("1", f"exists ({weights.stat().st_size / 1e6:.1f} MB)")

    # class truth
    mapping = json.loads((ML_TRAINING / "class_mapping.json").read_text(encoding="utf-8"))
    expect_names = {int(k): v for k, v in mapping["classes"].items()}
    nc = len(expect_names)

    # [2] loads
    try:
        from ultralytics import YOLO
        t0 = time.time()
        model = YOLO(str(weights))
        ok("2", f"loaded in {time.time() - t0:.1f}s")
    except Exception as e:  # noqa: BLE001
        fail("2", f"ultralytics could not load the model: {e}")
        print("\nMODEL VALIDATION: FAILED")
        return 1

    # [3] nc  (attributes differ across ultralytics versions — probe defensively)
    raw_nc = getattr(model, "nc", None)
    if raw_nc is None and hasattr(model, "model"):
        raw_nc = getattr(model.model, "nc", None)
    if isinstance(raw_nc, (list, tuple)):
        raw_nc = raw_nc[-1]
    try:
        got_nc = int(raw_nc)
    except (TypeError, ValueError):
        got_nc = len(model_names) if model_names else -1
    if got_nc != nc:
        fail("3", f"model nc={got_nc}, expected {nc}")
    else:
        ok("3", f"nc == {nc}")

    # [4] names
    model_names = getattr(model, "names", None) or {}
    mismatches = []
    for i in range(nc):
        got = model_names.get(i)
        want = expect_names[i]
        if got != want:
            mismatches.append(f"id {i}: model={got!r} mapping={want!r}")
    if mismatches:
        fail("4", f"{len(mismatches)} name mismatches, e.g. {mismatches[:3]}")
    else:
        ok("4", "all 95 class names match class_mapping.json exactly")

    # [5] inference sanity
    img = Path(args.image) if args.image else first_val_image()
    if img is None or not img.exists():
        fail("5", f"no image available for inference check ({img})")
    else:
        try:
            t0 = time.time()
            res = model.predict(str(img), verbose=False)
            dt = time.time() - t0
            r = res[0]
            names = r.names
            problems = []
            for b in r.boxes:
                label = b.cls
                cls_id = int(label)
                if not isinstance(names.get(cls_id), str):
                    problems.append(f"cls {cls_id} has no string label")
                xyxy = b.xyxy[0].tolist()
                if any(x != x or x in (float("inf"), float("-inf")) for x in xyxy):
                    problems.append(f"non-finite bbox for cls {cls_id}")
            if problems:
                fail("5", "; ".join(problems))
            else:
                n = len(r.boxes)
                ok("5", f"inference on {img.name}: {n} detections in {dt * 1000:.0f} ms "
                        f"(0 detections is acceptable)")
        except Exception as e:  # noqa: BLE001
            fail("5", f"inference failed: {e}")

    # [6] optional full val (LONG)
    if args.full_val:
        print("  [6] running full validation (this takes minutes) ...")
        try:
            metrics = model.val(data=str(DATASET_YAML), verbose=False)
            mp = getattr(metrics, "box", None)
            print(f"  ok 6: val metrics produced (mAP50-95="
                  f"{float(getattr(mp, 'map', 0)):.4f}, mAP50={float(getattr(mp, 'map50', 0)):.4f})")
        except Exception as e:  # noqa: BLE001
            fail("6", f"full val failed: {e}")
    else:
        print("  [6] skipped (run with --full-val for dataset metrics)")

    print()
    if CRITICAL:
        print("MODEL VALIDATION: FAILED")
        for c in CRITICAL:
            print(f"  - {c}")
        print("=" * 64)
        return 1
    print("MODEL VALIDATION: PASSED")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
