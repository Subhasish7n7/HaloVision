"""Quarantine label+image pairs whose labels contain ONLY invalid (zero-area)
annotations — derived-data cleanup, reversible (files are MOVED, never deleted).

Input: runs/validation/dataset_validation_report.json (full report from
validate_dataset.py, which uses the exact same w<=0 / h<=0 check).

Safety:
  * a label that contains ANY valid line is NOT moved (reported instead) —
    legitimate annotations are never thrown away.
  * image+label moved together to keep the dataset pair-consistent.
  * destination: <CACHE>/zero_area_quarantine/<split>/ (never D:\ source data).

Usage: python quarantine_zero_area.py [--dry-run]
Exit: 0 = nothing to do / all moved; 1 = skipped files need review.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import CACHE_DIR, VALIDATION_RUNS  # noqa: E402

REPORT = VALIDATION_RUNS / "dataset_validation_report.json"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
DRY = "--dry-run" in sys.argv


def label_state(path: Path) -> tuple[list[str], int]:
    """Return (bad_lines, valid_line_count)."""
    bad, valid = [], 0
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            w, h = float(parts[3]), float(parts[4])
        except ValueError:
            continue
        if w <= 0 or h <= 0:
            bad.append(f"line {n}: cls={parts[0]} w={w} h={h}")
        else:
            valid += 1
    return bad, valid


def main() -> int:
    if not REPORT.exists():
        print(f"ERROR: report not found: {REPORT}")
        return 1
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    label_paths = sorted({item.rsplit(": ", 1)[0].rsplit(":", 1)[0]
                          for item in report.get("zero_area_boxes", [])})
    print(f"zero-area label files in report: {len(label_paths)}")

    quarantine_root = CACHE_DIR / "zero_area_quarantine"
    moved = skipped_valid = missing_img = errors = 0
    for lp in label_paths:
        lbl = Path(lp)
        if not lbl.exists():
            print(f"  MISSING label: {lp}")
            errors += 1
            continue
        bad, valid = label_state(lbl)
        if not bad:
            print(f"  clean now (no bad lines): {lbl.name}")
            continue
        if valid:
            # contains legitimate annotations — DO NOT quarantine, needs review
            print(f"  REVIEW: {lbl.name} has {valid} valid + {len(bad)} bad lines — NOT moved")
            skipped_valid += 1
            continue
        img_dir = lbl.parent.parent.parent / "images" / lbl.parent.name
        img = next((img_dir / (lbl.stem + e) for e in IMG_EXTS
                    if (img_dir / (lbl.stem + e)).exists()), None)
        if img is None:
            print(f"  REVIEW: {lbl.name} has no matching image — label only? NOT moved")
            errors += 1
            continue
        dest_dir = quarantine_root / lbl.parent.name
        if DRY:
            print(f"  DRY would move: {img.name} + {lbl.name} -> {dest_dir}")
            moved += 1
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(img), str(dest_dir / img.name))
        shutil.move(str(lbl), str(dest_dir / lbl.name))
        moved += 1
        print(f"  moved: {lbl.parent.name}/{img.name} + {lbl.name}")

    print()
    print(f"{'DRY-RUN ' if DRY else ''}quarantine summary: moved={moved} "
          f"review_skipped={skipped_valid} missing_image={errors} "
          f"-> {quarantine_root}")
    return 1 if (skipped_valid or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
