"""Unit tests for perception pipeline — IoU, DIoU, deduplication."""
import os
import sys
import numpy as np
import pytest

# Set test environment
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")

from App.Perception.perception_system import PerceptionSystem
from App.core.contracts import ObjectData


def _make_obj(object_id, bbox, class_name="person", confidence=0.9, depth_norm=0.5, h_offset=0.0):
    """Helper to create an ObjectData for testing."""
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    return ObjectData(
        object_id=object_id,
        class_name=class_name,
        confidence=confidence,
        bbox=tuple(float(v) for v in bbox),
        centroid=(float(cx), float(cy)),
        depth_norm=depth_norm,
        depth_confidence=0.8,
        horizontal_offset_norm=h_offset,
        velocity_norm=None,
        direction_vector=None,
        is_stationary=False,
        is_moving_towards_user=False,
        first_seen_ts=0.0,
        last_seen_ts=0.0,
        frame_timestamp=0.0,
        track_id=1,
    )


class TestIoU:
    def test_identical_boxes(self):
        box = (10, 10, 50, 50)
        iou = PerceptionSystem._iou(box, box)
        assert abs(iou - 1.0) < 1e-6

    def test_no_overlap(self):
        a = (0, 0, 10, 10)
        b = (20, 20, 30, 30)
        iou = PerceptionSystem._iou(a, b)
        assert iou == 0.0

    def test_partial_overlap(self):
        a = (0, 0, 20, 20)
        b = (10, 10, 30, 30)
        iou = PerceptionSystem._iou(a, b)
        # Intersection = 10x10 = 100, Union = 400+400-100 = 700
        expected = 100 / 700
        assert abs(iou - expected) < 1e-6

    def test_contained_box(self):
        outer = (0, 0, 100, 100)
        inner = (25, 25, 75, 75)
        iou = PerceptionSystem._iou(outer, inner)
        # Intersection = 2500, Union = 10000
        assert abs(iou - 0.25) < 1e-6

    def test_symmetry(self):
        a = (0, 0, 20, 20)
        b = (10, 10, 30, 30)
        assert abs(PerceptionSystem._iou(a, b) - PerceptionSystem._iou(b, a)) < 1e-9


class TestDIoU:
    def test_identical_boxes(self):
        box = (10, 10, 50, 50)
        diou = PerceptionSystem._diou(box, box)
        assert abs(diou - 1.0) < 1e-6

    def test_no_overlap(self):
        a = (0, 0, 10, 10)
        b = (100, 100, 110, 110)
        diou = PerceptionSystem._diou(a, b)
        assert diou < 0

    def test_partial_overlap(self):
        a = (0, 0, 20, 20)
        b = (10, 10, 30, 30)
        diou = PerceptionSystem._diou(a, b)
        assert -1 <= diou <= 1


class TestDedupeOverlapping:
    def test_no_duplicates(self):
        ps = PerceptionSystem.__new__(PerceptionSystem)
        ps.tracker = None
        ps.depth_provider = None
        ps.frame_id = 0
        ps.first_seen = {}
        ps.last_depth = None
        ps.last_spoken = ""
        ps._last_infer_ms = 0.0
        ps._fps = 0.0
        ps._perf_last = None

        objs = {
            "track_1": _make_obj("track_1", (10, 10, 50, 50)),
            "track_2": _make_obj("track_2", (200, 200, 250, 250)),
        }
        result = ps._dedupe_overlapping(objs)
        assert len(result) == 2

    def test_removes_duplicates(self):
        ps = PerceptionSystem.__new__(PerceptionSystem)
        ps.tracker = None
        ps.depth_provider = None
        ps.frame_id = 0
        ps.first_seen = {}
        ps.last_depth = None
        ps.last_spoken = ""
        ps._last_infer_ms = 0.0
        ps._fps = 0.0
        ps._perf_last = None

        # Nearly identical boxes (high DIoU)
        objs = {
            "track_1": _make_obj("track_1", (10, 10, 50, 50), confidence=0.9),
            "track_2": _make_obj("track_2", (12, 12, 52, 52), confidence=0.7),
        }
        result = ps._dedupe_overlapping(objs)
        assert len(result) == 1
        assert "track_1" in result  # Higher confidence kept


class TestBuildObjectData:
    def test_returns_none_on_exception(self):
        ps = PerceptionSystem.__new__(PerceptionSystem)
        ps.tracker = None
        ps.depth_provider = None
        ps.frame_id = 0
        ps.first_seen = {}
        ps.last_depth = None
        ps.last_spoken = ""
        ps._last_infer_ms = 0.0
        ps._fps = 0.0
        ps._perf_last = None

        # Pass invalid track object
        result = ps._build_object_data(
            track=None,
            depth_map=None,
            frame_width=640,
            frame_height=480,
            timestamp=0.0,
        )
        assert result is None
