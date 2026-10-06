"""
HaloVision shared path resolution.

Single source of truth for where large ML data lives.
Reads HALOVISION_DATA_DIR (default: D:/HaloVisionData) so the C: project
holds only code/config/metadata while datasets/models/runs stay on D:.

Usage:
    from hv_paths import DATA_DIR, DATASETS, HALOVISION_V2, ...
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Storage root
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("HALOVISION_DATA_DIR", "D:/HaloVisionData"))

DATASETS = DATA_DIR / "datasets"
COCO_DIR = DATASETS / "coco2017"
OPEN_IMAGES_DIR = DATASETS / "open_images_v7"
ROBOFLOW_DIR = DATASETS / "roboflow"
CUSTOM_DIR = DATASETS / "custom"
HALOVISION_V2 = DATASETS / "halovision_v2"

MODELS_DIR = DATA_DIR / "models"
ORIGINAL_MODELS_DIR = MODELS_DIR / "original"
V2_MODELS_DIR = MODELS_DIR / "yolo26_halovision_v2"

RUNS_DIR = DATA_DIR / "runs"
TRAINING_RUNS = RUNS_DIR / "training"
VALIDATION_RUNS = RUNS_DIR / "validation"

DOWNLOADS = DATA_DIR / "downloads"
COCO_DOWNLOADS = DOWNLOADS / "coco"
OPEN_IMAGES_DOWNLOADS = DOWNLOADS / "open_images"
ROBOFLOW_DOWNLOADS = DOWNLOADS / "roboflow"
HF_DOWNLOADS = DOWNLOADS / "hf"

# User-provided raw source exports (read-only; never modified/deleted).
EXTRACTED_ROOT = Path(r"D:\Training model\extracted files")

CACHE_DIR = DATA_DIR / "cache"

# ---------------------------------------------------------------------------
# Dataset layout (YOLO format)
# ---------------------------------------------------------------------------
SPLITS = ("train", "val", "test")

DATASET_YAML = HALOVISION_V2 / "halovision_v2.yaml"


def images_dir(split: str) -> Path:
    return HALOVISION_V2 / "images" / split


def labels_dir(split: str) -> Path:
    return HALOVISION_V2 / "labels" / split


# ---------------------------------------------------------------------------
# C: project locations (code/config only)
# ---------------------------------------------------------------------------
def project_root() -> Path:
    """Repo root, derived from this file's location (no hardcoded chdir)."""
    return Path(__file__).resolve().parents[2]


REPO_ROOT = project_root()
ML_TRAINING = REPO_ROOT / "ml" / "training"
REPO_DATASET_YAML_MIRROR = REPO_ROOT / "ml" / "training" / "datasets" / "halovision_v2" / "halovision_v2.yaml"
TRAINING_CONFIG = REPO_ROOT / "models" / "yolo26_halovision_v2" / "training_config.json"
ACTIVE_MODEL_JSON = REPO_ROOT / "models" / "active_model.json"

# Original (never overwrite) checkpoints on C:
ORIGINAL_V8M = REPO_ROOT / "App" / "yolov8m.pt"
ROOT_YOLOV8M = REPO_ROOT / "yolov8m.pt"
ROOT_YOLOV8N = REPO_ROOT / "yolov8n.pt"
BASE_YOLO26N = REPO_ROOT / "yolo26n.pt"      # transfer-learning base (read-only)
BASE_YOLO26S = REPO_ROOT / "yolo26s.pt"      # superseded by yolo26n per spec
BASE_YOLO26M = REPO_ROOT / "yolo26m.pt"
ORIGINAL_YOLO26M_BACKUP = REPO_ROOT / "models" / "original" / "yolo26m_original.pt"


def ensure_dirs() -> None:
    """Create the D: directory skeleton (idempotent)."""
    for p in (
        COCO_DIR, OPEN_IMAGES_DIR, ROBOFLOW_DIR, CUSTOM_DIR, HALOVISION_V2,
        ORIGINAL_MODELS_DIR, V2_MODELS_DIR,
        TRAINING_RUNS, VALIDATION_RUNS,
        COCO_DOWNLOADS, OPEN_IMAGES_DOWNLOADS, ROBOFLOW_DOWNLOADS,
        CACHE_DIR,
    ):
        p.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        images_dir(split).mkdir(parents=True, exist_ok=True)
        labels_dir(split).mkdir(parents=True, exist_ok=True)


def disk_free_gb(path: Path = None) -> float:
    """Free space in GB for the volume containing path."""
    import shutil
    target = Path(path or DATA_DIR)
    target.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(str(target)).free / 1024**3


if __name__ == "__main__":
    print(f"HALOVISION_DATA_DIR -> {DATA_DIR}")
    for name, p in sorted(
        ((k, v) for k, v in list(globals().items()) if isinstance(v, Path) and "DIR" in k.upper() or isinstance(v, Path) and k.isupper()),
        key=lambda kv: kv[0],
    ):
        print(f"  {name:28s} {p}  {'[exists]' if p.exists() else '[absent]'}")
    print(f"  {'FREE_SPACE_GB':28s} {disk_free_gb():.1f}")
