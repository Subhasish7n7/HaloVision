# HaloVision YOLO26 Dataset Plan — v2 (RESTART)

> **Status: 2026-09-24 — Workflow restarted from the beginning.**
> Stage 0 audit completed. Previous acquisition run was partially complete and is
> superseded where noted below. Machine-readable tracking lives in
> `dataset_manifest.yaml` (Stage 1). Storage moved to **D:\HaloVisionData**
> (`HALOVISION_DATA_DIR`); the C: project keeps only code/config/small metadata.

---

## 0. Stage 0 Audit Results (2026-09-24)

| Item | Finding | Action |
|---|---|---|
| COCO 2017 zips | **COMPLETE & VERIFIED** in `D:\HaloVisionData\downloads\coco\` (moved from `D:\halovision_downloads\`): train2017.zip 19,336,861,798 B (118,288 entries), val2017.zip 815,585,330 B (5,001 entries), annotations_trainval2017.zip 252,907,541 B (6 entries). Zip central-directory integrity PASS. | **Do not redownload.** |
| COCO extraction | train2017: 118,287 files, val2017: 5,000 files, annotations: 6 files — was on C:, **moved to `D:\HaloVisionData\datasets\coco2017\`**. | Reuse as conversion source. |
| Previous partial conversion | C: `ml/training/datasets/halovision_v2/` had 94,475 train images / 94,474 labels (1 image missing label), **0 val, 0 test**. Sampled 30,000 labels: 0 malformed, class IDs only 0–79 (mapping correct), ~0.9% empty background labels (normal for COCO). | **Superseded** — clean rebuild on D: with proper train/val/test splits. C: copy retained until rebuilt dataset validates, then removed (derived data, reproducible). |
| Class mapping 0–79 | `halovision_v2.yaml` names match standard COCO→YOLO order exactly; verified against `instances_train2017.json` (80 categories, sparse IDs 1–90, sorted-index mapping). **No discrepancy found.** | Mapping FROZEN as approved. |
| Open Images | Nothing downloaded. | Stage 3 (targeted subset only). |
| Roboflow | Nothing downloaded. | Stage 4, gap-driven only; export needs API key. |
| Custom data | Nothing collected. | Stage 5 structure + report gaps. |
| Previous training runs | **None** (`runs/`, `ml/training/runs/` absent). | — |
| Model files | `yolov8n.pt`, `yolov8m.pt`, `App/yolov8m.pt`, `yolo26n/s/m.pt`, `models/original/yolo26m_original.pt` all present. `models/yolo26_halovision_v2/` contains only `training_config.json` — **no trained checkpoint exists yet** (`active_model.json` points at nonexistent `best.pt`). | Originals protected; new model → D:. |
| Training scripts | Hardcoded `os.chdir(r'C:\Users\wwwas\...')` + `D:/halovision_downloads`; `validate_dataset.py` NameError (`line_id`); `train_halovision.py` typo `metrics/mAP50-50(B)`; empty-label policy conflict between converter and validator. | Rewritten for this restart (Stage 8). |
| Toolchain | `.venv` is empty. Working interpreter: **`C:\Python314\python.exe`** (Python 3.14.3, ultralytics **8.4.24**, torch 2.11.0). GPU present: **RTX 3060 6GB** (CUDA 12.8 driver) but torch was CPU-only → CUDA wheel install in progress. | Use Python314; CUDA torch for training. |
| Disk space | C: 62.6 GB free, **D: 103.4 GB free**, RAM 16 GB, CPU 8c/16t. | D: budget below. |

### Disk budget (before any new download)

| Stage | Estimate | Fits D: (103.4 GB free)? |
|---|---|---|
| COCO move (done) | 0 net (relocated) | ✔ |
| COCO → halovision_v2 conversion (images copied once) | +19.4 GB | ✔ |
| Open Images CSVs | ~2.1 GB | ✔ |
| Open Images subset images | 1–4 GB | ✔ |
| Roboflow (if needed) | 1–4 GB | ✔ |
| Final halovision_v2 dataset | ~22–26 GB | ✔ |
| Training runs (checkpoints, yolo26s) | ~3–6 GB | ✔ |
| Trained models | <0.5 GB | ✔ |
| **Peak total** | **~55 GB** | ✔ ~48 GB headroom |
| Cleanup after validation (archives + C: partial) | −20 GB archives, −15 GB C: | ✔ |

Nothing large is ever written to C:.

---

## 1. Goal

YOLO26 model with **95 classes**:
- IDs **0–79**: original COCO classes, preserved exactly (baseline capability retained).
- IDs **80–94**: HaloVision accessibility classes (approved mapping, frozen).

Trained via transfer learning from `yolo26s.pt`. Output: `D:\HaloVisionData\models\yolo26_halovision_v2\{best.pt,last.pt,data.yaml,metadata.json,results.csv}`.
**Original YOLOv8 model is never modified.** Rollback: `App/yolov8m.pt` (+ copy staged to `D:\HaloVisionData\models\original\`).

## 2. Class definitions (annotation contract)

| ID | Name | Definition / labeling rule |
|---|---|---|
| 80 | wheelchair | A wheelchair (occupied or empty). |
| 81 | white_cane | **Only** mobility canes used by blind/low-vision people. Never sticks, umbrellas, poles, hiking poles. |
| 82 | crutches | Pair or single crutch in use or standing. |
| 83 | guide_dog | Dog with harness/vest indicating guide role. Pet dogs = class 16 `dog`. |
| 84 | crosswalk | Painted pedestrian crossing on roadway. |
| 85 | curb | Raised kerb/curb separating road from pavement. |
| 86 | pothole | Damaged road surface hole/depression. |
| 87 | stairs | **Fixed flight of steps** (whole flight). Separate from escalator (88). Not a single step, ladder, or ramp. |
| 88 | escalator | Moving staircase. |
| 89 | elevator | Elevator car/doors-as-elevator (lift). |
| 90 | door | Physical door panel/leaf. |
| 91 | entrance | Entrance opening/passage into a structure (may include open doorways). |
| 92 | exit | Egress opening or EXIT-sign-marked doorway. |
| 93 | bollard | Short free-standing vertical post controlling traffic. |
| 94 | road_barrier | Horizontal/temporary road barrier, guard rail, gate arm. Not a bollard. |

Renames from old plan applied: `walking_cane → white_cane`, `staircase → stairs`.

## 3. Sources & licensing

| Source | Classes covered | License | Method | Status (2026-09-26) |
|---|---|---|---|---|
| **COCO 2017** (verified, on D:) | baseline 0–79 | COCO Terms of Use; annotations CC BY 4.0 | Already downloaded+extracted; converted with train/val/test splits | **Converted**: 112,304 train / 5,000 val / 5,983 test; 886,282 annos |
| **Open Images V7** (Stage 3) | wheelchair(80), crutches(82), stairs(87), door(90) — only these 4 exist as boxable classes (all 601 names scanned) | Images CC BY 4.0; annotations CC BY 4.0 | CSV-filter by LabelName → S3-mirror image download (image-URL CSVs are 403; v5 bbox object 403 → used v6 object) | **Downloaded + converted**: 1,872 subset images |
| **CDSet-3434 crosswalk** (Stage 4) | crosswalk(84) | Apache-2.0 | HF mirror of Zenodo DOI 10.5281/zenodo.8289874; guide-arrow class unmapped→skipped | **Converted**: 2,923 imgs (train 2,096 / val 413 / test 414) |
| **RDD2022-derived road damage** (Stage 4) | pothole(86) via class D40 | CC BY-SA 4.0 | HF mirror of CRDDC 2022 derivative; crack classes D00/D10/D20 unmapped→skipped | **Converted**: 6,279 imgs (train 4,344 / val 962 / test 973) |
| **ROD Obstacle-Detection** (Stage 4, HF) | stairs(87), crosswalk(84), road_barrier(94) via local 4/14/18/20 | **MIT** (rev pinned `add28c7f…`; cite `zandi2026rod`) | Selective download of target-class splits; **guard rail(13) excluded** (~33% label noise) | **Converted + deduped** (2026-09-26): 4,158 imgs, 0 missing labels |
| **AssistEye Unified Obstacles** (Stage 4, HF) | pothole(86) via local 3 | **MIT** (rev pinned `319fa39f…`) | Full download; **pole(7) rejected** (verification failed: 58% streetlights) | **Converted + deduped** (2026-09-26): 292 imgs |
| **Rejected**: miia-pothole (classification-only), Nielbagz/Bollard (empty repo), GuideDog (VQA CC-BY-NC), keremberke/pothole (90 imgs, masks), ROD Guard rail (label noise), AssistEye pole (wrong objects) | — | — | — | Rejected: license/quality reasons recorded in manifest |
| **Custom phone captures** (Stage 5) | final gaps: white_cane, guide_dog, elevator, entrance, exit, bollard | Project-owned | Manual; ≥50 images/gap class; structure created | **Structure created** (15 class dirs + guides); needs manual capture |

No account/API-key source was required — Roboflow Universe exports were avoided in favor of account-free HF mirrors with explicit licenses.

Classes with no faithful external equivalent are **not force-labeled** — they go to Stage 5.

## 4. Target layout (D:)

```
D:\HaloVisionData\datasets\halovision_v2\
    images\{train,val,test}\      labels\{train,val,test}\
    halovision_v2.yaml            sources\<per-source provenance>\
```

- **val/** = full COCO val2017 (5,000) + new-class val splits → preserves standard COCO comparison basis (Stage 11).
- **test/** = deterministic 5% carve of COCO train2017 + 15% of each new-class source.
- **train/** = remaining COCO train2017 + 70% of each new-class source.
- Leakage control: MD5 dedup across splits; same-source id uniqueness; deterministic seeding.
- Empty (background) labels are **valid** for COCO images with no instances — validator treats "image with no label file" as error, "empty label file" as OK (policy conflict from old scripts resolved).

## 5. Pipeline stages (automation order)

1. ~~AUDIT~~ ✔ 2026-09-24
2. ~~MANIFEST~~ ✔ `dataset_manifest.yaml` + this file
3. ~~COCO~~ ✔ zips verified; moved to D:; converted (112,304/5,000/5,983)
4. ~~OPEN IMAGES~~ ✔ class verification (4 matched/11 absent) + 1,872 subset images
5. ~~ROBOFLOW/SUPPLEMENTAL~~ ✔ CDSet-3434 + RDD2022 + ROD + AssistEye (account-free HF mirrors, MIT/Apache/CC-BY-SA; pinned revisions)
6. ~~CUSTOM STRUCTURE~~ ✔ 15 class dirs created; 6 gap classes await manual capture (81/83/89/91/92/93)
7. ~~CONVERSION~~ ✔ final rerun 2026-09-26 (HF ingest active) + dedup applied (1,079 pairs quarantined)
8. ~~VALIDATION~~ ✔ **PASSED 2026-09-26** — `validate_dataset.py` exit 0, 0/10 critical keys (report JSON: `runs\validation\dataset_validation_report.json`); 167,655 imgs / 955,224 anns; gaps [81, 83, 89, 91, 92, 93]
9. **TRAINING PREP** — `train_halovision.py` (YOLO26, D: paths, config/metadata/results capture; originals untouched)
10. **TRAIN** — `train_halovision.py` (2-phase transfer from yolo26n) → versioned output on D: — **MANUAL: user runs this command**
11. **EVALUATION** — new model: COCO 0–79, new 80–94, P/R/mAP, per-class, speed
12. **COMPARISON** — same val set: original `yolov8m.pt` vs new `best.pt`; report measured deltas incl. COCO degradation check
13. **INTEGRATION CHECK** — load model in `PerceptionSystem` context, verify output shape/classes/tracking/depth/EventBus compatibility (no architecture changes)
14. **VERSIONING/ROLLBACK** — `models/yolo26_halovision_v2/metadata.json`, update `active_model.json` **only if integration passes**; rollback = original YOLOv8
15. **FINAL VERIFICATION** — pytest suite + model-load/inference/track-ID smoke tests + original-file checksum proof

## 6. Rules of engagement

- No stage declared complete without executed + verified evidence.
- No silent class-ID changes; mapping frozen in `dataset_manifest.yaml`.
- No validation-before-training skip; validator never weakened to hide errors.
- Original YOLOv8/`App/yolov8m.pt` never overwritten (checksum-verified at end).
- Every large download reports: size estimate, D: free space, partial state, subset strategy first.
- Blocking stops only for: external account/login, manual image capture, destructive actions, license acceptance, unforeseen genuinely-blocking decisions.
