import cv2


def draw_annotations(frame, tracks, distances, speeds, class_names):

    for track in tracks:

        track_id, x1, y1, x2, y2, cls = track

        label = class_names[cls]
        dist = distances.get(track_id, "unknown")
        speed = speeds.get(track_id, 0.0)

        # ---------------- TEXT ---------------- #
        text = f"{label} | {dist} | {speed:.2f} m/s"

        # ---------------- COLOR LOGIC ---------------- #
        color = (0, 255, 0)  # default = far (green)

        if isinstance(dist, str):
            if "near" in dist:
                color = (0, 0, 255)       # red (danger)
            elif "medium" in dist:
                color = (0, 255, 255)     # yellow

        # ---------------- DRAW BOX ---------------- #
        cv2.rectangle(
            frame,
            (int(x1), int(y1)),
            (int(x2), int(y2)),
            color,
            2,
        )

        # ---------------- TEXT BACKGROUND ---------------- #
        (text_width, text_height), _ = cv2.getTextSize(
            text,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            2,
        )

        cv2.rectangle(
            frame,
            (int(x1), int(y1) - text_height - 10),
            (int(x1) + text_width, int(y1)),
            color,
            -1,
        )

        # ---------------- PUT TEXT ---------------- #
        cv2.putText(
            frame,
            text,
            (int(x1), int(y1) - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),  # black text for contrast
            2,
        )

    return frame