"""
HaloVision Stage 3b — Open Images V7 subset image downloader.

Reads D:/HaloVisionData/cache/open_images_class_map.json (from discover_open_images.py)
and downloads only the matched images from the CVDF S3 mirror:

    https://s3.amazonaws.com/open-images-dataset/{train|validation|test}/{ImageID}.jpg

Disk-space rule: reports destination free space + expected total size before
starting; skips images already present; resumes after interruption.

Caps per class (default 600 images) with deterministic ordering so reruns are
reproducible. Also pulls box coordinates for each kept image into
D:/HaloVisionData/cache/open_images_boxes.json for convert_new_classes.py.

Usage:
    python ml/training/download_open_images.py [--per-class 600] [--workers 16]
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import CACHE_DIR, OPEN_IMAGES_DIR, disk_free_gb  # noqa: E402

S3_MIRROR = "https://s3.amazonaws.com/open-images-dataset"
CLASS_MAP = CACHE_DIR / "open_images_class_map.json"
FILTERED_CSV = CACHE_DIR / "open_images_filtered.csv"
OUT_ROOT = OPEN_IMAGES_DIR / "raw"

# Rough average JPEG size in the mirror (rescaled, max 1024px)
EST_BYTES_PER_IMAGE = 150_000


def fetch(url: str, dest: Path, retries: int = 3, timeout: int = 30) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        return True
    tmp = dest.with_suffix(".part")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HaloVision-dataset/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            if tmp.stat().st_size < 1000:
                tmp.unlink(missing_ok=True)
                return False
            tmp.replace(dest)
            return True
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                return False          # image not in mirror: permanent, do not retry
            if attempt == retries - 1:
                return False
            time.sleep(1.0 * (attempt + 1))
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=600,
                    help="max images to keep per class (deterministic order)")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    print("=" * 64)
    print("OPEN IMAGES V7 SUBSET DOWNLOAD (Stage 3b)")
    print("=" * 64)

    if not CLASS_MAP.exists():
        print("FATAL: run discover_open_images.py first (class map missing)")
        return 1
    if not FILTERED_CSV.exists():
        print("FATAL: filtered annotation CSV missing")
        return 1

    meta = json.loads(CLASS_MAP.read_text(encoding="utf-8"))
    matched = {int(cid): m for cid, m in meta["classes"].items() if m["status"] == "matched"}
    id_split = meta.get("id_split", {})
    if not matched:
        print("No matched classes — nothing to download (all gaps -> Stage 4/5).")
        return 0

    # Collect boxes per image (multiple classes can share an image)
    label_to_cid = {m["label_name"]: cid for cid, m in matched.items()}
    boxes_by_image = defaultdict(list)          # ImageID -> [(cid, xmin, ymin, xmax, ymax)]
    with open(FILTERED_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = label_to_cid.get(row["LabelName"])
            if cid is None:
                continue
            boxes_by_image[row["ImageID"]].append(
                (cid, float(row["XMin"]), float(row["YMin"]),
                 float(row["XMax"]), float(row["YMax"]))
            )

    # Deterministic per-class selection: images whose boxes touch that class,
    # ordered by ImageID, capped at --per-class.
    images_for_class = defaultdict(list)
    for cid in matched:
        ids = sorted(iid for iid, boxes in boxes_by_image.items()
                     if any(b[0] == cid for b in boxes))
        images_for_class[cid] = ids[: args.per_class]

    # Union of images to download (one file can serve multiple classes)
    plan = {}                                   # ImageID -> split
    for cid in matched:
        for iid in images_for_class[cid]:
            plan[iid] = id_split.get(iid, "train")

    total = len(plan)
    est_gb = total * EST_BYTES_PER_IMAGE / 1e9
    free = disk_free_gb()
    already = sum(
        1 for iid in plan
        if (OUT_ROOT / id_split.get(iid, "train") / f"{iid}.jpg").exists()
    )
    print(f"\nPlan: {total} unique images across {len(matched)} matched classes")
    for cid in sorted(matched):
        print(f"  [{cid}] {matched[cid]['our_name']:14s}: "
              f"{len(images_for_class[cid]):5d} images "
              f"(OI class '{matched[cid]['oi_name']}')")
    print(f"Already downloaded : {already}")
    print(f"Estimated new bytes: {est_gb:.2f} GB (avg {EST_BYTES_PER_IMAGE//1000} KB/img)")
    print(f"Free space on D:   : {free:.1f} GB")
    print(f"Workers            : {args.workers}\n")

    if est_gb > free - 5:
        print("FATAL: insufficient free space (need est + 5 GB headroom)")
        return 1

    tasks = []
    for iid, split in plan.items():
        dest = OUT_ROOT / split / f"{iid}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not (dest.exists() and dest.stat().st_size > 1000):
            tasks.append((f"{S3_MIRROR}/{split}/{iid}.jpg", dest, iid))

    t0 = time.time()
    ok = 0
    fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch, u, d): iid for u, d, iid in tasks}
        for n, fut in enumerate(as_completed(futures), 1):
            if fut.result():
                ok += 1
            else:
                fail += 1
            if n % 500 == 0:
                print(f"  {n}/{len(tasks)} attempted (ok={ok} fail={fail}) "
                      f"({time.time()-t0:.0f}s)")

    # Persist box annotations for convert_new_classes.py
    kept_ids = {iid for iid in plan
                if (OUT_ROOT / id_split.get(iid, "train") / f"{iid}.jpg").exists()}
    out = {
        "images": {
            iid: {"split_hint": id_split.get(iid, "train"),
                  "boxes": boxes_by_image[iid]}
            for iid in sorted(kept_ids)
        },
        "classes": {str(cid): m for cid, m in matched.items()},
        "per_class_counts": {str(cid): sum(1 for i in images_for_class[cid] if i in kept_ids)
                             for cid in matched},
    }
    (CACHE_DIR / "open_images_boxes.json").write_text(
        json.dumps(out), encoding="utf-8")

    print()
    print("=" * 64)
    print(f"Downloaded ok : {ok}")
    print(f"Failed/missing: {fail}")
    print(f"Kept images   : {len(kept_ids)}")
    print(f"Elapsed       : {time.time()-t0:.0f}s")
    print(f"Boxes written : {CACHE_DIR / 'open_images_boxes.json'}")
    for cid in sorted(matched):
        print(f"  [{cid}] {matched[cid]['our_name']:14s}: "
              f"{out['per_class_counts'][str(cid)]} images")
    print("Next: python ml/training/convert_new_classes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
