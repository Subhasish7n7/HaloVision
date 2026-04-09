import time


class SpeedEstimator:
    """
    Stable velocity estimator using:
    - correct direction (positive = approaching)
    - EMA smoothing
    - noise filtering
    """

    def __init__(self):
        self.history = {}

        # tuning parameters
        self.alpha = 0.6            # smoothing (higher = faster response)
        self.min_dt = 0.05          # ignore very fast updates
        self.noise_threshold = 0.02 # ignore tiny movement
        self.max_speed = 3.0        # clamp unrealistic spikes

    def estimate(self, track_id, depth_value):
        now = time.time()

        # first observation
        if track_id not in self.history:
            self.history[track_id] = {
                "depth": depth_value,
                "time": now,
                "speed": 0.0,
            }
            return 0.0

        prev = self.history[track_id]

        dt = now - prev["time"]
        if dt < self.min_dt:
            return prev["speed"]

        # 🔥 CORRECT PHYSICS:
        # positive = approaching
        raw_speed = (prev["depth"] - depth_value) / dt

        # remove noise
        if abs(raw_speed) < self.noise_threshold:
            raw_speed = 0.0

        # smoothing
        smooth_speed = (
            self.alpha * raw_speed +
            (1 - self.alpha) * prev["speed"]
        )

        # clamp
        smooth_speed = max(min(smooth_speed, self.max_speed), -self.max_speed)

        # update
        self.history[track_id] = {
            "depth": depth_value,
            "time": now,
            "speed": smooth_speed,
        }

        return smooth_speed

    # ------------------------------
    # helper functions (clean usage)
    # ------------------------------

    @staticmethod
    def is_approaching(speed):
        return speed > 0.1

    @staticmethod
    def is_moving_away(speed):
        return speed < -0.1

    @staticmethod
    def is_static(speed):
        return abs(speed) < 0.05