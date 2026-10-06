"""
HaloVision v2 Training Script (restart rewrite — Stages 8/9).

Transfer learning from yolo26n.pt -> yolo26_halovision_v2 (95 classes).

Guarantees:
- Original YOLOv8 checkpoints (App/yolov8m.pt, root yolov8*.pt) are NEVER
  written. Base yolo26n.pt is opened read-only by ultralytics.
- All outputs go to D:/HaloVisionData (HALOVISION_DATA_DIR):
    runs/training/            ultralytics run dirs (checkpoints, curves)
    models/yolo26_halovision_v2/  best.pt, last.pt, data.yaml, metadata.json,
                                  results.csv, training_config snapshot
- Dataset validation must have PASSED first (checked here unless --skip-check
  is explicitly given; the check itself never mutates the dataset).
- Uses CUDA if available (falls back to CPU with a warning).
- Records: full hyperparameter config, class names, dataset version, source
  dataset info, ultralytics/torch versions, metrics per epoch.

Two-phase transfer learning:
  Phase 1: frozen backbone (freeze=10), higher LR head warm-up
  Phase 2: full fine-tune from phase-1 best.pt

Usage:
    python ml/training/train_halovision.py [--skip-val-check] [--phases 1|2|both]
"""

import argparse
import csv
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hv_paths import (  # noqa: E402
    DATASET_YAML, REPO_ROOT, TRAINING_CONFIG, V2_MODELS_DIR, TRAINING_RUNS,
    ORIGINAL_V8M, disk_free_gb,
)
from generate_yaml import NAMES  # noqa: E402  (single source of truth)


def load_config() -> dict:
    with open(TRAINING_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def check_validation() -> bool:
    """Run validator; do not proceed on critical errors."""
    import validate_dataset
    print("Pre-training dataset validation check...")
    ok = validate_dataset.validate_dataset(str(DATASET_YAML))
    if not ok:
        print("\nABORT: dataset validation FAILED. Fix the dataset first.")
    return ok


def snapshot_original_models() -> None:
    """Stage 13: keep a D: copy of the baseline for old-vs-new comparison."""
    from hv_paths import ORIGINAL_MODELS_DIR
    ORIGINAL_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    src = ORIGINAL_V8M
    dst = ORIGINAL_MODELS_DIR / "yolov8m_original.pt"
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
        print(f"Baselined original model -> {dst} (source untouched: {src})")


def train_phase(model_path: Path, cfg: dict, phase: int, project_dir: Path):
    from ultralytics import YOLO

    tc = cfg["training_config"]
    tl = cfg["transfer_learning"]
    is_p1 = phase == 1
    epochs = tl["phase1_epochs"] if is_p1 else tl["phase2_epochs"]
    lr = tl["phase1_lr"] if is_p1 else tl["phase2_lr"]
    freeze = tl["phase1_freeze"] if is_p1 else 0

    print(f"\n--- Phase {phase}: {epochs} epochs, lr={lr}, freeze={freeze} ---")
    model = YOLO(str(model_path))
    run_name = f"halovision_v2_phase{phase}"
    t0 = time.time()
    results = model.train(
        data=str(DATASET_YAML),
        epochs=epochs,
        batch=tc["batch"],
        imgsz=tc["imgsz"],
        lr0=lr,
        lrf=tc["lrf"],
        optimizer=tc["optimizer"],
        momentum=tc["momentum"],
        weight_decay=tc["weight_decay"],
        warmup_epochs=tc["warmup_epochs"],
        warmup_momentum=tc["warmup_momentum"],
        warmup_bias_lr=tc["warmup_bias_lr"],
        device=tc["device"],
        workers=tc["workers"],
        cos_lr=tc["cos_lr"],
        close_mosaic=tc["close_mosaic"],
        amp=tc["amp"],
        seed=tc["seed"],
        patience=tc["patience"],
        save_period=tc["save_period"],
        freeze=freeze,
        project=str(project_dir),
        name=run_name,
        exist_ok=True,
        pretrained=True,
        verbose=True,
    )
    elapsed = time.time() - t0
    run_dir = project_dir / run_name
    print(f"Phase {phase} done in {elapsed/60:.1f} min -> {run_dir}")
    return results, run_dir, elapsed


def export_results_csv(run_dir: Path, dst: Path) -> int:
    """Copy ultralytics results.csv and return epoch count."""
    src = run_dir / "results.csv"
    if not src.exists():
        print(f"WARNING: {src} missing; results.csv not written")
        return 0
    with open(src, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phase"] + [h.strip() for h in rows[0]])
        # results.csv belongs to last phase only; keep as-is with phase tag
        for r in rows[1:]:
            w.writerow(["last"] + [c.strip() for c in r])
    return max(len(rows) - 1, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-val-check", action="store_true",
                    help="skip pre-training validation (NOT recommended)")
    ap.add_argument("--phases", choices=["1", "2", "both"], default="both")
    args = ap.parse_args()

    print("=" * 64)
    print("HALOVISION YOLO26 TRAINING (Stage 9)")
    print("=" * 64)

    # --- preconditions -----------------------------------------------------
    if not DATASET_YAML.exists():
        print(f"FATAL: dataset yaml missing: {DATASET_YAML}")
        return 1
    if not args.skip_val_check:
        if not check_validation():
            return 1

    import torch
    if not torch.cuda.is_available():
        print("WARNING: CUDA not available — training will be slow on CPU")
    else:
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    free = disk_free_gb()
    print(f"Free D: space {free:.1f} GB (need ~10 GB for checkpoints)")
    if free < 10:
        print("FATAL: insufficient space on D:")
        return 1

    cfg = load_config()
    base_ckpt = REPO_ROOT / cfg["base_checkpoint"]
    if not base_ckpt.exists():
        print(f"FATAL: base checkpoint missing: {base_ckpt}")
        return 1

    # device resolution: prefer CUDA (RTX 3060 + cu128 torch installed for this
    # run); fall back to CPU only if CUDA is genuinely unavailable.
    cfg_dev = cfg["training_config"]["device"]
    if torch.cuda.is_available():
        if str(cfg_dev) == "cpu":
            print("Config says device=cpu but CUDA is available -> using GPU (0)")
        cfg["training_config"]["device"] = 0
    else:
        cfg["training_config"]["device"] = "cpu"

    snapshot_original_models()

    V2_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_RUNS.mkdir(parents=True, exist_ok=True)

    print(f"Base model:    {base_ckpt}")
    print(f"Dataset:       {DATASET_YAML}")
    print(f"Classes:       {cfg['total_classes']}")
    print(f"Output models: {V2_MODELS_DIR}")
    print(f"Run dir:       {TRAINING_RUNS}")

    start_utc = datetime.now(timezone.utc).isoformat()
    total_elapsed = 0.0
    phase_runs = {}
    current_ckpt = base_ckpt
    phase1_dir = None

    if args.phases in ("1", "both"):
        # Idempotent resume: skip phase 1 when a prior run already finished all
        # its epochs (results.csv row count) — an interrupted wrapper restart
        # must not waste ~10 h retraining a completed phase 1.
        p1_epochs = int(cfg["transfer_learning"]["phase1_epochs"])
        completed_p1 = None
        for cand in sorted(TRAINING_RUNS.glob("halovision_v2_phase1*"), reverse=True):
            rcsv = cand / "results.csv"
            if (cand / "weights" / "best.pt").exists() and rcsv.exists():
                try:
                    with open(rcsv, newline="", encoding="utf-8") as f:
                        n_rows = sum(1 for _ in csv.reader(f)) - 1
                except OSError:
                    continue
                if n_rows >= p1_epochs:
                    completed_p1 = cand
                    break
        if completed_p1 is not None:
            print(f"Phase 1 already complete ({completed_p1}) — skipping to phase 2")
            current_ckpt = completed_p1 / "weights" / "best.pt"
            phase1_dir = completed_p1
            phase_runs[1] = str(completed_p1)
        else:
            results, run_dir, elapsed = train_phase(current_ckpt, cfg, 1, TRAINING_RUNS)
            total_elapsed += elapsed
            phase_runs[1] = str(run_dir)
            best1 = run_dir / "weights" / "best.pt"
            if best1.exists():
                current_ckpt = best1
            phase1_dir = run_dir

    if args.phases == "2" and phase1_dir is None:
        # Resume: --phases 2 without a fresh phase 1 must start from the latest
        # phase-1 run's best.pt — otherwise phase 2 would silently train from
        # the base checkpoint and discard all phase-1 learning.
        for cand in sorted(TRAINING_RUNS.glob("halovision_v2_phase1*"), reverse=True):
            b = cand / "weights" / "best.pt"
            if b.exists():
                current_ckpt = b
                phase1_dir = cand
                print(f"Resume: phase 2 starts from phase-1 best -> {b}")
                break
        else:
            print(f"FATAL: --phases 2 but no phase-1 best.pt under {TRAINING_RUNS}")
            return 1

    if args.phases in ("2", "both"):
        # phase 2 continues from phase-1 best when available
        results, run_dir, elapsed = train_phase(current_ckpt, cfg, 2, TRAINING_RUNS)
        total_elapsed += elapsed
        phase_runs[2] = str(run_dir)
        final_dir = run_dir
    else:
        final_dir = phase1_dir

    # --- harvest outputs ---------------------------------------------------
    weights = final_dir / "weights"
    best = weights / "best.pt"
    last = weights / "last.pt"
    if not best.exists():
        print(f"FATAL: no best.pt produced at {best}")
        return 1

    shutil.copy2(best, V2_MODELS_DIR / "best.pt")
    if last.exists():
        shutil.copy2(last, V2_MODELS_DIR / "last.pt")
    shutil.copy2(DATASET_YAML, V2_MODELS_DIR / "data.yaml")

    n_epochs = export_results_csv(final_dir, V2_MODELS_DIR / "results.csv")

    # metrics from final results.csv (strip whitespace keys)
    metrics = {}
    results_csv = final_dir / "results.csv"
    if results_csv.exists():
        with open(results_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows:
            last_row = {k.strip(): v.strip() for k, v in rows[-1].items()}
            metrics = last_row

    import ultralytics
    metadata = {
        "model_version": "halovision_v2",
        "created_utc": start_utc,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "base_model": cfg["base_model"],
        "base_checkpoint": cfg["base_checkpoint"],
        "ultralytics_version": ultralytics.__version__,
        "torch_version": __import__("torch").__version__,
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "dataset_version": cfg["dataset_version"],
        "dataset_yaml": str(DATASET_YAML),
        "dataset_sources": {
            "coco2017": "D:/HaloVisionData/datasets/coco2017 (train/val pools)",
            "open_images_v7": "CVDF S3 mirror subset (see dataset_manifest.yaml)",
            "roboflow": "see dataset_manifest.yaml",
            "custom": "see dataset_manifest.yaml / reports",
        },
        "class_count": cfg["total_classes"],
        "class_names": {str(i): n for i, n in sorted(NAMES.items())},
        "new_class_ids": cfg["new_class_ids"],
        "training_config": cfg["training_config"],
        "transfer_learning": cfg["transfer_learning"],
        "phases_run": args.phases,
        "phase_run_dirs": phase_runs,
        "total_training_minutes": round(total_elapsed / 60, 1),
        "epochs_recorded": n_epochs,
        "final_metrics_row": metrics,
        "outputs": {
            "best": str(V2_MODELS_DIR / "best.pt"),
            "last": str(V2_MODELS_DIR / "last.pt"),
            "data_yaml": str(V2_MODELS_DIR / "data.yaml"),
            "results": str(V2_MODELS_DIR / "results.csv"),
        },
        "rollback_model": str(ORIGINAL_V8M),
        "rollback_note": "Original YOLOv8 model never modified by this run.",
    }
    (V2_MODELS_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8")

    # config snapshot alongside the model
    shutil.copy2(TRAINING_CONFIG, V2_MODELS_DIR / "training_config_snapshot.json")

    print()
    print("=" * 64)
    print("TRAINING COMPLETE")
    print(f"  best.pt : {V2_MODELS_DIR / 'best.pt'}")
    print(f"  last.pt : {V2_MODELS_DIR / 'last.pt'}")
    print(f"  results : {V2_MODELS_DIR / 'results.csv'} ({n_epochs} epochs)")
    print(f"  metadata: {V2_MODELS_DIR / 'metadata.json'}")
    print(f"  elapsed : {total_elapsed/60:.1f} min")
    print(f"  original model intact: {ORIGINAL_V8M.exists()} at {ORIGINAL_V8M}")
    print("=" * 64)
    print("Next: python ml/training/evaluate_models.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
