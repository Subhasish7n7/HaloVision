"""
HaloVision Stage 6 — merge non-COCO sources into halovision_v2 (YOLO format).

Sources handled:
  1. Open Images  : D:/HaloVisionData/cache/open_images_boxes.json + raw images
  2. Roboflow     : D:/HaloVisionData/datasets/roboflow/<project>/{images,labels}
                    (YOLO labels with a data.yaml mapping local ids -> names)
  3. Custom       : D:/HaloVisionData/datasets/custom/<class_name>/{images,labels}
  4. Extracted    : D:/Training model/extracted files/<folder> (read-only user
                    COCO/YOLO exports; excluded/unrelated folders listed in
                    class_mapping.json are never ingested)

All annotations are remapped to the FROZEN 95-class IDs (80-94 for HaloVision
classes). Split policy for new-class images: deterministic 70/15/15
train/val/test by sha1(image bytes) — same content never lands in two splits,
and stems are prefixed by source to prevent COCO filename collisions.

Robustness: skips corrupt images, zero-area boxes, unknown class ids, and
malformed label lines (all logged). Existing COCO entries are never touched.

Usage:
    python ml/training/convert_new_classes.py
"""

import hashlib
import json
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import (  # noqa: E402
    CACHE_DIR, CUSTOM_DIR, EXTRACTED_ROOT, HF_DOWNLOADS, OPEN_IMAGES_DIR,
    ROBOFLOW_DIR, images_dir, labels_dir, ensure_dirs, disk_free_gb,
)

# Authoritative mapping — loaded from class_mapping.json (single source of
# truth for ids, canonical names, explicit aliases, and per-source id maps).
_CLASS_MAPPING = Path(__file__).resolve().parent / "class_mapping.json"
_M = json.loads(_CLASS_MAPPING.read_text(encoding="utf-8"))
NAMES = {int(k): v for k, v in _M["classes"].items()}      # id -> canonical name
ALIASES = {k: int(v) for k, v in _M["aliases"].items()}    # verified source label -> id
SOURCE_MAPS = {
    k: {int(lk): lv for lk, lv in v.items()}
    for k, v in _M["source_maps"].items()
}
# Raw-source folders that must never be ingested (user decisions recorded in
# class_mapping.json: excluded = wrong content, unrelated = never auto-include).
EXCLUDED_FOLDERS = set(_M.get("excluded_source_folders", []))
UNRELATED_FOLDERS = set(_M.get("unrelated_source_folders", []))

SPLIT_RATIOS = (0.70, 0.15, 0.15)   # train / val / test


def split_of(digest_hex: str) -> str:
    bucket = int(digest_hex, 16) % 10000
    if bucket < SPLIT_RATIOS[0] * 10000:
        return "train"
    if bucket < (SPLIT_RATIOS[0] + SPLIT_RATIOS[1]) * 10000:
        return "val"
    return "test"


def map_class(name: str):
    """Exact alias lookup (normalization: strip().lower()). No fuzzy matching."""
    return ALIASES.get(name.strip().lower())


def _to_float(value) -> float:
    """Coerce Roboflow-exported numbers (some ship as strings) to float.

    Returns 0.0 for anything non-numeric so the caller's sanity checks
    (<= 0 / missing dimension) reject the record instead of crashing.
    """
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def place_image(src: Path, stem_prefix: str, boxes, stats, source: str):
    """boxes: list of (class_id, cx, cy, w, h) already normalized+validated.

    Images whose annotations contain NO mapped class (e.g. RDD crack-only
    images, CDSet guide-arrow-only images) are skipped entirely: they would be
    useless empty-label copies of data we already have from COCO, and would
    bloat the dataset without adding signal.
    """
    valid_boxes = []
    for cid, cx, cy, w, h in boxes:
        # Quantize to label precision FIRST: a box of 4e-7 would pass a
        # raw >0 check but be written as 0.000000, which the validator
        # (correctly) flags as zero-area.
        cx, cy, w, h = (float(f"{v:.6f}") for v in (cx, cy, w, h))
        if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < w <= 1 and 0 < h <= 1):
            stats["bad_boxes"] += 1
            continue
        # 0-94: explicit aliases may legitimately map to COCO classes too
        # (e.g. person from the wheelchair/escalator folders); None = unmapped.
        if cid is None or not 0 <= cid <= 94:
            stats["bad_class"] += 1
            continue
        valid_boxes.append((cid, cx, cy, w, h))
    if boxes and not valid_boxes:
        stats["no_mapped_class"] += 1
        return
    if not boxes:
        stats["unlabeled_skipped"] += 1
        return

    try:
        raw = src.read_bytes()
    except OSError:
        stats["read_fail"] += 1
        return
    digest = hashlib.sha1(raw).hexdigest()
    split = split_of(digest)
    ext = src.suffix.lower() or ".jpg"
    stem = f"{stem_prefix}{src.stem}"

    dst_img = images_dir(split) / f"{stem}{ext}"
    dst_lbl = labels_dir(split) / f"{stem}.txt"

    if dst_img.exists():
        # Collision guard: same stem but different content (two source folders
        # shipping an identical filename) -> uniquify with a content-hash
        # suffix instead of silently overwriting another image's label.
        try:
            existing = hashlib.sha1(dst_img.read_bytes()).hexdigest()
        except OSError:
            existing = None
        if existing != digest:
            stem = f"{stem}_{digest[:8]}"
            dst_img = images_dir(split) / f"{stem}{ext}"
            dst_lbl = labels_dir(split) / f"{stem}.txt"

    if not dst_img.exists():
        # verify decodable before placing
        img = cv2.imread(str(src))
        if img is None:
            stats["corrupt"] += 1
            return
        shutil.copy2(src, dst_img)
    stats["images"][split] += 1

    lines = []
    for cid, cx, cy, w, h in valid_boxes:
        lines.append(f"{cid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        stats["class_counts"][cid] += 1
    dst_lbl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    stats["labels"][split] += 1
    stats["by_source"][source][split] += 1


def new_stats():
    return {"images": Counter(), "labels": Counter(), "class_counts": Counter(),
            "by_source": defaultdict(Counter), "corrupt": 0, "bad_boxes": 0,
            "bad_class": 0, "read_fail": 0, "missing_labels": 0, "orphan_labels": 0,
            "no_mapped_class": 0, "unlabeled_skipped": 0}


# ---------------------------------------------------------------------------
# Open Images
# ---------------------------------------------------------------------------
def ingest_open_images(stats):
    boxes_json = CACHE_DIR / "open_images_boxes.json"
    if not boxes_json.exists():
        print("[open_images] skipped (no open_images_boxes.json — nothing downloaded/matched)")
        return
    meta = json.loads(boxes_json.read_text(encoding="utf-8"))
    raw_root = OPEN_IMAGES_DIR / "raw"
    print(f"[open_images] {len(meta['images'])} images")
    for iid, info in meta["images"].items():
        split_hint = info.get("split_hint", "train")
        src = raw_root / split_hint / f"{iid}.jpg"
        if not src.exists():
            stats["missing_labels"] += 0
            stats["read_fail"] += 1
            continue
        boxes = [(cid, (xmin + xmax) / 2, (ymin + ymax) / 2, xmax - xmin, ymax - ymin)
                 for cid, xmin, ymin, xmax, ymax in info["boxes"]]
        place_image(src, "oi_", boxes, stats, "open_images")


# ---------------------------------------------------------------------------
# Supplemental YOLO-layout datasets under datasets/roboflow/ (Stage 4)
#
# Verified class maps (2026-09-24) — see dataset_manifest.yaml:
#   crosswalk_cdset3434: CDSet-3434 (Apache-2.0). Local 0 = crosswalk (VISUAL
#     confirm: zebra-crossing boxes), local 1 = guide arrows (road arrows ->
#     unmapped, our crosswalk class covers zebra crossings only).
#   rdd2022_road_damage: RDD_SPLIT 5-class export (CC BY-SA 4.0). Per the
#     reference 4-class CRDDC2022 export built from the SAME RDD_SPLIT files:
#     0=D00 longitudinal, 1=D10 transverse, 2=D20 alligator, 3=D40 POTHOLE,
#     4=unscored "other"/repair bucket. Only local 3 maps to our 86; cracks
#     and "other" are unmapped (geometry audit agrees: 0=tall, 1=flat,
#     2=largest area, 4=smallest). Images with no mapped box are skipped.
# ---------------------------------------------------------------------------
# The id maps live in class_mapping.json (source_maps) — that file is the
# authority; PROJECT_NOTES is display-only run metadata.
PROJECT_NOTES = {
    "crosswalk_cdset3434": "local 1 (guide arrows) unmapped",
    "rdd2022_road_damage": "local 0/1/2 cracks + 4 other unmapped",
}


def _find_label(img: Path) -> Path | None:
    """images[/sub]/x.jpg -> labels[/sub]/x.txt (segment replacement)."""
    parts = list(img.parts)
    if "images" in parts:
        parts[parts.index("images")] = "labels"
        cand = Path(*parts).with_suffix(".txt")
        if cand.exists():
            return cand
    cand = img.with_suffix(".txt")
    return cand if cand.exists() else None


# ---------------------------------------------------------------------------
# Supplemental sources (data.yaml optional; explicit verified maps above)
# ---------------------------------------------------------------------------
def ingest_roboflow(stats):
    if not ROBOFLOW_DIR.exists():
        print("[supplemental] no directory — skipped")
        return
    for proj in sorted(p for p in ROBOFLOW_DIR.iterdir() if p.is_dir()):
        local_to_our = SOURCE_MAPS.get(proj.name)
        source_note = PROJECT_NOTES.get(proj.name, "")
        if local_to_our is None:
            # generic path: project ships its own data.yaml
            yamls = list(proj.rglob("*.yaml")) + list(proj.rglob("*.yml"))
            if not yamls:
                print(f"[supplemental] {proj.name}: no data.yaml and no verified "
                      f"class map — skipped")
                continue
            cfg = yaml.safe_load(yamls[0].read_text(encoding="utf-8"))
            names = cfg.get("names", {})
            if isinstance(names, list):
                names = dict(enumerate(names))
            local_to_our, unknown = {}, []
            for k, v in names.items():
                cid = map_class(str(v))
                if cid is None:
                    unknown.append(v)
                else:
                    local_to_our[int(k)] = cid
            source_note = f"unmapped={unknown}"
        print(f"[supplemental] {proj.name}: mapped={local_to_our} "
              f"({source_note})")
        if not local_to_our:
            continue

        # image/label pairs anywhere in the project
        for img in proj.rglob("*"):
            if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            # CDSet ships an unlabeled binary-classification testset
            # (binary_testset_1770/Images) — not a YOLO source, skip by design.
            if any(p.lower().startswith("binary_testset") for p in img.parts):
                continue
            lbl = _find_label(img)
            boxes = []
            if lbl is None:
                stats["missing_labels"] += 1
            else:
                for line in lbl.read_text(errors="replace").splitlines():
                    parts = line.split()
                    if len(parts) < 5:
                        continue
                    try:
                        lid = int(parts[0])
                        cx, cy, w, h = map(float, parts[1:5])
                    except ValueError:
                        continue
                    our = local_to_our.get(lid)
                    if our is None:
                        stats["bad_class"] += 1
                        continue
                    boxes.append((our, cx, cy, w, h))
            place_image(img, "rf_", boxes, stats, f"roboflow/{proj.name}")


# ---------------------------------------------------------------------------
# Custom (per-class folders; labels optional-but-expected)
# ---------------------------------------------------------------------------
def ingest_custom(stats):
    if not CUSTOM_DIR.exists():
        print("[custom] no directory — skipped")
        return
    for cls_dir in sorted(p for p in CUSTOM_DIR.iterdir() if p.is_dir()):
        cid = map_class(cls_dir.name)
        if cid is None:
            print(f"[custom] {cls_dir.name}: not a HaloVision class — skipped")
            continue
        img_dir = cls_dir / "images"
        lbl_dir = cls_dir / "labels"
        imgs = [p for p in img_dir.rglob("*")
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")] if img_dir.exists() else []
        print(f"[custom] {cls_dir.name} (id {cid}): {len(imgs)} images")
        if len(imgs) == 0:
            continue
        for img in imgs:
            lbl = lbl_dir / (img.stem + ".txt") if lbl_dir.exists() else None
            boxes = []
            if lbl is None or not lbl.exists():
                stats["missing_labels"] += 1
            else:
                for line in lbl.read_text(errors="replace").splitlines():
                    parts = line.split()
                    if len(parts) < 5:
                        continue
                    try:
                        # custom labels may be either our fixed id or class-folder implied
                        cx, cy, w, h = map(float, parts[1:5])
                        lid = int(parts[0])
                    except ValueError:
                        continue
                    our = lid if 80 <= lid <= 94 else cid
                    boxes.append((our, cx, cy, w, h))
            place_image(img, "cu_", boxes, stats, f"custom/{cls_dir.name}")


# ---------------------------------------------------------------------------
# Extracted user folders (read-only COCO or YOLO exports at EXTRACTED_ROOT).
# Excluded/unrelated folders come from class_mapping.json — never guessed here.
# ---------------------------------------------------------------------------
def ingest_extracted(stats):
    if not EXTRACTED_ROOT.exists():
        print("[extracted] source directory missing — skipped")
        return
    for folder in sorted(p for p in EXTRACTED_ROOT.iterdir() if p.is_dir()):
        if folder.name in EXCLUDED_FOLDERS:
            print(f"[extracted] {folder.name}: excluded (user decision) — skipped")
            continue
        if folder.name in UNRELATED_FOLDERS:
            print(f"[extracted] {folder.name}: unrelated set — skipped")
            continue
        coco_files = sorted(folder.glob("*/_annotations.coco.json"))
        if coco_files:
            ingest_extracted_coco(folder, coco_files, stats)
        elif (folder / "data.yaml").exists() or any(folder.glob("*.yaml")):
            ingest_extracted_yolo(folder, stats)
        else:
            print(f"[extracted] {folder.name}: no COCO annotations and no data.yaml — skipped")


def ingest_extracted_coco(folder, json_files, stats):
    n_imgs = 0
    for jf in json_files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        cats = {c["id"]: map_class(str(c["name"])) for c in data.get("categories", [])}
        unmapped = sorted({str(c["name"]) for c in data.get("categories", [])
                           if map_class(str(c["name"])) is None})
        split_dir = jf.parent
        anns_by_img = defaultdict(list)
        for a in data.get("annotations", []):
            anns_by_img[a["image_id"]].append(a)
        for im in data.get("images", []):
            src = split_dir / im["file_name"]
            if not src.exists():
                alt = split_dir / "images" / Path(im["file_name"]).name
                src = alt if alt.exists() else src
            if not src.exists():
                stats["read_fail"] += 1
                continue
            # Roboflow COCO exports occasionally ship string numbers — coerce.
            w = _to_float(im.get("width"))
            h = _to_float(im.get("height"))
            boxes = []
            for a in anns_by_img.get(im["id"], []):
                cid = cats.get(a.get("category_id"))
                raw = a.get("bbox")
                vals = [_to_float(v) for v in raw] if isinstance(raw, (list, tuple)) else []
                if len(vals) != 4:
                    stats["bad_boxes"] += 1
                    continue
                x, y, bw, bh = vals
                if not w or not h or bw <= 0 or bh <= 0:
                    stats["bad_boxes"] += 1
                    continue
                boxes.append((cid, (x + bw / 2) / w, (y + bh / 2) / h, bw / w, bh / h))
            place_image(src, "ex_", boxes, stats, f"extracted/{folder.name}")
            n_imgs += 1
        if unmapped:
            print(f"[extracted] {folder.name}/{split_dir.name}: unmapped labels dropped: {unmapped}")
    print(f"[extracted] {folder.name}: COCO, {n_imgs} images in {len(json_files)} split(s)")


def ingest_extracted_yolo(folder, stats):
    yamls = [folder / "data.yaml"] if (folder / "data.yaml").exists() else sorted(folder.glob("*.yaml"))
    local_to_our, note = {}, ""
    if yamls:
        cfg = yaml.safe_load(yamls[0].read_text(encoding="utf-8"))
        names = cfg.get("names") or {}
        if isinstance(names, list):
            names = dict(enumerate(names))
        local_to_our = {int(k): map_class(str(v)) for k, v in names.items()}
        note = f"names={dict(names)}"
    if not any(v is not None for v in local_to_our.values()):
        sm = SOURCE_MAPS.get(folder.name)
        if sm:
            local_to_our = {int(k): v for k, v in sm.items()}
            note = "source_map (data.yaml names unmapped)"
    mapped = {k: v for k, v in local_to_our.items() if v is not None}
    print(f"[extracted] {folder.name}: YOLO mapped={mapped} ({note})")
    if not mapped:
        print(f"[extracted] {folder.name}: no mapped classes — skipped")
        return
    n_imgs = 0
    for img in sorted(folder.rglob("*")):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        lbl = _find_label(img)
        if lbl is None:
            stats["missing_labels"] += 1
            continue
        boxes = []
        for line in lbl.read_text(errors="replace").splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                lid = int(parts[0])
                cx, cy, w, h = map(float, parts[1:5])
            except ValueError:
                continue
            our = local_to_our.get(lid)
            if our is None:
                stats["bad_class"] += 1
                continue
            boxes.append((our, cx, cy, w, h))
        place_image(img, "ex_", boxes, stats, f"extracted/{folder.name}")
        n_imgs += 1
    print(f"[extracted] {folder.name}: YOLO, {n_imgs} images")


# ---------------------------------------------------------------------------
# HF sources (D:/HaloVisionData/downloads/hf/). INACTIVE until an approved
# mapping exists in class_mapping.json source_maps under the exact key below:
# no source_map entry -> the download is never touched (user decision gate).
# Re-split 70/15/15 by content hash like every other new source (place_image).
# ---------------------------------------------------------------------------
HF_DATASETS = {
    # source_map key -> (download subdir, destination stem prefix)
    "hf_rod": ("rod", "hf_rod_"),              # Abtinzandi ROD: <root>/<split>/{images,labels}
    "hf_assisteye": ("assisteye", "hf_eye_"),  # Dderedor: <root>/unified_obstacles/<split>/...
}
HF_IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _hf_split_of(rel_parts) -> str | None:
    """'train' | 'unified_obstacles/<split>' -> split; anything else -> None."""
    if rel_parts and rel_parts[0] in ("train", "valid", "test"):
        return rel_parts[0]
    if len(rel_parts) > 1 and rel_parts[0] == "unified_obstacles" and rel_parts[1] in ("train", "valid", "test"):
        return rel_parts[1]
    return None


def ingest_hf(stats):
    for key, (sub, prefix) in HF_DATASETS.items():
        local_to_our = SOURCE_MAPS.get(key)
        root = HF_DOWNLOADS / sub
        if not local_to_our:
            if root.exists():
                print(f"[hf] {key}: download present but NO approved source_map — not ingested")
            continue
        if not root.exists():
            print(f"[hf] {key}: source_map approved but download missing ({root}) — skipped")
            continue
        mapped = {int(k): v for k, v in local_to_our.items()}
        print(f"[hf] {key}: ingesting, mapped={mapped}")
        # Label index by (split, stem): ROD train labels are sharded into
        # subdirectories (train/labels/0/*.txt), so a flat path guess misses them.
        lbl_index: dict[tuple[str, str], Path] = {}
        for lp in root.rglob("*.txt"):
            rel = lp.relative_to(root)
            sp = _hf_split_of(rel.parts)
            if sp:
                lbl_index.setdefault((sp, lp.stem), lp)
        n_imgs = n_missing = 0
        for img in sorted(p for p in root.rglob("*")
                          if p.is_file() and p.suffix.lower() in HF_IMG_EXTS):
            rel = img.relative_to(root)
            sp = _hf_split_of(rel.parts)
            if not sp:
                continue
            lbl = lbl_index.get((sp, img.stem))
            if lbl is None:
                n_missing += 1
                stats["missing_labels"] += 1
                continue
            boxes = []
            for line in lbl.read_text(errors="replace").splitlines():
                parts = line.split()
                if len(parts) < 5:
                    continue
                try:
                    lid = int(parts[0])
                    cx, cy, w, h = map(float, parts[1:5])
                except ValueError:
                    stats["bad_boxes"] += 1
                    continue
                our = local_to_our.get(lid)
                if our is None:
                    stats["bad_class"] += 1
                    continue
                boxes.append((our, cx, cy, w, h))
            place_image(img, prefix, boxes, stats, key)
            n_imgs += 1
        print(f"[hf] {key}: {n_imgs} images processed, {n_missing} missing labels")


def main():
    print("=" * 64)
    print("NEW-CLASS SOURCES -> halovision_v2 (Stage 6 merge)")
    print("=" * 64)
    print(f"Free space D: {disk_free_gb():.1f} GB")
    ensure_dirs()
    stats = new_stats()
    t0 = time.time()
    ingest_open_images(stats)
    ingest_roboflow(stats)
    ingest_custom(stats)
    ingest_extracted(stats)
    ingest_hf(stats)

    print()
    print("=" * 64)
    print("MERGE SUMMARY")
    print(f"  images/split : {dict(stats['images'])}")
    print(f"  labels/split : {dict(stats['labels'])}")
    print(f"  corrupt skipped: {stats['corrupt']}  read/missing: {stats['read_fail']}")
    print(f"  bad boxes    : {stats['bad_boxes']}  bad class ids: {stats['bad_class']}")
    print(f"  images missing label file: {stats['missing_labels']}")
    print("  per source:")
    for src, counts in sorted(stats["by_source"].items()):
        print(f"    {src:40s} {dict(counts)}")
    print("  per class (instances):")
    for cid in sorted(stats["class_counts"]):
        name = NAMES.get(cid, f"?{cid}")
        print(f"    {cid:3d} {name:14s}: {stats['class_counts'][cid]}")
    missing = [f"{i}({n})" for i, n in NAMES.items() if stats["class_counts"][i] == 0]
    print(f"  classes with NO data yet: {missing}")
    print(f"  elapsed: {time.time()-t0:.0f}s")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
