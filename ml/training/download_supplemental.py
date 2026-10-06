"""
HaloVision Stage 4 — supplemental dataset downloader (account-free sources).

Downloads verified gap-class datasets from Hugging Face (no login required):

  1. zzd0225/crosswalk-detection-dataset  (CDSet-3434, Apache-2.0)
     -> class 84 crosswalk. Vehicle-camera zebra-crossing images, YOLO-style
        bbox labels (two classes: crosswalk, guide arrows -> we keep crosswalk).
     https://huggingface.co/datasets/zzd0225/crosswalk-detection-dataset

  2. akiii1234/RoadDamageDetection        (RDD2022-derived, CC BY-SA 4.0)
     -> class 86 pothole (RDD class D40 = pothole). Other RDD damage classes
        (D00/D10/D20 cracks) are NOT mapped -> images with no mapped class are
        skipped to avoid bloating the dataset.
     https://huggingface.co/datasets/akiii1234/RoadDamageDetection

Rejected candidates (recorded in dataset_manifest.yaml):
  - mabughali/miia-pothole-*   : classification labels only (no bounding boxes)
  - Nielbagz/Bollard           : empty repository (0 bytes)
  - kjunh/GuideDog             : image-to-text VQA (CC-BY-NC), no boxes
  - keremberke/pothole-segmentation : 90 images, segmentation masks only

Disk-space rule: reports D: free space + exact remote sizes before download;
skips complete files (size match); supports resume via HTTP Range.

Usage:
    python ml/training/download_supplemental.py
"""

import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import ROBOFLOW_DIR, ROBOFLOW_DOWNLOADS, disk_free_gb  # noqa: E402

DATASETS = [
    {
        "name": "crosswalk_cdset3434",
        "url": "https://huggingface.co/datasets/zzd0225/crosswalk-detection-dataset/resolve/main/CDSet.zip",
        "dest": ROBOFLOW_DOWNLOADS / "crosswalk_cdset3434" / "CDSet.zip",
        "extract_to": ROBOFLOW_DIR / "crosswalk_cdset3434",
        "license": "Apache-2.0",
        "source": "https://huggingface.co/datasets/zzd0225/crosswalk-detection-dataset (Zenodo DOI 10.5281/zenodo.8289874)",
        "classes_kept": {"crosswalk": 84},     # guide-arrow class NOT mapped
        "expected_bytes": 3_304_400_079,
    },
    {
        "name": "rdd2022_road_damage",
        "url": "https://huggingface.co/datasets/akiii1234/RoadDamageDetection/resolve/main/road_damage_dataset.zip",
        "dest": ROBOFLOW_DOWNLOADS / "rdd2022_road_damage" / "road_damage_dataset.zip",
        "extract_to": ROBOFLOW_DIR / "rdd2022_road_damage",
        "license": "CC BY-SA 4.0",
        "source": "https://huggingface.co/datasets/akiii1234/RoadDamageDetection (derived from RDD2022 / CRDDC 2022)",
        "classes_kept": {"D40": 86, "pothole": 86},   # cracks (D00/D10/D20) unmapped
        "expected_bytes": 8_974_467_909,
    },
]


def head_size(url: str) -> int | None:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            clen = r.headers.get("Content-Length")
            # HF resolve may redirect; final length is what we want
            return int(clen) if clen else None
    except Exception:
        return None


def download(url: str, dest: Path) -> bool:
    expected = head_size(url)
    if dest.exists():
        have = dest.stat().st_size
        if expected and have >= expected * 0.999:
            print(f"  complete already: {dest.name} ({have/1e9:.2f} GB)")
            return True
        if expected is None and have > 0:
            # cannot verify size; assume complete if >= our recorded expectation
            print(f"  present (size unverifiable): {dest.name} ({have/1e9:.2f} GB)")
            return True
        print(f"  partial: {dest.name} {have/1e9:.2f}/{(expected or 0)/1e9:.2f} GB -> resuming")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    mode = "ab" if tmp.exists() else "wb"
    have = tmp.stat().st_size if tmp.exists() else 0
    headers = {"User-Agent": "HaloVision-dataset/1.0"}
    if have:
        headers["Range"] = f"bytes={have}-"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, mode) as f:
            if mode == "ab" and r.status != 206:
                # server ignored range -> restart
                f.close()
                tmp.unlink(missing_ok=True)
                return download(url, dest)
            total = expected or (have + int(r.headers.get("Content-Length") or 0))
            n = have
            last = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                n += len(chunk)
                if n - last >= 1 << 28:      # print every 256 MB
                    print(f"    {n/1e9:.2f}/{total/1e9:.2f} GB ({100*n/total:.0f}%)")
                    last = n
        if tmp.stat().st_size < 1_000_000:
            print("  ERROR: file too small after download, discarding")
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(dest)
        print(f"  ok: {dest.name} ({dest.stat().st_size/1e9:.2f} GB)")
        return True
    except Exception as e:
        print(f"  download interrupted ({e}); partial kept at {tmp} for resume")
        return False


def extract(ds: dict) -> bool:
    import zipfile
    dest, target = ds["dest"], ds["extract_to"]
    if not dest.exists():
        return False
    marker = target / ".extracted"
    if marker.exists():
        print(f"  extracted already: {target}")
        return True
    target.mkdir(parents=True, exist_ok=True)
    print(f"  extracting {dest.name} -> {target} ...")
    try:
        with zipfile.ZipFile(dest) as z:
            bad = z.testzip()
            if bad:
                print(f"  ERROR: corrupt member {bad}")
                return False
            z.extractall(target)
        marker.write_text(f"source={dest.name}\n", encoding="utf-8")
        print("  extraction ok")
        return True
    except Exception as e:
        print(f"  extraction FAILED: {e}")
        return False


def main():
    print("=" * 64)
    print("SUPPLEMENTAL DATASET DOWNLOAD (Stage 4)")
    print("=" * 64)
    need = sum(d["expected_bytes"] for d in DATASETS) / 1e9
    free = disk_free_gb()
    print(f"Datasets: {', '.join(d['name'] for d in DATASETS)}")
    print(f"Expected download: {need:.1f} GB (+ ~{need:.1f} GB extracted)")
    print(f"Free space on D:  {free:.1f} GB")
    for d in DATASETS:
        print(f"  {d['name']:24s} license={d['license']:14s} partial={d['dest'].exists()}")
    print()
    if free < need * 2 + 5:
        print("FATAL: insufficient free space (need download+extract+5GB headroom)")
        return 1

    ok = True
    for d in DATASETS:
        print(f"--- {d['name']} ({d['license']}) ---")
        print(f"    {d['source']}")
        if not download(d["url"], d["dest"]):
            ok = False
            continue
        if not extract(d):
            ok = False

    print()
    print("=" * 64)
    print(f"{'COMPLETE' if ok else 'INCOMPLETE (rerun to resume)'}")
    print("Next: python ml/training/convert_new_classes.py")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
