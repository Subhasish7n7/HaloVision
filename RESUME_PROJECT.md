# HaloVision — Resume Project Entry

**Repo:** https://github.com/Alex132109/HaloVisionV2.git

---

## Copy-Paste Ready

HaloVision — https://github.com/Alex132109/HaloVisionV2.git
Built a real-time assistive navigation system for visually impaired users that speaks aloud what is around the user.
Designed an event-driven architecture for low-latency processing using perception, reasoning, and decision layers connected through a custom async EventBus.
Implemented object detection and tracking (YOLOv8/YOLO26, ByteTrack) with monocular depth estimation (MiDaS) running asynchronously to provide proximity and spatial awareness.
Developed a reasoning pipeline that computes object velocity, intercept course, and left/center/right position to detect dynamic threats (levels 0-3) in real time.
Engineered a rule-based system with prioritized alerts, cooldowns, duplicate suppression, and multi-mode support (navigation, threat, search, scene description).
Built live camera streaming to the backend over WebRTC (aiortc) with a JPEG-over-WebSocket fallback and latest-frame processing to bound latency.
Enabled real-time two-way communication using WebSockets — bounding boxes, labels, and threat data to the frontend; TTS audio and speech text back to the user.
Engineered a custom 95-class dataset (167k images / 955k annotations: COCO baseline + 15 accessibility classes) with conversion, dedup, and automated validation pipeline.
Developed a React frontend with live bbox overlays on the camera feed, detection panel, WebRTC client, MediaPipe hand-gesture control, and browser speech fallback.
Added JWT authentication, role-based access control, PostgreSQL persistence, Stripe billing, an admin dashboard, and Azure/edge TTS with graceful fallbacks.
TechStack: Python, FastAPI, WebSockets, WebRTC (aiortc), Ultralytics YOLOv8/YOLO26, ByteTrack, MiDaS, OpenCV, PyTorch, React, Vite, Tailwind CSS, PostgreSQL, SQLAlchemy, JWT, Stripe, pyttsx3/edge-tts, pytest, Docker

---

## Shorter Version (if space is tight)

HaloVision — https://github.com/Alex132109/HaloVisionV2.git
Built a real-time assistive navigation system for visually impaired users.
Designed an event-driven architecture for low-latency processing using perception, reasoning, and decision layers over an async EventBus.
Implemented object detection and tracking (YOLOv8/YOLO26, ByteTrack) with depth estimation (MiDaS) for spatial awareness.
Developed a reasoning pipeline to compute object motion and detect dynamic threats (0-3) in real time.
Engineered a rule-based system with prioritized alerts, cooldowns, and multi-mode support (navigation, threat, search).
Enabled real-time two-way communication using WebSockets and WebRTC: bbox overlays to the user, TTS audio guidance ("person on your left, nearby").
Built a validated 95-class, 167k-image custom dataset with a full conversion, dedup, and training pipeline.
TechStack: Python, FastAPI, WebSockets, WebRTC, YOLOv8/YOLO26, ByteTrack, MiDaS, OpenCV, React, PostgreSQL, pytest, Docker

---

### Notes
- Use **YOLOv8** alone if you want to match your example — the code wraps the Ultralytics `YOLO` API (v8-style `.track(persist=True)`), so either is defensible; the custom weights target YOLO26 (`yolo26n.pt` base).
- Training of the custom 95-class model is **prepared but not yet run** — the dataset bullet says "dataset + training pipeline," which is accurate as written.
