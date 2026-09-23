"""
HaloVision Dataset Validation Script
Validates YOLO-format dataset for correctness before training.

Usage:
    python ml/training/validate_dataset.py ml/training/datasets/halovision_v2/halovision_v2.yaml
"""

import os
import sys
import hashlib
from pathlib import Path
from collections import Counter, defaultdict
import yaml


def validate_dataset(yaml_path: str):
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    base = Path(cfg['path'])
    nc = cfg['nc']
    names = cfg['names']
    splits = ['train', 'val', 'test']

    report = {
        'total_images': 0,
        'total_labels': 0,
        'total_annotations': 0,
        'missing_labels': [],
        'missing_images': [],
        'corrupt_images': [],
        'empty_labels': [],
        'invalid_class_ids': [],
        'bbox_out_of_bounds': [],
        'zero_area_boxes': [],
        'invalid_format': [],
        'class_distribution': Counter(),
        'images_per_split': {},
        'annotations_per_split': {},
        'duplicates': [],
    }

    seen_hashes = set()

    for split in splits:
        img_dir = base / 'images' / split
        lbl_dir = base / 'labels' / split

        if not img_dir.exists():
            print(f'  SKIP split "{split}": images dir missing')
            continue

        images = {p.stem: p for p in img_dir.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.webp')}
        labels = {p.stem: p for p in lbl_dir.iterdir() if p.suffix == '.txt'} if lbl_dir.exists() else {}

        report['images_per_split'][split] = len(images)
        report['annotations_per_split'][split] = len(labels)
        report['total_images'] += len(images)

        for stem, img_path in images.items():
            # Duplicate check
            h = hashlib.md5(img_path.read_bytes()).hexdigest()
            if h in seen_hashes:
                report['duplicates'].append(str(img_path))
            seen_hashes.add(h)

            # Corrupt image check (try reading)
            try:
                with open(img_path, 'rb') as f:
                    header = f.read(16)
                if len(header) < 4:
                    report['corrupt_images'].append(str(img_path))
                    continue
                # Check JPEG/PNG magic bytes
                if header[:2] == b'\xff\xd8':  # JPEG
                    pass
                elif header[:8] == b'\x89PNG\r\n\x1a\n':  # PNG
                    pass
                elif header[:4] == b'RIFF':  # WebP
                    pass
                else:
                    # BMP or unknown - accept if file exists
                    pass
            except Exception as e:
                report['corrupt_images'].append(f'{img_path}: {e}')
                continue

            # Check for corresponding label
            if stem not in labels:
                report['missing_labels'].append(str(img_path))
                continue

            # Parse label file
            lbl_path = labels[stem]
            lbl_content = lbl_path.read_text().strip()

            if not lbl_content:
                report['empty_labels'].append(str(lbl_path))
                continue

            report['total_labels'] += 1

            for line_num, line in enumerate(lbl_content.split('\n'), 1):
                line = line.strip()
                if not line:
                    continue

                parts = line.split()
                if len(parts) < 5:
                    report['invalid_format'].append(f'{lbl_path}:{line_num}: expected >=5 values, got {len(parts)}')
                    continue

                try:
                    class_id = int(parts[0])
                    cx, cy, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                except ValueError:
                    report['invalid_format'].append(f'{lbl_path}:{line_num}: non-numeric values')
                    continue

                report['total_annotations'] += 1
                report['class_distribution'][class_id] += 1

                if class_id < 0 or class_id >= nc:
                    report['invalid_class_ids'].append(f'{lbl_path}:{line_id}: class_id {class_id} not in [0, {nc-1}]')

                if w <= 0 or h <= 0:
                    report['zero_area_boxes'].append(f'{lbl_path}:{line_num}: w={w} h={h}')

                if cx < 0 or cx > 1 or cy < 0 or cy > 1:
                    report['bbox_out_of_bounds'].append(f'{lbl_path}:{line_num}: center ({cx},{cy}) outside [0,1]')

                if w < 0 or w > 1 or h < 0 or h > 1:
                    report['bbox_out_of_bounds'].append(f'{lbl_path}:{line_num}: size ({w},{h}) outside [0,1]')

        # Check for label files without images
        for stem in labels:
            if stem not in images:
                report['missing_images'].append(str(labels[stem]))

    # Print report
    print()
    print('=' * 60)
    print('DATASET VALIDATION REPORT')
    print('=' * 60)
    print(f'Dataset: {yaml_path}')
    print(f'Classes: {nc}')
    print()
    print('--- Summary ---')
    print(f'Total images:        {report["total_images"]}')
    print(f'Total label files:   {report["total_labels"]}')
    print(f'Total annotations:   {report["total_annotations"]}')
    print()
    print('--- Per-Split ---')
    for split in splits:
        imgs = report['images_per_split'].get(split, 0)
        lbls = report['annotations_per_split'].get(split, 0)
        print(f'  {split}: {imgs} images, {lbls} label files')
    print()
    print('--- Errors ---')
    errors = [
        ('Missing labels', report['missing_labels']),
        ('Missing images', report['missing_images']),
        ('Corrupt images', report['corrupt_images']),
        ('Empty labels', report['empty_labels']),
        ('Invalid class IDs', report['invalid_class_ids']),
        ('BBox out of bounds', report['bbox_out_of_bounds']),
        ('Zero area boxes', report['zero_area_boxes']),
        ('Invalid format', report['invalid_format']),
        ('Duplicate images', report['duplicates']),
    ]

    has_errors = False
    for name, items in errors:
        if items:
            has_errors = True
            print(f'  {name}: {len(items)}')
            for item in items[:5]:
                print(f'    - {item}')
            if len(items) > 5:
                print(f'    ... and {len(items) - 5} more')
        else:
            print(f'  {name}: 0')
    print()
    print('--- Class Distribution ---')
    if report['class_distribution']:
        for cid in sorted(report['class_distribution'].keys()):
            name = names.get(cid, f'UNKNOWN_{cid}')
            count = report['class_distribution'][cid]
            print(f'  {cid:3d} ({name:20s}): {count:6d} annotations')
    else:
        print('  (no annotations found)')
    print()

    # Leakage check: stems in both train and val
    all_stems = defaultdict(list)
    for split in splits:
        img_dir = base / 'images' / split
        if img_dir.exists():
            for p in img_dir.iterdir():
                all_stems[p.stem].append(split)
    leaks = {s: splits_list for s, splits_list in all_stems.items() if len(splits_list) > 1}
    print('--- Train/Val Leakage ---')
    print(f'  Duplicates across splits: {len(leaks)}')
    for stem, splits_list in list(leaks.items())[:5]:
        print(f'    {stem}: {splits_list}')
    print()

    # Rare class detection
    print('--- Rare Classes (<10 annotations) ---')
    for cid in sorted(report['class_distribution'].keys()):
        if report['class_distribution'][cid] < 10:
            name = names.get(cid, f'UNKNOWN_{cid}')
            print(f'  {cid} ({name}): {report["class_distribution"][cid]} annotations')
    print()

    if has_errors:
        print('VALIDATION: FAILED (errors found)')
    else:
        print('VALIDATION: PASSED')
    print('=' * 60)

    return not has_errors


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python validate_dataset.py <dataset_yaml>')
        sys.exit(1)
    ok = validate_dataset(sys.argv[1])
    sys.exit(0 if ok else 1)
