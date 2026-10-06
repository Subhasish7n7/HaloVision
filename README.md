# HaloVision 👁️

**A real-time AI perception assistant for blind and low-vision people.**
Camera → YOLO26 (95 classes) → depth + tracking → safety rule engine → spoken alerts — running fully on your own machine.

HaloVision watches the world through a live camera stream, understands what is in front of you, and *says out loud* only what matters: a pothole approaching your feet, a group of people on your left, a traffic light turning red — in natural, rate-limited speech instead of a flood of notifications.

---

## Highlights

- **95-class YOLO26 detector** — all 80 COCO classes preserved plus 15 accessibility classes (`wheelchair, white_cane, crutches, guide_dog, crosswalk, curb, pothole, stairs, escalator, elevator, door, entrance, exit, bollard, road_barrier`) under frozen IDs 80–94.
- **Safety rule engine** — decides *what deserves to be spoken*, with per-object cooldowns, duplicate suppression, escalation bypass and threat-priority override. Multiple detections collapse into one phrase: *"2 people on your left, near you"* — never *"person, person, person"*.
- **Depth + tracking** — MiDaS (ONNX) depth and ByteTrack-style tracking so hazards are judged by distance and motion, not just presence.
- **Full duplex streaming** — WebRTC video + WebSocket control/analysis channels over a FastAPI backend.
- **Semantic EventBus** — perception, rules, speech and UI are decoupled through named events (`PERCEPTION_FRAME_READY`, `SPEECH_INTENT_CREATED`, …).
- **Modes** — navigation, object search, scene description and threat mode with different announcement policies.
- **Local-first / private** — inference, depth and TTS scheduling all run on-device (RTX 3060 + ONNX Runtime). No cloud vision APIs.
- **Reproducible ML pipeline** — audited, deduplicated, validated dataset with reversible-only operations (quarantine, never delete) and exit-code gates.

## Architecture

```
   Browser (React + Vite)                     FastAPI backend (:8000)
┌───────────────────────┐   WebRTC / WS  ┌──────────────────────────────────────┐
│  live video + HUD      │◄─────────────►│  Streaming endpoints (/ws, /rtc)     │
│  speech controls       │               │        │                             │
└────────────────────────┘               │        ▼                             │
                                          │  PerceptionSystem                   │
                                          │   ├─ Inference  (YOLO26 95-class)   │
                                          │   ├─ Tracker    (boxes over time)    │
                                          │   └─ Depth      (MiDaS ONNX)        │
                                          │        │  detections + depth        │
                                          │        ▼                             │
                                          │  EventBus ─► RuleEngine              │
                                          │   (named     (cooldowns, modes,      │
                                          │    events)    threat priority)       │
                                          │                 │ speech intents    │
                                          │                 ▼                   │
                                          │  SpeechScheduler ─► TTS (Azure)      │
                                          └──────────────────────────────────────┘
```

## The model: YOLO26 95-class (v2)

| | |
|---|---|
| **Base** | `yolo26n.pt` (Ultralytics 8.4) → fine-tuned to `yolo26_halovision_v2` |
| **Classes** | 0–79 COCO (frozen, untouched) + 80–94 HaloVision accessibility classes |
| **Training** | Two-phase transfer learning: phase 1 freezes the backbone (20 epochs), phase 2 full fine-tune (80 epochs) |
| **Dataset** | 167,655 images / 955,224 annotations — COCO 2017, Open Images, Roboflow, custom captures |
| **Splits** | train 143,358 · val 11,634 · test 12,663 images (deterministic, leakage-checked) |
| **Backward compatible** | rule_engine / safety.py class references never renumbered (`breaking_changes: none`) |

Six classes currently have zero training images (`white_cane, guide_dog, elevator, entrance, exit, bollard`) — tracked as explicit gaps in `ml/training/dataset_manifest.yaml`.

The pipeline is built from small, gated scripts under `ml/training/`:

1. **discover / download** — COCO, Open Images, Roboflow, supplemental sources
2. **convert** — source formats → unified YOLO format (`convert_coco.py`, `convert_new_classes.py`)
3. **map** — one authoritative label mapping (`class_mapping.json`, explicit aliases only — never fuzzy-matched)
4. **merge + split** — deterministic hash-based train/val/test
5. **dedup + quarantine** — perceptual-hash duplicate removal; zero-area labels quarantined (reversible, never deleted)
6. **validate** — `validate_dataset.py` must exit 0 (critical findings abort training)
7. **train** — `train_halovision.py` (2-phase, crash-safe resume)
8. **gate** — `validate_model.py` (95-class checkpoint check) + `integration_check.py`

## Quick start

### Backend

```powershell
# 1. environment
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. configuration
copy .env.example .env        # set SECRET_KEY, CORS_ORIGINS, Azure TTS keys (optional)

# 3. run
.venv\Scripts\python.exe run.py
# → http://127.0.0.1:8000  (health: /health, API docs: /docs)
```

### Frontend

```powershell
cd frontend
npm install
npm run dev          # https://localhost:5173 (proxies /api, /ws, /rtc → :8000)
npm run build        # production bundle in frontend/dist
```

### Tests

```powershell
.venv\Scripts\python.exe -m pytest tests        # 83 tests: API, auth, rule engine,
                                                # perception math, websocket, speech
```

### Try the model on images

```powershell
.venv\Scripts\python.exe ml\training\predict_images.py --source path\to\image.jpg
# uses yolo26_halovision_v2\best.pt when present, falls back to yolo26n.pt
```

## Training a new model

```powershell
# full run (dataset validation gate runs first; aborts on critical findings)
.venv\Scripts\python.exe ml\training\train_halovision.py

# options
.venv\Scripts\python.exe ml\training\train_halovision.py --skip-val-check
.venv\Scripts\python.exe ml\training\train_halovision.py --phases 1|2|both
```

- Outputs land on **D:** (`D:\HaloVisionData\...`) — checkpoints, logs, statistics; the repo never stores weights (`*.pt` is gitignored).
- Interrupted runs are safe: the trainer **skips a completed phase 1** and resumes phase 2 from its `best.pt`.
- Long runs are supervised by a Windows scheduled task (`HaloVisionTrain`) with an auto-restarting wrapper.

## Project structure

```
HaloVision/
├── App/                    # FastAPI backend
│   ├── main.py             #   app wiring, CORS, health
│   ├── api/                #   auth, admin, billing/rbac, migrations
│   ├── core/               #   rule_engine, event_bus, speech, safety, TTS
│   ├── Perception/         #   perception_system, tracker, depth, model_manager
│   └── schemas/            #   shared contracts
├── frontend/               # React + Vite + Tailwind SPA
├── ml/training/            # end-to-end dataset + training pipeline
│   ├── class_mapping.json  #   authoritative label mapping (frozen IDs)
│   ├── dataset_manifest.yaml  # sources, revisions, decisions, gaps
│   ├── validate_dataset.py #   dataset gate (exit-code enforced)
│   ├── train_halovision.py #   2-phase trainer with resume
│   ├── validate_model.py   #   95-class checkpoint gate
│   └── predict_images.py   #   image inference tester
├── tests/                  # 83 pytest tests
├── models/                 # model configs (weights live on D:)
└── run.py                  # server entry point
```

## Storage layout

| Where | What |
|---|---|
| `C:` (repo) | code, configs, docs, tests |
| `D:\HaloVisionData\` | datasets, runs, checkpoints, logs, quarantine caches |

One module (`ml/training/hv_paths.py`) is the single source of truth for every path.

## Roadmap

- [ ] Finish v2 training (95-class `best.pt`)
- [ ] Collect data for the 6 zero-annotation classes
- [ ] On-device export (ONNX) + latency benchmark (`bench_vision.py`)
- [ ] Alert-threshold tuning from real walking recordings

## Notes

- **Privacy:** no video or audio ever leaves the machine.
- **Reversibility:** dataset operations only ever *quarantine* — nothing is deleted (`D:\HaloVisionData\cache\*`).
- **Weights & datasets are intentionally not in git.**
