"""
HaloVision Stage 5 — custom phone-camera data collection structure.

Creates D:/HaloVisionData/datasets/custom/<class>/{images,labels} for every
HaloVision class that still needs manual captures. Idempotent: only creates
what is missing, never deletes.

Also writes a COLLECTION_GUIDE.md per class with the annotation contract.

Usage:
    python ml/training/setup_custom_data.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import CUSTOM_DIR, ensure_dirs  # noqa: E402

CLASSES = {
    80: "wheelchair", 81: "white_cane", 82: "crutches", 83: "guide_dog",
    84: "crosswalk", 85: "curb", 86: "pothole", 87: "stairs",
    88: "escalator", 89: "elevator", 90: "door", 91: "entrance",
    92: "exit", 93: "bollard", 94: "road_barrier",
}

ANNOTATION_NOTES = {
    "white_cane": "ONLY mobility/white canes used by blind/low-vision people. "
                  "Never label sticks, umbrellas, hiking poles or walking sticks.",
    "stairs": "Whole fixed flight of steps as one box. Keep separate from "
              "escalator. Not a single step, ladder or ramp.",
    "guide_dog": "Dog wearing a harness/vest indicating guide role. Plain pet "
                 "dogs are COCO class 16 (dog).",
    "entrance": "Entrance opening/passage into a structure; distinct from door "
                "(the leaf) and exit.",
    "exit": "Egress opening or EXIT-sign-marked doorway; distinct from entrance.",
    "road_barrier": "Horizontal/temporary road barrier or gate arm; distinct "
                    "from bollard.",
}

GUIDE = """# {name} — phone-camera collection guide

- Class ID: **{cid}**
- Target: at least **50** useful images (150+ if hard to detect).
- Capture variety: different distances, angles, indoor/outdoor, daylight and
  safe low light, partial occlusion, clutter, backgrounds, object sizes.
- Save images as JPG into `images/` with unique names (e.g. `{name}_001.jpg`).
- Label in YOLO format in `labels/<same-stem>.txt`:
  `class_id cx cy w h` (normalized 0-1, class_id = **{cid}**, one object per line).
- Do NOT fabricate annotations — leave unlabeled images out of `labels/` until
  they are truly annotated; the converter will flag them.

{note}
"""


def main():
    print("=" * 64)
    print("CUSTOM DATA STRUCTURE (Stage 5)")
    print("=" * 64)
    ensure_dirs()
    created, existing = [], []
    for cid, name in CLASSES.items():
        root = CUSTOM_DIR / name
        img, lbl = root / "images", root / "labels"
        was = root.exists()
        img.mkdir(parents=True, exist_ok=True)
        lbl.mkdir(parents=True, exist_ok=True)
        guide = root / "COLLECTION_GUIDE.md"
        if not guide.exists():
            guide.write_text(
                GUIDE.format(name=name, cid=cid,
                             note=ANNOTATION_NOTES.get(name, "")),
                encoding="utf-8")
        n_img = len([p for p in img.iterdir()
                     if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")])
        n_lbl = len(list(lbl.glob("*.txt")))
        (existing if was else created).append((cid, name, n_img, n_lbl))
    print(f"\n{'class':24s} {'id':>4s} {'images':>7s} {'labels':>7s}")
    for cid, name, n_img, n_lbl in sorted(existing + created):
        flag = "" if n_img >= 50 else "  <-- NEEDS MANUAL CAPTURE"
        print(f"{name:24s} {cid:>4d} {n_img:>7d} {n_lbl:>7d}{flag}")
    print(f"\nCreated {len(created)} new class dirs, {len(existing)} already present.")
    print(f"Root: {CUSTOM_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
