/**
 * HandTracker — MediaPipe HandLandmarker wrapper.
 *
 * Responsibilities:
 *  - Lazy init of the tasks-vision WASM + hand_landmarker model (local
 *    `public/` assets first, CDN fallback).
 *  - `detect(video)` -> hands[] with stable hand IDs while a hand stays
 *    visible, handedness (Left/Right), 21 normalized landmarks, per-finger
 *    geometry (boxes, tips, extension) and a gesture label.
 *  - `stop()` releases the GPU/WebGL resources.
 *
 * All inference runs locally in the browser — nothing is sent to the
 * backend, so the existing WS object-detection pipeline is untouched.
 */

import { FilesetResolver, HandLandmarker } from "@mediapipe/tasks-vision"
import { analyzeFingers } from "../utils/handGeometry"
import { detectGesture } from "../utils/gestures"

const wasmAssets =
  `${import.meta.env.BASE_URL}mediapipe/wasm`
const localTask =
  `${import.meta.env.BASE_URL}mediapipe/models/hand_landmarker.task`
const cdnTask =
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

// A hand seen again within this many ms keeps its ID.
const ABSENT_MS = 800
// Max centroid distance (fraction of palm size) for matching across frames.
const MATCH_FACTOR = 2.2

let filesetPromise = null

function loadFileset() {
  if (!filesetPromise) {
    filesetPromise = FilesetResolver.forVisionTasks(wasmAssets).catch((err) => {
      filesetPromise = null // allow a retry on next mount
      throw err
    })
  }
  return filesetPromise
}

async function loadModel(fileset, networkRetriesLeft) {
  for (const delegate of ["GPU", "CPU"]) {
    try {
      return await HandLandmarker.createFromOptions(fileset, {
        baseOptions: {
          modelAssetPath: localTask,
          delegate, // GPU via WebGL when available; CPU (wasm) otherwise
        },
        runningMode: "VIDEO",
        numHands: 2,
        minHandDetectionConfidence: 0.5,
        minHandPresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
      })
    } catch (err) {
      if (delegate === "GPU") continue // try CPU before giving up
      // Local asset missing (fresh build without the copied .task) — fall
      // back to the hosted model once, still GPU-first.
      if (networkRetriesLeft > 0) {
        return await HandLandmarker.createFromOptions(fileset, {
          baseOptions: {
            modelAssetPath: cdnTask,
            delegate: "GPU",
          },
          runningMode: "VIDEO",
          numHands: 2,
          minHandDetectionConfidence: 0.5,
          minHandPresenceConfidence: 0.5,
          minTrackingConfidence: 0.5,
        })
      }
      throw err
    }
  }
}

export class HandTracker {
  constructor({ onStatus } = {}) {
    this.landmarker = null
    this.ready = false
    this.lastError = null
    this.onStatus = onStatus || null
    this.nextHandId = 1
    this._prev = [] // { handId, center:{x,y}, size, handedness, lastSeen, onceHanded }
  }

  async init() {
    try {
      const fileset = await loadFileset()
      this.landmarker = await loadModel(fileset, 1)
      this.ready = true
      this.lastError = null
      this.onStatus?.({ ok: true })
    } catch (err) {
      this.ready = false
      this.lastError = err?.message || String(err)
      this.onStatus?.({ ok: false, error: this.lastError })
      throw err
    }
  }

  get isReady() {
    return this.ready && !!this.landmarker
  }

  /**
   * Run one inference on the live <video> element.
   * Returns normalized landmark hands (or [] when none / video not ready).
   */
  detect(video) {
    if (!this.isReady) return []
    if (!video || video.readyState < 2 || video.videoWidth === 0) return []

    let result
    try {
      result = this.landmarker.detectForVideo(video, performance.now())
    } catch {
      return [] // transient video frame issue — never crash the camera loop
    }

    const raw = (result?.landmarks || []).map(
      (lm, i) =>
        lm && {
          landmarks: lm.map((p) => ({ x: p.x, y: p.y, z: p.z || 0 })),
          worldLandmarks: result.worldLandmarks?.[i] || null,
          handedness:
            result.handednesses?.[i]?.[0]?.categoryName || "Unknown",
          handednessScore: result.handednesses?.[i]?.[0]?.score || 0,
        }
    )

    if (raw.length === 0) {
      // Evict stale hands — the caller renders nothing.
      this._prev = this._prev.filter(
        (p) => performance.now() - p.lastSeen < ABSENT_MS
      )
      return []
    }

    const now = performance.now()
    const matched = []

    for (const hand of raw) {
      const center = {
        x: hand.landmarks.reduce((s, p) => s + p.x, 0) / 21,
        y: hand.landmarks.reduce((s, p) => s + p.y, 0) / 21,
      }
      const wrist = hand.landmarks[0]
      const midMcp = hand.landmarks[9]
      const size = Math.hypot(midMcp.x - wrist.x, midMcp.y - wrist.y) || 1e-6

      // Greedy nearest-match against the previous frame's hands (palm-size
      // tolerant distance — works when hands move fast or cross).
      let best = null
      let bestCost = Infinity
      for (const p of this._prev) {
        const d = Math.hypot(p.center.x - center.x, p.center.y - center.y)
        const cost = d / Math.max(size, p.size)
        if (cost < Math.min(bestCost, MATCH_FACTOR)) {
          best = p
          bestCost = cost
        }
      }

      let handId
      let handedness = hand.handedness
      if (best) {
        handId = best.handId
        best.lastSeen = now
        best.center = center
        best.size = size
        // Handedness labels sometimes flicker between detections; keep the
        // first stable observation for the duration of the track.
        if (handedness === "Unknown" || handedness === best.onceHanded) {
          handedness = best.onceHanded || handedness
        }
        best.handedness = handedness
      } else {
        handId = this.nextHandId++
        const rec = {
          handId,
          center,
          size,
          handedness,
          onceHanded: handedness !== "Unknown" ? handedness : null,
          lastSeen: now,
        }
        this._prev.push(rec)
        best = rec
      }

      matched.push({ ...hand, handId, handedness, center })
    }

    // Drop tracks that vanished.
    this._prev = this._prev.filter(
      (p) => now - p.lastSeen < ABSENT_MS || matched.some((m) => m.handId === p.handId)
    )

    return matched.map((hand) => {
      const { fingers, palmSize: size } = analyzeFingers(hand.landmarks)
      return {
        handId: hand.handId,
        handedness: hand.handedness,
        handednessScore: hand.handednessScore,
        landmarks: hand.landmarks,
        worldLandmarks: hand.worldLandmarks,
        palmSize: size,
        fingers,
        gesture: detectGesture(hand.landmarks, fingers),
      }
    })
  }

  stop() {
    try {
      this.landmarker?.close()
    } catch {
      // already closed
    }
    this.landmarker = null
    this.ready = false
    this._prev = []
  }
}