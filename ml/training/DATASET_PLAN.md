# HaloVision v2 Dataset Acquisition Plan

**Generated:** 2026-09-23  
**Status:** PLANNING — No downloads yet  
**Goal:** Train YOLO26s with 95 classes (80 COCO + 15 HaloVision)

---

## Executive Summary

This plan documents the dataset acquisition strategy for HaloVision v2. The existing 80 COCO classes are confirmed to match the model's class mapping. 15 new HaloVision accessibility classes are proposed (IDs 80-94). After auditing Open Images V7 and Roboflow Universe, we found:

- **4 classes** available directly from Open Images V7
- **8 classes** available from Roboflow Universe (supplemental)
- **5 classes** require custom phone-camera capture

**Two class names must be renamed** to match available dataset terminology.

---

## Confirmed COCO Class Mapping

**Source:** `yolo26m.pt` (Ultralytics 8.4.158)  
**Verification:** All 80 COCO classes (IDs 0-79) match `halovision_v2.yaml` exactly.  
**No changes required to existing class IDs.**

---

## Proposed New Classes (IDs 80-94)

| ID | Current Name | Status | Action Required |
|----|--------------|--------|-----------------|
| 80 | wheelchair | ✅ Available | None |
| 81 | walking_cane | ⚠️ Rename | Rename to `white_cane` |
| 82 | crutches | ✅ Available | None |
| 83 | guide_dog | ❌ Custom | Custom capture required |
| 84 | crosswalk | ✅ Available | None |
| 85 | curb | ⚠️ Partial | Roboflow + custom recommended |
| 86 | pothole | ✅ Available | None |
| 87 | staircase | ⚠️ Rename | Rename to `stairs` |
| 88 | escalator | ⚠️ Partial | Roboflow + custom recommended |
| 89 | elevator | ⚠️ Partial | Roboflow + custom recommended |
| 90 | door | ✅ Available | None |
| 91 | entrance | ❌ Custom | Custom capture required |
| 92 | exit | ❌ Custom | Custom capture required |
| 93 | bollard | ⚠️ Partial | Roboflow + custom recommended |
| 94 | road_barrier | ❌ Custom | Custom capture required |

---

## Class Ambiguity Definitions

These definitions resolve potential confusion between similar classes:

### staircase → stairs (RENAMED)
- **Definition:** A flight of steps connecting different floor levels
- **Open Images V7:** Class 489 "Stairs"
- **Action:** Rename to `stairs` for consistency

### walking_cane → white_cane (RENAMED)
- **Definition:** A white cane used by visually impaired persons for navigation
- **Roboflow:** Multiple "white_cane" datasets available
- **Action:** Rename to `white_cane` to match dataset terminology

### guide_dog vs dog
- **guide_dog:** A dog wearing a harness, vest, or leading a visually impaired person
- **dog (Coco 16):** Any dog without harness/vest
- **Distinction:** Guide dogs have visible harness/vest equipment

### door vs entrance
- **door:** The physical door panel, gate, or entryway structure itself
- **entrance:** An entrance marked by signage, archway, or architectural features indicating entry point
- **Distinction:** Door is the object; entrance is the location/feature

### entrance vs exit
- **entrance:** Marked by entry signage, archway, or architectural cues
- **exit:** Marked by EXIT signage, emergency exit features, or architectural cues
- **Distinction:** Signage and context determine classification

### crosswalk vs road
- **crosswalk:** Painted zebra stripes or crosswalk markings on road surface
- **road:** The general road surface (not annotated)
- **Distinction:** Only painted markings are crosswalk

### bollard vs road_barrier
- **bollard:** Short, sturdy vertical post (metal/concrete) for traffic control
- **road_barrier:** Larger horizontal barrier (jersey barrier, guardrail, construction barrier)
- **Distinction:** Size and orientation (vertical vs horizontal)

### curb vs road edge
- **curb:** Raised edge between road and sidewalk/pavement
- **road edge:** The boundary line (not annotated as separate class)
- **Distinction:** Curb is the physical raised structure

---

## Open Images V7 Availability

| Class | OID ID | OID Name | Available |
|-------|--------|----------|-----------|
| wheelchair | 583 | Wheelchair | ✅ Yes |
| crutches | 145 | Crutch | ✅ Yes |
| stairs | 489 | Stairs | ✅ Yes |
| door | 164 | Door | ✅ Yes |

**Download method:** Ultralytics fiftyone script (filtered to 4 classes only)  
**License:** CC BY 4.0  
**Estimated images:** 500-2000 per class (filtered)

---

## Roboflow Universe Availability

| Class | Dataset | Images | License |
|-------|---------|--------|---------|
| wheelchair | MobilityAids/wheelchair-detection-hh3io | 9,210 | CC BY 4.0 |
| white_cane | nodongjaeteam-g1pbo/white-cane-hyjat | 9,500 | CC BY 4.0 |
| crutches | mbdetector/mobility-aid-detector-mwxuw | 9,200 | CC BY 4.0 |
| crosswalk | esera/bollards-crosswalk-stairs | Unknown | CC BY 4.0 |
| curb | fpn/ood-pbnro | 10,000 | CC BY 4.0 |
| pothole | aegis/pothole-detection-i00zy | 1,482 | CC BY 4.0 |
| stairs | esera/bollards-crosswalk-stairs | Unknown | CC BY 4.0 |
| escalator | mallescalatorsystem | Unknown | CC BY 4.0 |
| elevator | detection-kgttv/wheelchair-7fzdq | Unknown | CC BY 4.0 |
| door | vision-impaired-assistance/vision-impaired-assistance | 17,073 | CC BY 4.0 |
| bollard | esera/bollards-crosswalk-stairs | Unknown | CC BY 4.0 |

**Download method:** Roboflow API or manual download  
**License:** CC BY 4.0 (verify per dataset)  
**Note:** Each dataset must be filtered to only the classes we need.

---

## Custom Phone-Camera Capture Required

| Class | Reason | Min Images | Target |
|-------|--------|------------|--------|
| guide_dog | No public dataset; must distinguish from ordinary dogs | 50 | 300 |
| entrance | No public dataset; context-dependent architectural feature | 50 | 300 |
| exit | No public dataset; must show EXIT signage | 50 | 300 |
| road_barrier | No public dataset; various barrier types | 50 | 300 |
| curb | OOD dataset exists but custom images recommended for diversity | 50 | 300 |

**Capture requirements:**
- Device: Mobile phone camera
- Conditions: Indoor/outdoor, day/night, various angles/distances
- Annotations: LabelImg or CVAT in YOLO format
- Format: `class_id cx cy w h` (normalized)

---

## Dataset Structure

```
ml/training/datasets/halovision_v2/
├── halovision_v2.yaml          # 95-class config
├── DATASET_PLAN.md             # This file
├── dataset_manifest.yaml       # Detailed acquisition manifest
├── images/
│   ├── train/                  # Training images
│   ├── val/                    # Validation images
│   └── test/                   # Test images
├── labels/
│   ├── train/                  # Training labels (YOLO format)
│   ├── val/                    # Validation labels
│   └── test/                   # Test labels
└── sources/
    ├── coco2017/               # COCO baseline data
    ├── open_images/            # Open Images V7 filtered
    ├── roboflow/               # Roboflow supplemental data
    └── custom/                 # Custom phone-camera data
```

---

## Download Sequence

### Phase 1: COCO 2017 (Baseline Preservation)
**Purpose:** Prevent catastrophic forgetting of 80 existing classes  
**Download:** ~19GB (train + val + annotations)  
**Source:** http://images.cocodataset.org/

### Phase 2: Open Images V7 (Filtered)
**Purpose:** 4 classes with direct OID matches  
**Download:** ~50GB estimated (filtered to 4 classes)  
**Method:** Ultralytics fiftyone script

### Phase 3: Roboflow Universe
**Purpose:** 8 classes with supplemental data  
**Download:** Variable (filter to needed classes)  
**Method:** Roboflow API or manual download

### Phase 4: Custom Capture
**Purpose:** 5 classes with no public datasets  
**Download:** N/A (capture manually)  
**Method:** Phone camera + LabelImg/CVAT

---

## License Compliance

| Source | License | Attribution Required |
|--------|---------|---------------------|
| COCO 2017 | CC BY 4.0 | Yes |
| Open Images V7 | CC BY 4.0 | Yes (Google) |
| Roboflow Universe | CC BY 4.0 (varies) | Yes (per dataset) |
| Custom capture | Internal | No |

**Required attributions:**
- COCO: "Contains images from MS COCO dataset, licensed under CC BY 4.0"
- Open Images: "Contains images from Google Open Images V7, licensed under CC BY 4.0"
- Roboflow: "Contains data from Roboflow Universe, licensed under CC BY 4.0"

---

## Validation Checklist

Before training, verify:
- [ ] All images present in correct split directories
- [ ] All labels present and matching image filenames
- [ ] No corrupt images (JPEG/PNG header check)
- [ ] No empty label files
- [ ] All class IDs in valid range (0-94)
- [ ] All bounding boxes normalized (0-1)
- [ ] No zero-area bounding boxes
- [ ] No train/val/test leakage
- [ ] Class distribution acceptable (no rare classes <10 annotations)
- [ ] No duplicate images across splits

**Run validation:**
```bash
python ml/training/validate_dataset.py ml/training/datasets/halovision_v2/halovision_v2.yaml
```

---

## Next Steps

1. **Verify dataset_manifest.yaml** — Review all class definitions and acquisition sources
2. **Confirm class renames** — Approve `walking_cane` → `white_cane` and `staircase` → `stairs`
3. **Begin Phase 1** — Download COCO 2017 baseline
4. **Begin Phase 2** — Download Open Images V7 filtered classes
5. **Begin Phase 3** — Download Roboflow supplemental datasets
6. **Begin Phase 4** — Custom phone-camera capture for 5 classes
7. **Validate dataset** — Run validation script
8. **Proceed to training** — Once validation passes

---

## Files Created

| File | Purpose |
|------|---------|
| `ml/training/datasets/halovision_v2/halovision_v2.yaml` | 95-class dataset config |
| `ml/training/datasets/halovision_v2/DATASET_PLAN.md` | This acquisition plan |
| `ml/training/dataset_manifest.yaml` | Detailed per-class acquisition manifest |
| `ml/training/validate_dataset.py` | Dataset validation script |
| `ml/training/train_halovision.py` | 2-phase training script |
| `models/yolo26_halovision_v2/training_config.json` | Training hyperparameters |
| `models/active_model.json` | Model switching config |
| `App/Perception/model_manager.py` | Model loading/switching/rollback |
