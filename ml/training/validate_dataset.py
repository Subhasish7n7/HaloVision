"""
HaloVision Dataset Validation Script (restart rewrite).

Validates the YOLO-format halovision_v2 dataset before training.

Fixes vs. old script:
- NameError `line_id` -> `line_num` (old line 125 crashed on invalid class ids).
- Empty label files are VALID background images (old script counted them as
  errors, which would always fail on COCO images with no instances).
  "Image with no label file at all" remains an ERROR.
- Data root resolves from HALOVISION_DATA_DIR (no hardcoded C: path).
- Real image decode check via OpenCV (old script only checked magic bytes).
- Exit code 0 = PASS, 1 = FAIL.

Usage:
    python ml/training/validate_dataset.py [yaml_path]
"""

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import DATASET_YAML, VALIDATION_RUNS  # noqa: E402

CRITICAL_KEYS = (
    "missing_labels",       # image without label file
    "missing_images",       # label without image
    "corrupt_images",
    "invalid_class_ids",
    "zero_area_boxes",
    "invalid_format",
    "duplicates",           # same image bytes in >1 place (incl. across splits)
    "leakage",              # stem present in multiple splits
    "nc_mismatch",
    "empty_dataset",         # zero images in all splits (vacuous pass guard)
)
WARN_KEYS = ("empty_labels", "bbox_out_of_bounds", "rare_classes")


def validate_dataset(yaml_path: str, deep_decode: bool = True) -> bool:
    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # (paths above resolved before per-split scan below)

    base = Path(cfg["path"])
    nc = cfg["nc"]
    names = {int(k): v for k, v in cfg["names"].items()}
    splits = ["train", "val", "test"]

    if not base.exists():
        print(f"CRITICAL: dataset root does not exist: {base}")
        return False

    report = {
        "total_images": 0, "total_label_files": 0, "total_annotations": 0,
        "background_images": 0,
        "missing_labels": [], "missing_images": [], "corrupt_images": [],
        "invalid_class_ids": [], "bbox_out_of_bounds": [], "zero_area_boxes": [],
        "invalid_format": [], "class_distribution": Counter(),
        "images_per_split": {}, "annotations_per_split": {},
        "duplicates": [], "leakage": [], "nc_mismatch": [],
        "empty_labels": [], "rare_classes": [], "empty_dataset": [],
    }

    hash_to_paths = defaultdict(list)
    stems_by_split = defaultdict(set)

    for split in splits:
        img_dir = base / "images" / split
        lbl_dir = base / "labels" / split
        if not img_dir.exists():
            print(f'  WARN split "{split}": images dir missing (treated as empty)')
            report["images_per_split"][split] = 0
            report["annotations_per_split"][split] = 0
            continue

        images = {p.stem: p for p in img_dir.iterdir()
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp")}
        labels = {p.stem: p for p in lbl_dir.iterdir() if p.suffix == ".txt"} if lbl_dir.exists() else {}

        report["images_per_split"][split] = len(images)
        report["annotations_per_split"][split] = len(labels)
        report["total_images"] += len(images)
        report["total_label_files"] += len(labels)
        stems_by_split[split] = set(images)

        for stem, img_path in images.items():
            # duplicate detection (cross-split leakage + intra-split duplicates)
            try:
                h = hashlib.md5(img_path.read_bytes()).hexdigest()
            except Exception as e:
                report["corrupt_images"].append(f"{img_path}: unreadable: {e}")
                continue
            hash_to_paths[h].append((split, img_path))

            # image integrity: decode
            if deep_decode:
                img = cv2.imread(str(img_path))
                if img is None:
                    report["corrupt_images"].append(str(img_path))
                    continue

            if stem not in labels:
                report["missing_labels"].append(str(img_path))
                continue

            lbl_path = labels[stem]
            content = lbl_path.read_text(errors="replace").strip()
            if not content:
                # Valid YOLO background image (no objects) — warning only
                report["empty_labels"].append(str(lbl_path))
                report["background_images"] += 1
                continue

            for line_num, line in enumerate(content.split("\n"), 1):
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 5:
                    report["invalid_format"].append(f"{lbl_path}:{line_num}: <5 values")
                    continue
                try:
                    class_id = int(parts[0])
                    cx, cy, w, h = (float(parts[1]), float(parts[2]),
                                    float(parts[3]), float(parts[4]))
                except ValueError:
                    report["invalid_format"].append(f"{lbl_path}:{line_num}: non-numeric")
                    continue

                report["total_annotations"] += 1
                report["class_distribution"][class_id] += 1

                if class_id < 0 or class_id >= nc:
                    report["invalid_class_ids"].append(
                        f"{lbl_path}:{line_num}: class_id {class_id} not in [0,{nc-1}]")
                    report["nc_mismatch"].append(str(lbl_path))
                if w <= 0 or h <= 0:
                    report["zero_area_boxes"].append(f"{lbl_path}:{line_num}: w={w} h={h}")
                if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < w <= 1 and 0 < h <= 1):
                    report["bbox_out_of_bounds"].append(
                        f"{lbl_path}:{line_num}: ({cx:.3f},{cy:.3f},{w:.3f},{h:.3f})")

        for stem, lbl_path in labels.items():
            if stem not in images:
                report["missing_images"].append(str(lbl_path))

    # duplicates by content hash
    for h, paths in hash_to_paths.items():
        if len(paths) > 1:
            report["duplicates"].append(" | ".join(str(p) for _, p in paths))

    # stem leakage across splits
    for i, s1 in enumerate(splits):
        for s2 in splits[i + 1:]:
            for stem in stems_by_split[s1] & stems_by_split[s2]:
                report["leakage"].append(f"{stem}: {s1}+{s2}")

    # rare classes
    for cid, count in report["class_distribution"].items():
        if count < 10:
            report["rare_classes"].append(f"{cid} ({names.get(cid, '?')}): {count}")

    missing_class_ids = sorted(set(range(nc)) - set(report["class_distribution"]))
    if report["total_images"] == 0:
        report["empty_dataset"].append("no images found in any split")

    # ---------------- report ----------------
    print()
    print("=" * 64)
    print("DATASET VALIDATION REPORT")
    print("=" * 64)
    print(f"Dataset:  {yaml_path}")
    print(f"Root:     {base}")
    print(f"Classes:  {nc}")
    print()
    print("--- Summary ---")
    print(f"Total images:        {report['total_images']}")
    print(f"Total label files:   {report['total_label_files']}")
    print(f"Total annotations:   {report['total_annotations']}")
    print(f"Background (empty):  {report['background_images']}  (valid, no objects)")
    print()
    print("--- Per-Split ---")
    for split in splits:
        print(f"  {split:5s}: {report['images_per_split'].get(split, 0):7d} images, "
              f"{report['annotations_per_split'].get(split, 0):7d} label files")
    print()
    print("--- Critical Errors ---")
    has_critical = False
    for key in CRITICAL_KEYS:
        items = report[key]
        if items:
            has_critical = True
            print(f"  {key}: {len(items)}")
            for item in items[:5]:
                print(f"    - {item}")
            if len(items) > 5:
                print(f"    ... and {len(items)-5} more")
        else:
            print(f"  {key}: 0")
    print()
    print("--- Warnings (non-blocking) ---")
    for key in WARN_KEYS:
        items = report[key]
        print(f"  {key}: {len(items)}")
        for item in items[:3]:
            print(f"    - {item}")
    if missing_class_ids:
        print(f"  classes with 0 annotations: {missing_class_ids}")
        print(f"    ({', '.join(names.get(c, '?') for c in missing_class_ids)})")
    print()
    print("--- Class Distribution ---")
    for cid in sorted(report["class_distribution"]):
        print(f"  {cid:3d} ({names.get(cid, f'UNKNOWN_{cid}'):20s}): "
              f"{report['class_distribution'][cid]:7d}")
    print()
    print("--- Train/Val/Test Leakage ---")
    print(f"  cross-split duplicate stems: {len(report['leakage'])}")
    print(f"  duplicate content hashes:    {len(report['duplicates'])}")
    print()

    # Full machine-readable report (complete item lists — the console only
    # shows the first 5/3 entries). Artifact for the final report.
    report["pass"] = not has_critical
    report["dataset_yaml"] = str(yaml_path)
    out_json = VALIDATION_RUNS / "dataset_validation_report.json"
    try:
        VALIDATION_RUNS.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, indent=2, default=str) + "\n",
                            encoding="utf-8")
        print(f"Full report: {out_json}")
    except OSError as e:
        print(f"WARNING: could not write report JSON: {e}")

    if has_critical:
        print("VALIDATION: FAILED (critical errors found)")
    else:
        print("VALIDATION: PASSED")
    print("=" * 64)
    return not has_critical


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(DATASET_YAML)
    ok = validate_dataset(path)
    sys.exit(0 if ok else 1)
