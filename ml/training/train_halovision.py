"""
HaloVision v2 Training Script
Runs transfer learning from yolo26s pretrained weights to create yolo26_halovision_v2.

Usage:
    python ml/training/train_halovision.py

Prerequisites:
    - Dataset prepared at ml/training/datasets/halovision_v2/
    - Dataset validated with ml/training/validate_dataset.py
    - yolo26s.pt base weights downloaded
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Ensure we're in the project root
os.chdir(r'C:\Users\wwwas\OneDrive\Desktop\FullStack Halovision\HaloVision')
sys.path.insert(0, '.')

from ultralytics import YOLO


def load_training_config():
    with open('models/yolo26_halovision_v2/training_config.json') as f:
        return json.load(f)


def run_training():
    cfg = load_training_config()
    tc = cfg['training_config']
    tl = cfg['transfer_learning']

    print('=' * 60)
    print('HALOVISION YOLO26 CUSTOM MODEL TRAINING')
    print('=' * 60)
    print(f'Base model:    {cfg["base_checkpoint"]}')
    print(f'Dataset:       {cfg["dataset_yaml"]}')
    print(f'Total classes: {cfg["total_classes"]}')
    print(f'Output:        {cfg["output_dir"]}')
    print()

    # Phase 1: Train with frozen backbone
    print(f'--- Phase 1: Freeze backbone ({tl["phase1_epochs"]} epochs, lr={tl["phase1_lr"]}) ---')
    model = YOLO(cfg['base_checkpoint'])

    results_phase1 = model.train(
        data=cfg['dataset_yaml'],
        epochs=tl['phase1_epochs'],
        batch=tc['batch'],
        imgsz=tc['imgsz'],
        lr0=tl['phase1_lr'],
        freeze=10,  # Freeze backbone layers
        device=tc['device'],
        workers=tc['workers'],
        patience=tc['patience'],
        project=cfg['output_dir'],
        name='phase1',
        exist_ok=True,
        pretrained=True,
        seed=tc['seed'],
        verbose=True,
    )

    print(f'Phase 1 complete. Best fitness: {results_phase1.results_dict.get("metrics/mAP50-50(B)", "N/A")}')

    # Phase 2: Fine-tune all layers
    print(f'\n--- Phase 2: Fine-tune all layers ({tl["phase2_epochs"]} epochs, lr={tl["phase2_lr"]}) ---')
    # Load best from phase 1
    phase1_best = Path(cfg['output_dir']) / 'phase1' / 'weights' / 'best.pt'
    model2 = YOLO(str(phase1_best))

    start_time = time.time()
    results_phase2 = model2.train(
        data=cfg['dataset_yaml'],
        epochs=tl['phase2_epochs'],
        batch=tc['batch'],
        imgsz=tc['imgsz'],
        lr0=tl['phase2_lr'],
        freeze=0,  # Unfreeze all layers
        device=tc['device'],
        workers=tc['workers'],
        patience=tc['patience'],
        project=cfg['output_dir'],
        name='phase2',
        exist_ok=True,
        pretrained=False,
        seed=tc['seed'],
        verbose=True,
    )
    elapsed = time.time() - start_time

    print(f'Phase 2 complete. Best fitness: {results_phase2.results_dict.get("metrics/mAP50-50(B)", "N/A")}')
    print(f'Phase 2 elapsed time: {elapsed/60:.1f} minutes')

    # Copy best.pt to output root
    import shutil
    phase2_best = Path(cfg['output_dir']) / 'phase2' / 'weights' / 'best.pt'
    final_best = Path(cfg['output_dir']) / 'best.pt'
    if phase2_best.exists():
        shutil.copy2(phase2_best, final_best)
        print(f'\nBest model saved to: {final_best}')

    # Save training metadata
    metadata = {
        'model_version': cfg['model_version'],
        'base_model': cfg['base_model'],
        'ultralytics_version': __import__('ultralytics').__version__,
        'pytorch_version': __import__('torch').__version__,
        'training_date': datetime.now().isoformat(),
        'phase1_epochs': tl['phase1_epochs'],
        'phase2_epochs': tl['phase2_epochs'],
        'total_epochs': tl['phase1_epochs'] + tl['phase2_epochs'],
        'batch_size': tc['batch'],
        'imgsz': tc['imgsz'],
        'device': tc['device'],
        'elapsed_seconds': elapsed,
        'results_phase1': {k: str(v) for k, v in results_phase1.results_dict.items()},
        'results_phase2': {k: str(v) for k, v in results_phase2.results_dict.items()},
    }

    with open(Path(cfg['output_dir']) / 'training_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    print('\nTraining metadata saved.')
    print('=' * 60)


if __name__ == '__main__':
    run_training()
