"""Single source of truth for safety/threat thresholds, taken verbatim from the
HaloVision SRS (SRSNewDocsLast, 2026) sections 4.3.3 / 4.3.4 and its annexes.

Any change here must be justified by an SRS update (or an admin overridable
system setting); the pipeline modules import from this module only.
"""

# --- Distance buckets (normalized MiDaS depth) · SRS §4.3.4, annexure G ---
# depth >= DEPTH_VERY_CLOSE  -> "very close"
# depth >= DEPTH_NEAR        -> "near"
# otherwise                  -> "far"
DEPTH_VERY_CLOSE = 0.60
DEPTH_NEAR = 0.35

# --- Motion escalation gates · SRS §4.3.4 ---
# very_close + (velocity > HIGH_SPEED or intercept)        -> level 3
# near       + (velocity > MED_SPEED  or intercept)        -> level >= 2
VELOCITY_HIGH = 0.05
VELOCITY_MED = 0.03

# --- Risk score weights · SRS §4.3.3 ---
W_PROXIMITY = 0.5
W_VELOCITY = 0.3
W_ALIGNMENT = 0.2

# --- Risk thresholds for the base level (SRS threat levels 0-3) ---
RISK_LEVEL_0 = 0.15
RISK_LEVEL_1 = 0.35
RISK_LEVEL_2 = 0.60

# --- Classes that trigger the spoken "Warning," prefix at level 3 · SRS §4.3.5 ---
DANGEROUS_CLASSES = frozenset({"car", "bus", "truck", "motorcycle", "bicycle"})