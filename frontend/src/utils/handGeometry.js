/**
 * Hand landmark geometry: finger definitions, joint math, extension state
 * and per-finger bounding boxes.
 *
 * Uses the standard 21 MediaPipe hand landmarks:
 *   0 wrist; 1..4 thumb; 5..8 index; 9..12 middle; 13..16 ring; 17..20 pinky
 * Landmarks are `{x, y}` in normalized coords (0..1).
 */

export const FINGER_ORDER = ["thumb", "index", "middle", "ring", "pinky"]

// Joint indices per finger — every finger includes its TIP as the last entry.
export const FINGER_LANDMARKS = {
  thumb: [1, 2, 3, 4],
  index: [5, 6, 7, 8],
  middle: [9, 10, 11, 12],
  ring: [13, 14, 15, 16],
  pinky: [17, 18, 19, 20],
}

// tip index per finger
export const FINGER_TIP = {
  thumb: 4,
  index: 8,
  middle: 12,
  ring: 16,
  pinky: 20,
}

export const WRIST = 0
export const THUMB_CMC = 1
export const INDEX_MCP = 5
export const MIDDLE_MCP = 9

// Straightness threshold (degrees) at a joint — fingers straighter than
// this count as extended. Straight real-world fingers give 170-180 deg at
// the PIP; folded ones land below ~150.
const EXTEND_ANGLE_PIP = 160
const EXTEND_ANGLE_DIP = 152
const EXTEND_ANGLE_THUMB_IP = 150

// ---------------------------------------------------------------------------
// Vector math (normalized coords; scale-invariant thanks to ratios)
// ---------------------------------------------------------------------------

export function sub(a, b) {
  return { x: a.x - b.x, y: a.y - b.y }
}

export function dot(a, b) {
  return a.x * b.x + a.y * b.y
}

export function len(v) {
  return Math.hypot(v.x, v.y)
}

export function dist(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/** Interior angle at vertex b formed by a->b->c, in degrees (0..180). */
export function jointAngle(a, b, c) {
  const v1 = sub(a, b)
  const v2 = sub(c, b)
  const l1 = len(v1)
  const l2 = len(v2)
  if (l1 < 1e-9 || l2 < 1e-9) return 180
  const cos = Math.min(1, Math.max(-1, dot(v1, v2) / (l1 * l2)))
  return (Math.acos(cos) * 180) / Math.PI
}

/** Palm scale: distance wrist -> middle MCP. All thresholds stay relative. */
export function palmSize(hand) {
  return dist(hand[WRIST], hand[MIDDLE_MCP]) || 1e-9
}

// ---------------------------------------------------------------------------
// Extension state
// ---------------------------------------------------------------------------

/**
 * Whether a finger is extended, judged by joint straightness (rotation-proof
 * — never compares raw screen coordinates, so the hand may rotate freely).
 *
 * Returns `{ extended, angle }` where `angle` is the straighter of the two
 * measured joints (a soft confidence proxy).
 */
export function fingerExtension(hand, fingerName) {
  const idx = FINGER_LANDMARKS[fingerName]

  if (fingerName === "thumb") {
    // Thumb: angle at the IP joint (2 -> 3 -> 4).
    const ip = jointAngle(hand[idx[1]], hand[idx[2]], hand[idx[3]])
    return { extended: ip >= EXTEND_ANGLE_THUMB_IP, angle: ip }
  }

  // Long fingers: PIP (mcp->pip->dip) must be straight AND the DIP
  // (pip->dip->tip) nearly straight — catches "folded" and "half-curled".
  const pip = jointAngle(hand[idx[0]], hand[idx[1]], hand[idx[2]])
  const dip = jointAngle(hand[idx[1]], hand[idx[2]], hand[idx[3]])
  const extended = pip >= EXTEND_ANGLE_PIP && dip >= EXTEND_ANGLE_DIP

  return { extended, angle: Math.min(pip, dip) }
}

export function analyzeFingers(hand) {
  const size = palmSize(hand)
  const fingers = {}

  for (const name of FINGER_ORDER) {
    const idx = FINGER_LANDMARKS[name]
    const { extended, angle } = fingerExtension(hand, name)
    const tipIdx = FINGER_TIP[name]
    const tip = hand[tipIdx]

    // Small padded box around this finger's own joints (normalized coords).
    const xs = idx.map((i) => hand[i].x)
    const ys = idx.map((i) => hand[i].y)
    const padX = size * 0.28
    const padY = size * 0.28

    fingers[name] = {
      landmarks: idx.map((i) => ({ ...hand[i] })),
      tip: { x: tip.x, y: tip.y },
      bbox: [
        Math.max(0, Math.min(...xs) - padX),
        Math.max(0, Math.min(...ys) - padY),
        Math.min(1, Math.max(...xs) + padX),
        Math.min(1, Math.max(...ys) + padY),
      ],
      extended,
      angle: Math.round(angle),
    }
  }

  return { fingers, palmSize: size }
}