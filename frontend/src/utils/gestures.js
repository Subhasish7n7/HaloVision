/**
 * Gesture recognition built purely on hand-landmark geometry.
 *
 * Gestures are inferred from finger extension states and *relative* landmark
 * distances (always scaled by palm size) — never from absolute screen
 * coordinates — so they keep working when the hand moves or rotates.
 */
import { FINGER_TIP, dist, palmSize, WRIST } from "./handGeometry"

const PINCH_RATIO = 0.55 // thumb<->index tip distance vs palm size
const PEACE_MIN_TIP_GAP = 0.35 // index/middle tip separation vs palm size

/**
 * @param {Array} hand 21 normalized landmarks
 * @param {Object} fingers analyzeFingers(hand) result
 * @returns {{ name: string, confidence: number }}
 *          name is one of: open_palm, fist, thumbs_up, point, peace,
 *          ok, none
 */
export function detectGesture(hand, fingers) {
  const e = {
    thumb: fingers.thumb.extended,
    index: fingers.index.extended,
    middle: fingers.middle.extended,
    ring: fingers.ring.extended,
    pinky: fingers.pinky.extended,
  }

  const size = fingers.palmSize || palmSize(hand)

  // OK / pinch: a *straight* thumb whose tip nearly touches the index tip
  // (scale-relative). A folded thumb tucked to the palm never qualifies,
  // which separates OK from a plain pointing hand.
  const thumbIndexGap =
    dist(hand[FINGER_TIP.thumb], hand[FINGER_TIP.index]) / size
  if (fingers.thumb.angle >= 150 && thumbIndexGap < PINCH_RATIO) {
    return { name: "ok", confidence: 0.9 }
  }

  // Open palm.
  if (e.thumb && e.index && e.middle && e.ring && e.pinky) {
    return { name: "open_palm", confidence: 0.95 }
  }

  // Fist (all folded).
  if (!e.thumb && !e.index && !e.middle && !e.ring && !e.pinky) {
    return { name: "fist", confidence: 0.9 }
  }

  // (Layout is geometry-based, so a raised thumb is still a raised thumb
  // regardless of rotation.)
  if (e.thumb && !e.index && !e.middle && !e.ring && !e.pinky) {
    return { name: "thumbs_up", confidence: 0.85 }
  }

  // Pointing / index up.
  if (e.index && !e.middle && !e.ring && !e.pinky && !e.thumb) {
    return { name: "point", confidence: 0.88 }
  }

  // Peace / V sign: index + middle extended, others folded, tips separated.
  if (e.index && e.middle && !e.ring && !e.pinky && !e.thumb) {
    const gap =
      dist(hand[FINGER_TIP.index], hand[FINGER_TIP.middle]) / size
    if (gap >= PEACE_MIN_TIP_GAP) {
      return { name: "peace", confidence: 0.85 }
    }
  }

  return { name: "none", confidence: 0 }
}

/** User-facing label for a gesture name. */
export function gestureLabel(name) {
  const labels = {
    open_palm: "OPEN PALM",
    fist: "FIST",
    thumbs_up: "THUMBS UP",
    point: "POINTING",
    peace: "PEACE",
    ok: "OK",
    none: "",
  }
  return labels[name] || ""
}