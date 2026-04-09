import numpy as np


def compute_object_depth(depth_map, bbox):

    x1, y1, x2, y2 = map(int, bbox)

    h, w = depth_map.shape

    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(w, x2)
    y2 = min(h, y2)

    roi = depth_map[y1:y2, x1:x2]

    if roi.size == 0:
        return None

    # Use median + ignore outliers
    return np.percentile(roi, 60)