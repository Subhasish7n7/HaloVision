# =============================================================================
# FILE: App/core/safety.py
# ROLE: Safety constants — single source of truth for all threat thresholds.
#
# WHAT THIS FILE DOES:
#   Defines all safety-related constants from the HaloVision SRS document.
#   Every module that evaluates threats or depth imports from this file.
#
# WHY THIS EXISTS:
#   Centralizes all safety constants so they can be:
#   - Changed in one place (with SRS justification)
#   - Overridden by admin system settings (future)
#   - Audited against the SRS document
#
# WHO IMPORTS THIS:
#   - ReasoningLayer: uses thresholds for threat evaluation
#   - RuleEngine: uses DANGEROUS_CLASSES for "Warning" prefix
#   - PerceptionSystem: uses DEPTH_VERY_CLOSE, DEPTH_NEAR for search
#   - main.py: uses DEPTH_VERY_CLOSE, DEPTH_NEAR for scene description
#
# SRS REFERENCES:
#   - Distance buckets: SRS §4.3.4, annexure G
#   - Motion escalation gates: SRS §4.3.4
#   - Risk score weights: SRS §4.3.3
#   - Dangerous classes: SRS §4.3.5
# =============================================================================

"""Single source of truth for safety/threat thresholds, taken verbatim from the
HaloVision SRS (SRSNewDocsLast, 2026) sections 4.3.3 / 4.3.4 and its annexes.

Any change here must be justified by an SRS update (or an admin overridable
system setting); the pipeline modules import from this module only.
"""

# --- Distance buckets (normalized MiDaS depth) · SRS §4.3.4, annexure G ---
# depth >= DEPTH_VERY_CLOSE  -> "very close" (level 3 if fast/intercepting)
# depth >= DEPTH_NEAR        -> "near" (level 2 if fast/intercepting)
# otherwise                  -> "far"
DEPTH_VERY_CLOSE = 0.60
DEPTH_NEAR = 0.35

# --- Motion escalation gates · SRS §4.3.4 ---
# These velocity thresholds determine when depth+velocity triggers higher threat:
# very_close + (velocity > HIGH_SPEED or intercept)        -> level 3
# near       + (velocity > MED_SPEED  or intercept)        -> level >= 2
VELOCITY_HIGH = 0.05
VELOCITY_MED = 0.03

# --- Risk score weights · SRS §4.3.3 ---
# risk = W_PROXIMITY * proximity_score + W_VELOCITY * velocity_score + W_ALIGNMENT * alignment_score
W_PROXIMITY = 0.5    # Closer objects are more dangerous
W_VELOCITY = 0.3     # Faster approach = higher risk
W_ALIGNMENT = 0.2    # More centered on user = higher risk

# --- Risk thresholds for the base level (SRS threat levels 0-3) ---
# risk < 0.15 → level 0 (safe)
# risk < 0.35 → level 1 (low)
# risk < 0.60 → level 2 (medium)
# risk >= 0.60 → level 3 (high)
RISK_LEVEL_0 = 0.15
RISK_LEVEL_1 = 0.35
RISK_LEVEL_2 = 0.60

# --- Classes that trigger the spoken "Warning," prefix at level 3 · SRS §4.3.5 ---
# Vehicles pose the highest risk to blind/visually impaired users
DANGEROUS_CLASSES = frozenset({"car", "bus", "truck", "motorcycle", "bicycle"})
