"""
HaloVision v2 - Roboflow Dataset Download Script
Downloads supplemental datasets from Roboflow Universe.

Usage:
    python ml/training/download_roboflow.py

Downloads to: ml/training/datasets/halovision_v2/sources/roboflow/
"""

import os
import sys
import json
from pathlib import Path

DOWNLOAD_BASE = Path('D:/halovision_downloads/roboflow')
EXTRACT_BASE = Path('ml/training/datasets/halovision_v2/sources/roboflow')

# Roboflow datasets to download
# Format: (name, url, classes_we_need, license)
ROBOFLOW_DATASETS = [
    {
        'name': 'wheelchair-detection',
        'url': 'https://universe.roboflow.com/mobilityaids/wheelchair-detection-hh3io',
        'download_url': 'https://universe.roboflow.com/mobilityaids/wheelchair-detection-hh3io/download/export?format=yolov8',
        'classes': ['wheelchair'],
        'license': 'CC BY 4.0',
        'our_class_ids': [80],
    },
    {
        'name': 'white-cane',
        'url': 'https://universe.roboflow.com/nodongjaeteam-g1pbo/white-cane-hyjat',
        'download_url': 'https://universe.roboflow.com/nodongjaeteam-g1pbo/white-cane-hyjat/download/export?format=yolov8',
        'classes': ['white_cane'],
        'license': 'CC BY 4.0',
        'our_class_ids': [81],
    },
    {
        'name': 'mobility-aid-detector',
        'url': 'https://universe.roboflow.com/mbdetector/mobility-aid-detector-mwxuw',
        'download_url': 'https://universe.roboflow.com/mbdetector/mobility-aid-detector-mwxuw/download/export?format=yolov8',
        'classes': ['crutches', 'wheelchair'],
        'license': 'CC BY 4.0',
        'our_class_ids': [82, 80],
    },
    {
        'name': 'bollards-crosswalk-stairs',
        'url': 'https://universe.roboflow.com/esera/bollards-crosswalk-stairs',
        'download_url': 'https://universe.roboflow.com/esera/bollards-crosswalk-stairs/download/export?format=yolov8',
        'classes': ['crosswalk', 'Bollard', 'downstairs', 'upstairs'],
        'license': 'CC BY 4.0',
        'our_class_ids': [84, 93, 87, 87],
    },
    {
        'name': 'pothole-detection',
        'url': 'https://universe.roboflow.com/aegis/pothole-detection-i00zy',
        'download_url': 'https://universe.roboflow.com/aegis/pothole-detection-i00zy/download/export?format=yolov8',
        'classes': ['Pothole'],
        'license': 'CC BY 4.0',
        'our_class_ids': [86],
    },
    {
        'name': 'ood-obstacles',
        'url': 'https://universe.roboflow.com/fpn/ood-pbnro',
        'download_url': 'https://universe.roboflow.com/fpn/ood-pbnro/download/export?format=yolov8',
        'classes': ['curb', 'stairs', 'crutch'],
        'license': 'CC BY 4.0',
        'our_class_ids': [85, 87, 82],
    },
    {
        'name': 'vision-impaired-assistance',
        'url': 'https://universe.roboflow.com/vision-impaired-assistance/vision-impaired-assistance',
        'download_url': 'https://universe.roboflow.com/vision-impaired-assistance/vision-impaired-assistance/download/export?format=yolov8',
        'classes': ['door'],
        'license': 'CC BY 4.0',
        'our_class_ids': [90],
    },
]

def download_roboflow(dataset_info):
    """Download a Roboflow dataset."""
    name = dataset_info['name']
    dest_dir = DOWNLOAD_BASE / name
    
    if dest_dir.exists() and any(dest_dir.iterdir()):
        print(f'  Already exists: {name}')
        return True
    
    print(f'  Downloading: {name}')
    print(f'  URL: {dataset_info["download_url"]}')
    print(f'  Classes needed: {dataset_info["classes"]}')
    
    # Note: Roboflow downloads require authentication
    # This script creates a manifest for manual download
    print(f'  NOTE: Roboflow downloads require API key or manual download')
    print(f'  Please download from: {dataset_info["url"]}')
    print(f'  Export format: YOLOv8')
    print()
    
    return True

def create_download_manifest():
    """Create a manifest of all Roboflow datasets to download."""
    manifest = {
        'note': 'Download these datasets manually from Roboflow Universe',
        'format': 'YOLOv8',
        'datasets': []
    }
    
    for ds in ROBOFLOW_DATASETS:
        manifest['datasets'].append({
            'name': ds['name'],
            'url': ds['url'],
            'classes': ds['classes'],
            'license': ds['license'],
            'our_class_ids': ds['our_class_ids'],
            'download_instructions': f'Go to {ds["url"]}, click Download, select YOLOv8 format',
        })
    
    manifest_path = EXTRACT_BASE / 'download_manifest.json'
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f'Download manifest created: {manifest_path}')
    return manifest_path

def main():
    os.chdir(r'C:\Users\wwwas\OneDrive\Desktop\FullStack Halovision\HaloVision')
    
    print('=' * 60)
    print('ROBOFLOW DATASET DOWNLOAD')
    print('=' * 60)
    print()
    
    # Create directories
    DOWNLOAD_BASE.mkdir(parents=True, exist_ok=True)
    EXTRACT_BASE.mkdir(parents=True, exist_ok=True)
    
    # Create manifest
    print('--- Creating Download Manifest ---')
    manifest_path = create_download_manifest()
    print()
    
    # Print download instructions
    print('--- Download Instructions ---')
    print('The following datasets need to be downloaded manually:')
    print()
    for ds in ROBOFLOW_DATASETS:
        print(f'1. Go to: {ds["url"]}')
        print(f'2. Click "Download"')
        print(f'3. Select "YOLOv8" format')
        print(f'4. Save to: {DOWNLOAD_BASE / ds["name"]}')
        print(f'5. Extract to: {EXTRACT_BASE / ds["name"]}')
        print(f'6. Classes needed: {ds["classes"]}')
        print(f'7. License: {ds["license"]}')
        print()
    
    print('=== ROBOFLOW MANIFEST COMPLETE ===')
    print(f'Manifest: {manifest_path}')
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
