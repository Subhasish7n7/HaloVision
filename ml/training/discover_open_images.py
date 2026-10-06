"""
HaloVision Stage 3a — Open Images V7 discovery & verification.

Downloads (once):
  1. class-descriptions-boxable.csv  (~11 KB)   -> verify which of our 15 classes exist
  2. oidv6-train-annotations-bbox.csv (~550 MB) -> filter rows to target LabelNames

Writes:
  D:/HaloVisionData/downloads/open_images/class-descriptions-boxable.csv
  D:/HaloVisionData/downloads/open_images/oidv6-train-annotations-bbox.csv
  D:/HaloVisionData/cache/open_images_filtered.csv      (filtered annotations)
  D:/HaloVisionData/cache/open_images_class_map.json    (class -> label_name, counts, verdict)

Semantics verification: for each of the 15 HaloVision classes we assert the
Open Images class NAME matches our definition (see ACCEPTED_MAP). Anything
uncertain (guide_dog, entrance, exit, white_cane likely absent) is rejected
=> gap -> Stage 4/5. No force-labeling.

Usage:
    python ml/training/discover_open_images.py
"""

import csv
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import OPEN_IMAGES_DOWNLOADS, CACHE_DIR  # noqa: E402

# Verified accessible 2026-09-24 (v5 object is 403-blocked, v6 works)
CLASS_DESC_URL = "https://storage.googleapis.com/openimages/v5/class-descriptions-boxable.csv"
BBOX_URL = "https://storage.googleapis.com/openimages/v6/oidv6-train-annotations-bbox.csv"
BBOX_VAL_URL = "https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv"
BBOX_TEST_URL = "https://storage.googleapis.com/openimages/v5/test-annotations-bbox.csv"
# Images fetched directly from CVDF S3 mirror by ImageID (no URL CSV needed;
# the images-with-rotation CSVs are 403-blocked):
S3_MIRROR = "https://s3.amazonaws.com/open-images-dataset"

# Our class -> acceptable Open Images class names (exact boxable names).
# A class is USED only if an exact-name match (or listed synonym) exists.
# This forces semantic verification instead of fuzzy matching.
ACCEPTED_MAP = {
    80: ("wheelchair", ["Wheelchair"]),
    81: ("white_cane", ["White cane"]),            # rarely/never boxable -> expect absent
    82: ("crutches", ["Crutch", "Crutches"]),
    83: ("guide_dog", ["Guide dog"]),              # expect absent -> custom
    84: ("crosswalk", ["Crosswalk", "Pedestrian crosswalk", "Zebra crossing"]),
    85: ("curb", ["Curb"]),                        # may be absent
    86: ("pothole", ["Pothole"]),                  # expect absent -> supplemental
    87: ("stairs", ["Stairs", "Staircase", "Stairs (structure)"]),
    88: ("escalator", ["Escalator"]),
    89: ("elevator", ["Elevator"]),
    90: ("door", ["Door"]),
    91: ("entrance", ["Entrance", "Entryway"]),    # expect absent -> custom
    92: ("exit", ["Exit sign", "Emergency exit"]),  # expect absent -> custom
    93: ("bollard", ["Bollard"]),
    94: ("road_barrier", ["Traffic barrier", "Road barrier", "Barricade", "Barrier"]),
}

# Which boxable names are DEFINITELY our meaning (listed above); none require
# redefinition. If a synonym exists but differs subtly, we still require an
# exact accepted name — nothing else is pulled.

FILTER_COLS = ("ImageID", "Source", "LabelName", "Confidence", "XMin", "XMax",
               "YMin", "YMax", "IsOccluded", "IsTruncated", "IsGroupOf",
               "IsDepiction", "IsInside")


def download(url: str, dest: Path, min_bytes: int = 100) -> bool:
    if dest.exists() and dest.stat().st_size >= min_bytes:
        print(f"  cached: {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
        return True
    print(f"  downloading: {url}")
    print(f"    -> {dest}")
    try:
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, str(tmp))
        if tmp.stat().st_size < min_bytes:
            print("    ERROR: file too small, discarding")
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(dest)
        print(f"    ok ({dest.stat().st_size/1e6:.1f} MB)")
        return True
    except Exception as e:
        print(f"    ERROR: {e}")
        return False


def main():
    print("=" * 64)
    print("OPEN IMAGES V7 DISCOVERY (Stage 3a)")
    print("=" * 64)
    OPEN_IMAGES_DOWNLOADS.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    desc_path = OPEN_IMAGES_DOWNLOADS / "class-descriptions-boxable.csv"
    bbox_path = OPEN_IMAGES_DOWNLOADS / "oidv6-train-annotations-bbox.csv"

    if not download(CLASS_DESC_URL, desc_path, min_bytes=1000):
        return 1

    # --- class verification: reverse map name -> LabelName ---
    name_to_label = {}
    with open(desc_path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) == 2:
                label_name, display = row[0], row[1]
                name_to_label[display] = label_name

    class_map = {}
    print("\n--- Class existence verification ---")
    for cid, (our_name, accepted) in ACCEPTED_MAP.items():
        found = None
        for cand in accepted:
            if cand in name_to_label:
                found = (cand, name_to_label[cand])
                break
        if found:
            class_map[cid] = {"our_name": our_name, "oi_name": found[0],
                              "label_name": found[1], "status": "matched"}
            print(f"  [{cid}] {our_name:14s} -> OI '{found[0]}' ({found[1]})  MATCH")
        else:
            # Surface case-insensitive near-misses for human review ONLY.
            # They are NOT auto-accepted (semantics must match our definition).
            token = our_name.split("_")[0]
            hints = [n for n in name_to_label if token.lower() in n.lower()]
            class_map[cid] = {"our_name": our_name, "oi_name": None,
                              "label_name": None, "status": "absent_in_oi",
                              "accepted_synonyms_tried": accepted,
                              "near_miss_hints": hints[:5]}
            print(f"  [{cid}] {our_name:14s} -> NO exact boxable class {accepted}"
                  f"  -> GAP (Stage 4/5)  hints={hints[:5]}")

    matched = {cid: m for cid, m in class_map.items() if m["status"] == "matched"}
    print(f"\nMatched: {len(matched)}/15 classes. Absent: "
          f"{[class_map[c]['our_name'] for c in class_map if c not in matched]}")

    if not matched:
        print("Nothing to filter; all classes -> Stage 4/5.")
        (CACHE_DIR / "open_images_class_map.json").write_text(json.dumps(class_map, indent=2))
        return 0

    # --- bbox CSVs: train (2.26 GB) + validation + test (small) ---
    bbox_files = []
    for url, path, minb in (
        (BBOX_URL, bbox_path, 100_000_000),
        (BBOX_VAL_URL, OPEN_IMAGES_DOWNLOADS / "validation-annotations-bbox.csv", 10_000_000),
        (BBOX_TEST_URL, OPEN_IMAGES_DOWNLOADS / "test-annotations-bbox.csv", 50_000_000),
    ):
        if not download(url, path, min_bytes=minb):
            return 1
        bbox_files.append((path, "train" if path == bbox_path else path.name.split("-")[0]))

    wanted_labels = {m["label_name"]: cid for cid, m in matched.items()}
    filtered_path = CACHE_DIR / "open_images_filtered.csv"
    counts = {cid: 0 for cid in matched}
    image_ids = {cid: set() for cid in matched}
    id_split = {}                             # ImageID -> OI split (for S3 path)
    kept_rows = []

    print("\n--- Filtering bbox annotations to target classes ---")
    for path, split_name in bbox_files:
        split_for_img = "train" if split_name == "train" else (
            "validation" if split_name.startswith("validation") else "test")
        n = 0
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                n += 1
                ln = row["LabelName"]
                if ln in wanted_labels and row.get("Confidence", "1") == "1":
                    cid = wanted_labels[ln]
                    counts[cid] += 1
                    image_ids[cid].add(row["ImageID"])
                    id_split[row["ImageID"]] = split_for_img
                    kept_rows.append(row)
                if n % 2_000_000 == 0:
                    print(f"  {path.name}: scanned {n/1e6:.0f}M rows, kept {len(kept_rows)}")
        print(f"  {path.name}: scanned {n} rows ({split_for_img})")

    with open(filtered_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FILTER_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(kept_rows)

    for cid in sorted(class_map):
        entry = class_map[cid]
        if cid in counts:
            entry["annotations"] = counts[cid]
            entry["images"] = len(image_ids[cid])
            print(f"  [{cid}] {entry['our_name']:14s}: {counts[cid]:7d} boxes / "
                  f"{len(image_ids[cid]):6d} images")

    out = {"classes": class_map,
           "filtered_csv": str(filtered_path),
           "s3_mirror": S3_MIRROR,
           "id_split": id_split,
           "image_ids": {str(cid): sorted(s) for cid, s in image_ids.items()}}
    (CACHE_DIR / "open_images_class_map.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {filtered_path}")
    print(f"Wrote {CACHE_DIR / 'open_images_class_map.json'}")
    print("Next: python ml/training/download_open_images.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
