"""
HaloVision image inference tester.

Point it at your own photo(s) (or any folder) and see what the current model
detects. Annotated copies are saved so you can look at the boxes.

What you can test:
  * COCO classes 0-79 (person, car, traffic light, ...)  -> detectable NOW
    with the base yolo26n.pt weights.
  * HaloVision classes 80-94 (wheelchair, white_cane, pothole, ...) ->
    only detectable AFTER training produces models/yolo26_halovision_v2/best.pt.
  The tool auto-picks best.pt when it exists, else falls back to the base
  model and says so explicitly.

Never trains, never touches the dataset. Outputs go to
D:/HaloVisionData/runs/benchmarks/predictions/.

Usage:
    python ml/training/predict_images.py --source "D:/photos/street.jpg"
    python ml/training/predict_images.py --source "D:/photos" --conf 0.3
    python ml/training/predict_images.py --source IMG --model PATH/weights.pt

Exit codes: 0 = ran, 1 = failed (missing source / model load error).
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import (  # noqa: E402
    BASE_YOLO26M, BASE_YOLO26N, RUNS_DIR, V2_MODELS_DIR,
    disk_free_gb,
)

IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
PRED_DIR = RUNS_DIR / "benchmarks" / "predictions"
CUSTOM_ID_MIN = 80  # HaloVision classes 80-94


def resolve_model(explicit: str | None) -> tuple[Path, str]:
    """Explicit --model > HALOVISION_MODEL env > trained best.pt > base."""
    if explicit:
        return Path(explicit), "--model"
    import os
    env = os.environ.get("HALOVISION_MODEL")
    if env:
        return Path(env), "HALOVISION_MODEL env"
    best = V2_MODELS_DIR / "best.pt"
    if best.exists():
        return best, "trained v2 model"
    for base in (BASE_YOLO26N, BASE_YOLO26M):
        if base.exists():
            return base, "base model (fallback)"
    raise FileNotFoundError("no weights found: tried best.pt, yolo26n.pt, yolo26m.pt")


def collect_images(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() in IMG_EXTS else []
    if source.is_dir():
        return sorted(p for p in source.rglob("*")
                      if p.is_file() and p.suffix.lower() in IMG_EXTS)
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True,
                    help="image file or folder of images")
    ap.add_argument("--model", default=None,
                    help="weights path (default: runtime chain)")
    ap.add_argument("--conf", type=float, default=0.25,
                    help="confidence threshold (default 0.25)")
    ap.add_argument("--limit", type=int, default=0,
                    help="max images to process (0 = all)")
    ap.add_argument("--no-save", action="store_true",
                    help="print results but do not write annotated copies")
    args = ap.parse_args()

    print("=" * 64)
    print("HALOVISION IMAGE TEST")
    print("=" * 64)
    print(f"Free D: {disk_free_gb():.1f} GB")

    source = Path(args.source)
    images = collect_images(source)
    if not images:
        print(f"ERROR: no images found at {source}")
        return 1
    if args.limit:
        images = images[: args.limit]
    print(f"Source : {source} ({len(images)} image(s))")

    try:
        weights, origin = resolve_model(args.model)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    print(f"Weights: {weights} ({origin})")

    try:
        from ultralytics import YOLO
        t0 = time.time()
        model = YOLO(str(weights))
        print(f"Loaded  : {time.time() - t0:.1f}s, {len(model.names)} classes")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not load model: {e}")
        return 1

    is_base = origin == "base model (fallback)"
    if is_base:
        print()
        print("NOTE: base COCO model active — classes 0-79 (person, car,")
        print("traffic light, ...) work; HaloVision 80-94 (wheelchair,")
        print("pothole, white_cane, ...) appear only after training best.pt.")
    print()

    if not args.no_save:
        PRED_DIR.mkdir(parents=True, exist_ok=True)

    summary = {
        "model": str(weights),
        "model_origin": origin,
        "conf": args.conf,
        "source": str(source),
        "images": [],
    }
    class_totals: dict[tuple[int, str], int] = {}  # (id, name) -> count

    for i, img in enumerate(images, 1):
        try:
            res = model.predict(str(img), conf=args.conf, verbose=False)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(images)}] {img.name}: inference failed: {e}")
            continue
        r = res[0]
        names = r.names
        dets = []
        for b in r.boxes:
            cls_id = int(b.cls)
            conf = float(b.conf)
            xyxy = [round(float(x), 1) for x in b.xyxy[0].tolist()]
            dets.append({"id": cls_id, "name": names.get(cls_id, "?"),
                         "conf": round(conf, 3), "xyxy": xyxy})
        dets.sort(key=lambda d: -d["conf"])
        for d in dets:
            key = (d["id"], d["name"])
            class_totals[key] = class_totals.get(key, 0) + 1

        # annotated copy
        saved_as = None
        if not args.no_save:
            out = PRED_DIR / f"{img.stem}_pred.jpg"
            try:
                r.save(filename=str(out))
                saved_as = str(out)
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(images)}] {img.name}: save failed: {e}")

        if dets:
            shown = ", ".join(
                f"{d['name']} {d['conf']:.2f}"
                f"{'*' if d['id'] >= CUSTOM_ID_MIN else ''}" for d in dets[:8])
            extra = "" if len(dets) <= 8 else f" (+{len(dets) - 8} more)"
            print(f"[{i}/{len(images)}] {img.name}: {len(dets)} det -> {shown}{extra}")
        else:
            print(f"[{i}/{len(images)}] {img.name}: 0 detections (conf>={args.conf})")

        summary["images"].append({"file": img.name, "path": str(img),
                                  "detections": dets, "annotated": saved_as})

    print()
    print("-" * 64)
    if class_totals:
        print("Totals this run (* = HaloVision custom class 80-94):")
        for (cid, name), n in sorted(class_totals.items(), key=lambda kv: -kv[1]):
            star = " *" if cid >= CUSTOM_ID_MIN else ""
            print(f"  {name:24s} {n}{star}")
        if is_base:
            print("(no * entries: base model has no custom classes — train best.pt)")
    else:
        print("No detections this run.")

    if not args.no_save:
        out_json = PRED_DIR / "last_prediction.json"
        out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"\nAnnotated images + JSON -> {PRED_DIR}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
