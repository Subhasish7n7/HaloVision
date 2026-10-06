"""
HaloVision v2 - COCO 2017 -> YOLO converter (restart rewrite).

- Reads extracted COCO from D:/HaloVisionData/datasets/coco2017 (HALOVISION_DATA_DIR aware).
- Writes YOLO images/labels for train|val|test into D:/HaloVisionData/datasets/halovision_v2.
- Class mapping: sorted(COCO categories by id) -> 0..79 (FROZEN; verified 2026-09-24).
- Splits:
    val  = 100% of val2017            (standard COCO val, basis for old-vs-new comparison)
    test = deterministic 5% of train2017 (md5-of-filename seeding; never trained on)
    train= remaining 95% of train2017
- Background images (no annotations) get an EMPTY label file (valid YOLO).
- Resumable: skips image/label pairs already present with correct content.
- Never writes to C: project model files.

Usage:
    python ml/training/convert_coco.py [--limit N] [--force]
"""

import argparse
import hashlib
import json
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import (  # noqa: E402
    COCO_DIR, HALOVISION_V2, images_dir, labels_dir, ensure_dirs, disk_free_gb,
)

TEST_FRACTION = 0.05
TEST_SEED = "halovision_v2_test_carve"    # deterministic; hash(filename) decides test carve


def build_category_map(coco: dict) -> dict:
    """COCO category_id -> YOLO class index 0..79 via sorted-by-id order."""
    cats = sorted(coco["categories"], key=lambda c: c["id"])
    if len(cats) != 80:
        raise RuntimeError(f"Expected 80 COCO categories, found {len(cats)}")
    return {c["id"]: i for i, c in enumerate(cats)}


def coco_bbox_to_yolo(bbox, img_w, img_h):
    x, y, w, h = bbox
    cx, cy = x + w / 2, y + h / 2
    cx, w = cx / img_w, w / img_w
    cy, h = cy / img_h, h / img_h
    # Clamp into [0,1] (COCO boxes may hang slightly off-frame)
    cx = min(max(cx, 0.0), 1.0)
    cy = min(max(cy, 0.0), 1.0)
    w = min(max(w, 0.0), 1.0)
    h = min(max(h, 0.0), 1.0)
    return cx, cy, w, h


def goes_to_test(filename: str) -> bool:
    h = hashlib.sha1(f"{TEST_SEED}:{filename}".encode()).hexdigest()
    return (int(h, 16) % 10000) < int(TEST_FRACTION * 10000)


def process_split(pool: str, ann_file: Path, src_images: Path, force: bool, limit=None):
    """Convert one COCO split pool. pool in {'train','val'}."""
    t0 = time.time()
    print(f"--- pool={pool} ({ann_file.name}) ---")

    coco = json.loads(ann_file.read_text(encoding="utf-8"))
    cat_map = build_category_map(coco)
    images = {img["id"]: img for img in coco["images"]}

    anns_by_image = defaultdict(list)
    crowd_skipped = 0
    for ann in coco["annotations"]:
        if ann.get("iscrowd", 0):
            crowd_skipped += 1
            continue
        if ann["image_id"] not in images or ann["category_id"] not in cat_map:
            continue
        anns_by_image[ann["image_id"]].append((cat_map[ann["category_id"]], ann["bbox"]))

    stats = {"train": 0, "val": 0, "test": 0, "missing_src": 0, "labels_written": 0,
             "images_copied": 0, "skipped_existing": 0, "annos": 0}

    for n, (img_id, info) in enumerate(images.items()):
        if limit and n >= limit:
            print(f"  --limit {limit} reached")
            break
        fname = info["file_name"]
        w, h = info["width"], info["height"]
        src = src_images / fname
        if not src.exists():
            stats["missing_src"] += 1
            continue

        split = "val" if pool == "val" else ("test" if goes_to_test(fname) else "train")
        dst_img = images_dir(split) / fname
        dst_lbl = labels_dir(split) / (Path(fname).stem + ".txt")

        # Build label content
        lines = []
        for cls_id, bbox in anns_by_image.get(img_id, []):
            cx, cy, bw, bh = coco_bbox_to_yolo(bbox, w, h)
            if bw <= 0 or bh <= 0:
                continue
            lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        content = "\n".join(lines) + ("\n" if lines else "")

        # Copy image if needed
        if force or not dst_img.exists():
            shutil.copy2(src, dst_img)
            stats["images_copied"] += 1
        else:
            stats["skipped_existing"] += 1

        # Write label if missing/stale
        if force or not dst_lbl.exists() or dst_lbl.read_text() != content:
            dst_lbl.write_text(content)
            stats["labels_written"] += 1

        stats[split] += 1
        stats["annos"] += len(lines)

        if (n + 1) % 20000 == 0:
            print(f"  {n+1}/{len(images)} images ({time.time()-t0:.0f}s)")

    print(f"  -> {stats}")
    print(f"  crowd annotations skipped: {crowd_skipped}")
    return stats


def main():
    t_start = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="convert only first N images per pool (smoke test)")
    ap.add_argument("--force", action="store_true", help="re-copy/re-write even if present")
    args = ap.parse_args()

    print("=" * 60)
    print("COCO 2017 -> YOLO CONVERSION (halovision_v2)")
    print("=" * 60)
    print(f"COCO source : {COCO_DIR}")
    print(f"Output      : {HALOVISION_V2}")
    print(f"Free space  : {disk_free_gb():.1f} GB")
    print(f"Test carve  : {TEST_FRACTION:.0%} of train2017 (deterministic)")
    print()

    ensure_dirs()

    ann_train = COCO_DIR / "annotations" / "instances_train2017.json"
    ann_val = COCO_DIR / "annotations" / "instances_val2017.json"
    src_train = COCO_DIR / "train2017"
    src_val = COCO_DIR / "val2017"

    for p in (ann_train, ann_val, src_train, src_val):
        if not p.exists():
            print(f"MISSING: {p}")
            return 1

    s_train = process_split("train", ann_train, src_train, args.force, args.limit)
    s_val = process_split("val", ann_val, src_val, args.force, args.limit)

    print()
    print("=" * 60)
    print("CONVERSION SUMMARY")
    print(f"  train images : {s_train['train'] + s_train['test'] if False else s_train['train']}")
    print(f"  test  images : {s_train['test']}")
    print(f"  val   images : {s_val['val']}")
    print(f"  annotations  : {s_train['annos'] + s_val['annos']}")
    print(f"  missing src  : {s_train['missing_src'] + s_val['missing_src']}")
    print(f"  elapsed      : {time.time() - t_start:.0f}s")
    print("=" * 60)
    print("Next: python ml/training/validate_dataset.py <dataset_yaml>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
