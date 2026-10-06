"""
HaloVision dataset deduplication (Stage 7 fix).

COCO train2017 contains the same image bytes under different file IDs.
Our deterministic test carve hashed per-filename, so identical content can
land in train AND test (leakage) or twice in train.

Policy (deterministic, reversible):
- group = identical image bytes (md5) anywhere in the dataset
- keeper: cross-split -> the copy in the earliest split (train > val > test),
  because leaking test content into train is worse than dropping a test item;
  within-split -> lexicographically smallest stem
- non-keepers are MOVED (not deleted) to
  D:/HaloVisionData/cache/dedup_quarantine/<split>/
  together with their label files, so the action is fully reversible
- every move is logged to cache/dedup_report.json

Run AFTER convert_new_classes.py and BEFORE validate_dataset.py.

Usage:
    python ml/training/dedup_dataset.py [--apply]
    (no --apply = dry run, prints the plan only)
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import CACHE_DIR, DATASET_YAML, disk_free_gb  # noqa: E402

import yaml  # noqa: E402

SPLIT_RANK = {"train": 0, "val": 1, "test": 2}
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
QUARANTINE = CACHE_DIR / "dedup_quarantine"


def main():
    apply = "--apply" in sys.argv

    with open(DATASET_YAML, encoding="utf-8") as f:
        base = Path(yaml.safe_load(f)["path"])

    print("=" * 64)
    print("DATASET DEDUPLICATION" + ("" if apply else " (DRY RUN)"))
    print("=" * 64)
    print(f"Root:     {base}")
    print(f"Free D:   {disk_free_gb():.1f} GB")

    hash_to = defaultdict(list)
    for split in ("train", "val", "test"):
        d = base / "images" / split
        if not d.exists():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in IMG_EXT:
                continue
            try:
                h = hashlib.md5(p.read_bytes()).hexdigest()
            except OSError:
                continue
            hash_to[h].append((split, p))

    groups = {h: v for h, v in hash_to.items() if len(v) > 1}
    print(f"\nScanned images: {sum(len(v) for v in hash_to.values())}")
    print(f"Duplicate groups: {len(groups)}")

    plan = []       # (split, img_path, keeper_rel)
    for h, members in sorted(groups.items(), key=lambda kv: kv[1][0][1].name):
        # keeper: earliest split; tie -> lexicographically smallest stem
        members_sorted = sorted(members, key=lambda m: (SPLIT_RANK.get(m[0], 9),
                                                        m[1].stem))
        keeper_split, keeper_img = members_sorted[0]
        keeper_rel = f"{keeper_split}/{keeper_img.name}"
        for split, img in members_sorted[1:]:
            plan.append((split, img, keeper_rel, h))

    if not plan:
        print("\nNo duplicates found — nothing to do.")
        return 0

    moved_imgs = moved_lbls = 0
    for split, img, keeper_rel, h in plan:
        lbl = base / "labels" / split / (img.stem + ".txt")
        print(f"  quarantine {split}/{img.name}"
              + (f" (+label)" if lbl.exists() else " (no label)")
              + f"  -> keeper {keeper_rel}  [{h[:12]}]")
        if apply:
            dest_dir = QUARANTINE / split
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_img = dest_dir / img.name
            if dest_img.exists():
                # never clobber an earlier quarantine entry (would lose it)
                dest_img = dest_dir / f"{h[:8]}_{img.name}"
            img.rename(dest_img)
            moved_imgs += 1
            if lbl.exists():
                lbl.rename(dest_dir / (dest_img.stem + ".txt"))
                moved_lbls += 1

    report = {
        "root": str(base),
        "mode": "applied" if apply else "dry_run",
        "groups": len(groups),
        "quarantined_images": moved_imgs if apply else len(plan),
        "quarantined_labels": moved_lbls if apply else sum(
            1 for _, i, _, _ in plan
            if (base / "labels" / i.parent.name / (i.stem + ".txt")).exists()),
        "items": [
            {"quarantined": f"{s}/{i.name}", "kept": k, "content_md5": h}
            for s, i, k, h in plan
        ],
        "note": "Files moved to cache/dedup_quarantine (reversible). "
                "Source COCO zips untouched.",
    }
    out = CACHE_DIR / ("dedup_report.json" if apply else "dedup_report_dryrun.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {out}")
    if not apply:
        print("DRY RUN — rerun with --apply to quarantine.")
    else:
        print(f"Moved {moved_imgs} images + {moved_lbls} labels to {QUARANTINE}")
        print("Next: python ml/training/validate_dataset.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
