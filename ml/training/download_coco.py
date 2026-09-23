"""
HaloVision v2 - COCO 2017 Download Script
Downloads COCO 2017 train/val for baseline preservation.

Usage:
    python ml/training/download_coco.py

Downloads to: D:/halovision_downloads/coco2017/
Extracts to: ml/training/datasets/halovision_v2/sources/coco2017/
"""

import os
import sys
import urllib.request
import zipfile
import json
import time
from pathlib import Path
from hashlib import sha256

# Use D: drive for large downloads
DOWNLOAD_DIR = Path('D:/halovision_downloads/coco2017')
EXTRACT_DIR = Path('ml/training/datasets/halovision_v2/sources/coco2017')

COCO_URLS = {
    'train_images': {
        'url': 'http://images.cocodataset.org/zips/train2017.zip',
        'filename': 'train2017.zip',
        'size_gb': 18.0,
    },
    'val_images': {
        'url': 'http://images.cocodataset.org/zips/val2017.zip',
        'filename': 'val2017.zip',
        'size_gb': 1.0,
    },
    'annotations': {
        'url': 'http://images.cocodataset.org/annotations/annotations_trainval2017.zip',
        'filename': 'annotations_trainval2017.zip',
        'size_gb': 0.24,
    },
}

def download_file(url, dest, expected_size_gb=None):
    """Download file with progress reporting."""
    if dest.exists():
        actual_size = dest.stat().st_size
        if expected_size_gb:
            expected_bytes = expected_size_gb * 1024**3
            if actual_size > expected_bytes * 0.99:
                print(f'  Already exists and complete: {dest.name} ({actual_size/1024**3:.1f} GB)')
                return True
        print(f'  Already exists: {dest.name} ({actual_size/1024**3:.1f} GB)')
        return True
    
    print(f'  Downloading: {dest.name}')
    print(f'  From: {url}')
    if expected_size_gb:
        print(f'  Expected size: ~{expected_size_gb:.0f} GB')
    
    start_time = time.time()
    
    try:
        def progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            elapsed = time.time() - start_time
            if elapsed > 0:
                speed = downloaded / elapsed
                if total_size > 0:
                    pct = min(100, downloaded * 100 / total_size)
                    remaining = (total_size - downloaded) / speed if speed > 0 else 0
                    print(f'\r  {pct:.1f}% ({downloaded/1024**3:.1f}/{total_size/1024**3:.1f} GB) '
                          f'Speed: {speed/1024**2:.1f} MB/s  ETA: {remaining/60:.0f} min',
                          end='', flush=True)
                else:
                    print(f'\r  {downloaded/1024**3:.1f} GB downloaded '
                          f'Speed: {speed/1024**2:.1f} MB/s',
                          end='', flush=True)
        
        urllib.request.urlretrieve(url, str(dest), reporthook=progress)
        elapsed = time.time() - start_time
        print(f'\n  Download complete in {elapsed/60:.1f} minutes')
        return True
    except Exception as e:
        print(f'\n  ERROR: {e}')
        if dest.exists():
            dest.unlink()
        return False

def extract_zip(zip_path, extract_to, member=None):
    """Extract zip file."""
    print(f'  Extracting: {zip_path.name}')
    start_time = time.time()
    
    try:
        with zipfile.ZipFile(str(zip_path), 'r') as zf:
            if member:
                zf.extract(member, str(extract_to))
            else:
                zf.extractall(str(extract_to))
        elapsed = time.time() - start_time
        print(f'  Extracted in {elapsed/60:.1f} minutes')
        return True
    except Exception as e:
        print(f'  ERROR: {e}')
        return False

def verify_coco_structure(base_dir):
    """Verify COCO directory structure."""
    print('--- Verifying COCO Structure ---')
    
    checks = [
        (base_dir / 'train2017', 'Train images directory'),
        (base_dir / 'val2017', 'Val images directory'),
        (base_dir / 'annotations' / 'instances_train2017.json', 'Train annotations'),
        (base_dir / 'annotations' / 'instances_val2017.json', 'Val annotations'),
    ]
    
    all_ok = True
    for path, desc in checks:
        if path.exists():
            if path.is_dir():
                count = len(list(path.iterdir()))
                print(f'  OK: {desc} ({count} files)')
            else:
                size = path.stat().st_size / 1024**2
                print(f'  OK: {desc} ({size:.0f} MB)')
        else:
            print(f'  MISSING: {desc}')
            all_ok = False
    
    return all_ok

def main():
    os.chdir(r'C:\Users\wwwas\OneDrive\Desktop\FullStack Halovision\HaloVision')
    
    print('=' * 60)
    print('COCO 2017 DOWNLOAD')
    print('=' * 60)
    print(f'Download dir: {DOWNLOAD_DIR}')
    print(f'Extract dir: {EXTRACT_DIR}')
    print()
    
    # Create directories
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Download each file
    for name, info in COCO_URLS.items():
        print(f'--- {name} ---')
        dest = DOWNLOAD_DIR / info['filename']
        
        if not download_file(info['url'], dest, info['size_gb']):
            print(f'FAILED to download {name}')
            return False
        print()
    
    # Extract
    print('--- Extracting ---')
    for name, info in COCO_URLS.items():
        zip_path = DOWNLOAD_DIR / info['filename']
        
        if not extract_zip(zip_path, EXTRACT_DIR):
            print(f'FAILED to extract {name}')
            return False
        print()
    
    # Verify
    if not verify_coco_structure(EXTRACT_DIR):
        print('WARNING: COCO structure verification failed')
    
    # Save metadata
    metadata = {
        'source': 'COCO 2017',
        'license': 'CC BY 4.0',
        'url': 'http://images.cocodataset.org/',
        'download_date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'files': {name: info['filename'] for name, info in COCO_URLS.items()},
    }
    
    with open(EXTRACT_DIR / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print()
    print('=== COCO 2017 DOWNLOAD COMPLETE ===')
    print(f'Next step: Convert COCO annotations to YOLO format')
    print(f'Run: python ml/training/convert_coco.py')
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
