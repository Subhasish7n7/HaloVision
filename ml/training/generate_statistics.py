"""
HaloVision dataset statistics (Phase 8).

Single pass over halovision_v2 producing machine-readable + human-readable
statistics for the FINAL merged dataset:

- per-split images / label files / annotations / background images
- per-class instance AND image counts (all 95 classes; zeros shown explicitly)
- source breakdown via stem prefix (coco2017 | oi_ | rf_ | cu_ | ex_ | hf_)
- box-size distribution (relative area buckets, documented thresholds)
- gap-class confirmation (classes with 0 instances)

Outputs:
  <runs>/validation/dataset_statistics.json
  <runs>/validation/dataset_statistics.md
  (console summary)

Usage:
    python ml/training/generate_statistics.py
"""

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import DATASET_YAML, VALIDATION_RUNS, disk_free_gb  # noqa: E402

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# Relative box area (w*h of normalized YOLO box = fraction of image area)
SIZE_BUCKETS = (
    ("tiny", 0.0, 0.01),
    ("small", 0.01, 0.05),
    ("medium", 0.05, 0.25),
    ("large", 0.25, 1.01),
)

SOURCE_PREFIXES = (("ex_", "extracted_folders"), ("hf_", "huggingface"),
                   ("oi_", "open_images"), ("rf_", "roboflow_supplemental"),
                   ("cu_", "custom"))


def source_of(stem: str) -> str:
    for prefix, name in SOURCE_PREFIXES:
        if stem.startswith(prefix):
            return name
    if stem.isdigit():
        return "coco2017"
    return "other"


def main():
    t0 = time.time()
    with open(DATASET_YAML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    base = Path(cfg["path"])
    names = {int(k): v for k, v in cfg["names"].items()}
    nc = cfg["nc"]

    print("=" * 64)
    print("DATASET STATISTICS")
    print("=" * 64)
    print(f"Root:   {base}")
    print(f"Free D: {disk_free_gb():.1f} GB")

    splits = ["train", "val", "test"]
    stats = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_yaml": str(DATASET_YAML),
        "root": str(base),
        "nc": nc,
        "splits": {},
        "classes": {},
        "sources": defaultdict(lambda: {"images": 0, "annotations": 0}),
        "box_sizes": Counter(),
        "totals": {"images": 0, "label_files": 0, "annotations": 0,
                   "background_images": 0},
    }
    class_inst = Counter()          # instances per class id
    class_imgs = Counter()          # images containing >=1 box of class id
    class_split_inst = defaultdict(Counter)
    class_split_imgs = defaultdict(Counter)

    for split in splits:
        img_dir = base / "images" / split
        lbl_dir = base / "labels" / split
        images = ([p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXT]
                  if img_dir.exists() else [])
        labels = ([p for p in lbl_dir.iterdir() if p.suffix == ".txt"]
                  if lbl_dir.exists() else [])

        n_ann = n_bg = 0
        for lbl in labels:
            content = lbl.read_text(errors="replace").strip()
            if not content:
                n_bg += 1
                continue
            seen_here = set()
            for line in content.splitlines():
                parts = line.split()
                if len(parts) < 5:
                    continue
                try:
                    cid = int(parts[0])
                    w, h = float(parts[3]), float(parts[4])
                except ValueError:
                    continue
                n_ann += 1
                class_inst[cid] += 1
                class_split_inst[cid][split] += 1
                seen_here.add(cid)
                area = w * h
                for bname, lo, hi in SIZE_BUCKETS:
                    if lo <= area < hi:
                        stats["box_sizes"][bname] += 1
                        break
            for cid in seen_here:
                class_imgs[cid] += 1
                class_split_imgs[cid][split] += 1

        for img in images:
            stats["sources"][source_of(img.stem)]["images"] += 1
        for lbl in labels:
            stats["sources"][source_of(lbl.stem)]["annotations"] += sum(
                1 for line in lbl.read_text(errors="replace").splitlines()
                if len(line.split()) >= 5)

        stats["splits"][split] = {
            "images": len(images),
            "label_files": len(labels),
            "annotations": n_ann,
            "background_images": n_bg,
        }
        stats["totals"]["images"] += len(images)
        stats["totals"]["label_files"] += len(labels)
        stats["totals"]["annotations"] += n_ann
        stats["totals"]["background_images"] += n_bg
        print(f"  {split:5s}: {len(images):7d} images  {len(labels):7d} labels  "
              f"{n_ann:8d} annotations  ({n_bg} background)")

    for cid in range(nc):
        stats["classes"][str(cid)] = {
            "name": names.get(cid, f"UNKNOWN_{cid}"),
            "instances": class_inst[cid],
            "images": class_imgs[cid],
            "per_split_instances": dict(class_split_inst[cid]),
        }

    stats["gap_classes"] = sorted(
        cid for cid in range(nc) if class_inst[cid] == 0)
    stats["box_sizes"] = dict(stats["box_sizes"])
    stats["sources"] = {k: v for k, v in sorted(stats["sources"].items())}
    stats["elapsed_sec"] = round(time.time() - t0, 1)

    # ---------------- write outputs ----------------
    VALIDATION_RUNS.mkdir(parents=True, exist_ok=True)
    json_path = VALIDATION_RUNS / "dataset_statistics.json"
    md_path = VALIDATION_RUNS / "dataset_statistics.md"
    json_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    md = ["# HaloVision halovision_v2 — dataset statistics", "",
          f"Generated: {stats['generated']}  |  root: `{base}`", "",
          "## Splits", "",
          "| split | images | label files | annotations | background |",
          "|---|---:|---:|---:|---:|"]
    for s in splits:
        r = stats["splits"][s]
        md.append(f"| {s} | {r['images']} | {r['label_files']} | "
                  f"{r['annotations']} | {r['background_images']} |")
    md += ["", "## Sources (image files)", "",
           "| source | images | annotations |", "|---|---:|---:|"]
    for src, r in stats["sources"].items():
        md.append(f"| {src} | {r['images']} | {r['annotations']} |")
    md += ["", "## Classes (95)", "",
           "| id | name | instances | images | train/val/test inst. |",
           "|---:|---|---:|---:|---|"]
    for cid in range(nc):
        c = stats["classes"][str(cid)]
        ps = c["per_split_instances"]
        md.append(f"| {cid} | {c['name']} | {c['instances']} | {c['images']} | "
                  f"{ps.get('train', 0)}/{ps.get('val', 0)}/{ps.get('test', 0)} |")
    md += ["", f"**Gap classes (0 instances):** {stats['gap_classes']}", "",
           "## Box sizes (relative area)", "",
           "| bucket | area range | boxes |", "|---|---|---:|"]
    for bname, lo, hi in SIZE_BUCKETS:
        md.append(f"| {bname} | [{lo}, {hi}) | {stats['box_sizes'].get(bname, 0)} |")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print()
    print(f"gap classes (0 instances): {stats['gap_classes']}")
    print(f"box sizes: {dict(stats['box_sizes'])}")
    print(f"sources:   { {k: v['images'] for k, v in stats['sources'].items()} }")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"elapsed: {stats['elapsed_sec']}s")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
