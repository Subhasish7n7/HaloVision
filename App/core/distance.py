import numpy as np


class DistanceEstimator:
    """
    Adaptive relative distance estimator.

    Converts depth values into:
        - near (0–3m)
        - medium (3–10m)
        - far (10m+)

    NOTE:
    These are semantic labels, NOT exact meters.
    """

    def __init__(self):
        # Store previous category per object
        self.history = {}

        # Number of frames required to confirm change (anti-flicker)
        self.stability_frames = 3

    def estimate(self, track_id, depth_value, depth_map):
        """
        Estimate distance category for an object.
        """

        if depth_value is None:
            return None

        # Flatten depth map
        flat = depth_map.flatten()

        # Remove extreme noise (optional but improves stability)
        flat = flat[np.isfinite(flat)]

        if flat.size == 0:
            return None

        # Adaptive thresholds (percentile-based)
        near_th = np.percentile(flat, 70)
        far_th = np.percentile(flat, 30)

        # Classification
        if depth_value >= near_th:
            category = "near (0-3m)"
        elif depth_value >= far_th:
            category = "medium (3-10m)"
        else:
            category = "far (10m+)"

        # Smooth result
        category = self._smooth(track_id, category)

        return category

    def _smooth(self, track_id, current_category):
        """
        Stabilize category changes using small buffer (no randomness).
        """

        if track_id not in self.history:
            self.history[track_id] = {
                "category": current_category,
                "count": 1
            }
            return current_category

        prev = self.history[track_id]

        # If same category → increase confidence
        if prev["category"] == current_category:
            prev["count"] += 1
            return current_category

        # If different → wait for stability
        prev["count"] -= 1

        if prev["count"] <= 0:
            prev["category"] = current_category
            prev["count"] = 1

        return prev["category"]