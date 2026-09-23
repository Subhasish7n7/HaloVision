"""
HaloVision v2 - COCO to YOLO Format Converter
Converts COCO 2017 annotations to YOLO format for HaloVision training.

Usage:
    python ml/training/convert_coco.py

Input: ml/training/datasets/halovision_v2/sources/coco2017/
Output: ml/training/datasets/halovision_v2/ (YOLO format)
"""

import os
import sys
import json
import shutil
from pathlib import Path
from collections import defaultdict

# Paths
COCO_DIR = Path('ml/training/datasets/halovision_v2/sources/coco2017')
OUTPUT_DIR = Path('ml/training/datasets/halovision_v2')

# COCO class ID to HaloVision class ID mapping
# COCO classes 0-79 map to HaloVision classes 0-79 (same order)
COCO_TO_HALOVISION = {i: i for i in range(80)}

def convert_coco_bbox_to_yolo(bbox, img_width, img_height):
    """Convert COCO bbox [x, y, w, h] to YOLO format [cx, cy, w, h] normalized."""
    x, y, w, h = bbox
    
    # Convert to center format
    cx = x + w / 2
    cy = y + h / 2
    
    # Normalize
    cx /= img_width
    cy /= img_height
    w /= img_width
    h /= img_height
    
    return [cx, cy, w, h]

def process_coco_annotations(annotations_file, images_dir, output_labels_dir, output_images_dir):
    """Process a single COCO annotations file."""
    print(f'  Processing: {annotations_file.name}')
    
    with open(annotations_file) as f:
        coco = json.load(f)
    
    # Build image info lookup
    images = {img['id']: img for img in coco['images']}
    
    # Build category lookup
    categories = {cat['id']: cat for cat in coco['categories']}
    
    # Group annotations by image
    annotations_by_image = defaultdict(list)
    for ann in coco['annotations']:
        if ann.get('iscrowd', 0):
            continue  # Skip crowd annotations
        
        img_id = ann['image_id']
        if img_id not in images:
            continue
        
        cat_id = ann['category_id']
        if cat_id not in categories:
            continue
        
        # Map COCO category to HaloVision class ID
        # COCO category IDs are 1-based, but we need to find the index
        # COCO categories are ordered by id, but not necessarily sequential
        halo_class_id = None
        for i, cat in enumerate(coco['categories']):
            if cat['id'] == cat_id:
                halo_class_id = i
                break
        
        if halo_class_id is None or halo_class_id >= 80:
            continue  # Skip if not in our 80-class mapping
        
        annotations_by_image[img_id].append({
            'class_id': halo_class_id,
            'bbox': ann['bbox'],
        })
    
    # Process each image
    processed = 0
    skipped = 0
    
    for img_id, img_info in images.items():
        filename = img_info['file_name']
        img_width = img_info['width']
        img_height = img_info['height']
        
        # Source image path
        src_img = images_dir / filename
        if not src_img.exists():
            skipped += 1
            continue
        
        # Copy image to output
        dst_img = output_images_dir / filename
        if not dst_img.exists():
            shutil.copy2(src_img, dst_img)
        
        # Create label file
        label_filename = Path(filename).stem + '.txt'
        label_path = output_labels_dir / label_filename
        
        if img_id in annotations_by_image:
            with open(label_path, 'w') as f:
                for ann in annotations_by_image[img_id]:
                    yolo_bbox = convert_coco_bbox_to_yolo(ann['bbox'], img_width, img_height)
                    f.write(f"{ann['class_id']} {yolo_bbox[0]:.6f} {yolo_bbox[1]:.6f} {yolo_bbox[2]:.6f} {yolo_bbox[3]:.6f}\n")
        else:
            # Empty label file for images with no annotations
            label_path.touch()
        
        processed += 1
    
    print(f'    Processed: {processed} images')
    print(f'    Skipped: {skipped} images (missing source)')
    print(f'    Labels: {len(list(output_labels_dir.glob("*.txt")))} files')
    
    return processed

def main():
    os.chdir(r'C:\Users\wwwas\OneDrive\Desktop\FullStack Halovision\HaloVision')
    
    print('=' * 60)
    print('COCO TO YOLO CONVERSION')
    print('=' * 60)
    print(f'Source: {COCO_DIR}')
    print(f'Output: {OUTPUT_DIR}')
    print()
    
    # Create output directories
    for split in ['train', 'val']:
        (OUTPUT_DIR / 'images' / split).mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / 'labels' / split).mkdir(parents=True, exist_ok=True)
    
    # Process train split
    print('--- Train Split ---')
    train_annotations = COCO_DIR / 'annotations' / 'instances_train2017.json'
    train_images = COCO_DIR / 'train2017'
    train_labels_out = OUTPUT_DIR / 'labels' / 'train'
    train_images_out = OUTPUT_DIR / 'images' / 'train'
    
    if train_annotations.exists() and train_images.exists():
        train_count = process_coco_annotations(
            train_annotations, train_images, train_labels_out, train_images_out
        )
    else:
        print(f'  MISSING: {train_annotations} or {train_images}')
        return False
    print()
    
    # Process val split
    print('--- Val Split ---')
    val_annotations = COCO_DIR / 'annotations' / 'instances_val2017.json'
    val_images = COCO_DIR / 'val2017'
    val_labels_out = OUTPUT_DIR / 'labels' / 'val'
    val_images_out = OUTPUT_DIR / 'images' / 'val'
    
    if val_annotations.exists() and val_images.exists():
        val_count = process_coco_annotations(
            val_annotations, val_images, val_labels_out, val_images_out
        )
    else:
        print(f'  MISSING: {val_annotations} or {val_images}')
        return False
    print()
    
    # Summary
    print('=== CONVERSION COMPLETE ===')
    print(f'Train: {train_count} images converted')
    print(f'Val: {val_count} images converted')
    print(f'Total: {train_count + val_count} images')
    print()
    print('Next steps:')
    print('1. Run validation: python ml/training/validate_dataset.py ml/training/datasets/halovision_v2/halovision_v2.yaml')
    print('2. Download Open Images V7 filtered classes')
    print('3. Download Roboflow supplemental datasets')
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
