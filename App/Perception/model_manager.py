"""
HaloVision Model Manager
Handles loading, switching, and rollback of YOLO models.

Usage:
    from App.Perception.model_manager import ModelManager
    mm = ModelManager()
    model = mm.load_active_model()  # Returns YOLO instance
    mm.switch_to("yolo26_halovision_v2")
    mm.switch_to("original")  # Rollback
"""

import json
import os
from pathlib import Path
from typing import Optional

from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / 'models'
ACTIVE_MODEL_PATH = MODELS_DIR / 'active_model.json'


class ModelManager:
    def __init__(self):
        self._active_config = self._load_config()

    def _load_config(self) -> dict:
        if ACTIVE_MODEL_PATH.exists():
            with open(ACTIVE_MODEL_PATH) as f:
                return json.load(f)
        return {
            'active_model': 'yolo26m',
            'checkpoint': 'yolo26m.pt',
            'fallback_model': 'yolo26m',
            'fallback_checkpoint': 'yolo26m.pt',
        }

    def _save_config(self, config: dict):
        with open(ACTIVE_MODEL_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        self._active_config = config

    def load_active_model(self) -> YOLO:
        checkpoint = self._active_config.get('checkpoint', 'yolo26m.pt')
        full_path = PROJECT_ROOT / checkpoint
        if not full_path.exists():
            print(f'WARNING: Active checkpoint not found: {full_path}')
            print(f'Falling back to: {self._active_config.get("fallback_checkpoint", "yolo26m.pt")}')
            full_path = PROJECT_ROOT / self._active_config.get('fallback_checkpoint', 'yolo26m.pt')
        return YOLO(str(full_path))

    def get_active_info(self) -> dict:
        return self._active_config.copy()

    def switch_to(self, model_name: str):
        configs = {
            'yolo26_halovision_v2': {
                'active_model': 'yolo26_halovision_v2',
                'checkpoint': 'models/yolo26_halovision_v2/best.pt',
            },
            'original': {
                'active_model': 'yolo26m',
                'checkpoint': 'models/original/yolo26m_original.pt',
            },
            'yolo26m': {
                'active_model': 'yolo26m',
                'checkpoint': 'yolo26m.pt',
            },
            'yolo26s': {
                'active_model': 'yolo26s',
                'checkpoint': 'yolo26s.pt',
            },
            'yolo26n': {
                'active_model': 'yolo26n',
                'checkpoint': 'yolo26n.pt',
            },
        }
        if model_name not in configs:
            raise ValueError(f'Unknown model: {model_name}. Available: {list(configs.keys())}')

        new_config = configs[model_name]
        new_config['fallback_model'] = self._active_config.get('active_model', 'yolo26m')
        new_config['fallback_checkpoint'] = self._active_config.get('checkpoint', 'yolo26m.pt')
        new_config['switch_date'] = __import__('datetime').datetime.now().isoformat()

        self._save_config(new_config)
        print(f'Switched to model: {model_name}')
        print(f'Checkpoint: {new_config["checkpoint"]}')
        print(f'Rollback available: {new_config["fallback_model"]}')

    def list_available_models(self) -> list:
        models = []
        for name in ['yolo26m.pt', 'yolo26s.pt', 'yolo26n.pt']:
            p = PROJECT_ROOT / name
            if p.exists():
                models.append({'name': name, 'path': str(p), 'size_mb': p.stat().st_size / (1024*1024)})
        hv2 = MODELS_DIR / 'yolo26_halovision_v2' / 'best.pt'
        if hv2.exists():
            models.append({'name': 'yolo26_halovision_v2', 'path': str(hv2), 'size_mb': hv2.stat().st_size / (1024*1024)})
        orig = MODELS_DIR / 'original' / 'yolo26m_original.pt'
        if orig.exists():
            models.append({'name': 'yolo26m_original', 'path': str(orig), 'size_mb': orig.stat().st_size / (1024*1024)})
        return models
