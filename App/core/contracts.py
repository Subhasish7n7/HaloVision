# core/contracts.py

from dataclasses import dataclass
from typing import Tuple, Optional, Dict, List


@dataclass
class ObjectData:
    object_id: str
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]
    centroid: Tuple[int, int]
    depth_m: float
    depth_confidence: float
    horizontal_offset_norm: float
    velocity_mps: Optional[float] = None
    direction_vector: Optional[Tuple[float, float]] = None
    is_stationary: bool = False
    is_moving_towards_user: bool = False
    first_seen_ts: float = 0.0
    last_seen_ts: float = 0.0
    frame_timestamp: float = 0.0
    last_announced_ts: float = 0.0
    announce_cooldown_sec: float = 5.0


@dataclass
class TrackingState:
    active_objects: Dict[str, ObjectData]
    frame_id: int
    timestamp: float


@dataclass
class ThreatAssessment:
    object_id: str
    class_name: str
    threat_level: int
    reason: str
    distance_m: float
    time_to_collision: Optional[float]
    priority: int
    timestamp: float
    horizontal_offset_norm: float
    depth_bucket: str
    velocity_mps: float




@dataclass
class SceneRelation:
    subject_id: str
    relation_type: str
    object_id: str
    confidence: float


@dataclass
class SceneGraph:
    objects: Dict[str, ObjectData]
    relations: List[SceneRelation]
    global_summary: Optional[str] = None
    timestamp: float = 0.0

@dataclass
class FrameAnalysis:
    frame_id: int
    timestamp: float
    scene_graph: SceneGraph
    threats: List[ThreatAssessment]

@dataclass
class ModeState:
    navigation_mode: bool = True
    description_mode: bool = False
    search_mode: bool = False
    search_target: Optional[str] = None
    muted: bool = False
    last_user_command_ts: float = 0.0


@dataclass
class SpeechIntent:
    intent_id: str
    category: str
    text: str
    priority: int
    related_object_id: Optional[str]
    created_ts: float
    expires_ts: float
    suppress_if_duplicate: bool = True


@dataclass
class SystemEvent:
    event_id: str
    event_type: str
    payload: object
    priority: int
    timestamp: float
