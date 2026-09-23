# =============================================================================
# FILE: App/core/contracts.py
# ROLE: Data contracts — shared data structures that flow between all layers.
#
# WHAT THIS FILE DOES:
#   Defines the dataclasses that are the "currency" of the event-driven pipeline.
#   Every layer communicates by producing and consuming these structures.
#
# WHY THIS EXISTS:
#   Clear data contracts prevent tight coupling between layers.
#   Each layer only needs to know the structure of the data it receives,
#   not how that data was produced.
#
# KEY DATA FLOW THROUGH THESE CONTRACTS:
#
#   ObjectData (per detected object)
#       ↑ Created by PerceptionSystem._build_object_data()
#       ↓ Consumed by ReasoningLayer, send_detections()
#
#   TrackingState (complete frame state)
#       ↑ Created by PerceptionSystem.process_frame()
#       ↓ Wrapped in SystemEvent, published to EventBus
#
#   ThreatAssessment (per object's threat evaluation)
#       ↑ Created by ReasoningLayer._evaluate_threats()
#       ↓ Consumed by RuleEngine._handle_threat()
#
#   SceneGraph (spatial relationships between objects)
#       ↑ Created by ReasoningLayer._build_scene_graph()
#       ↓ Consumed by RuleEngine._handle_navigation()
#
#   FrameAnalysis (combined scene + threats)
#       ↑ Created by ReasoningLayer._emit_frame_analysis()
#       ↓ Published as "FRAME_ANALYSIS_READY" event → RuleEngine
#
#   SpeechIntent (what should be spoken)
#       ↑ Created by RuleEngine._create_intent()
#       ↓ Published as "SPEECH_INTENT_CREATED" event → SpeechScheduler
#
#   SystemEvent (generic event envelope)
#       ↑ Created by PerceptionSystem, ReasoningLayer, RuleEngine
#       ↓ Published to EventBus → fans out to subscribed handlers
# =============================================================================

from dataclasses import dataclass
from typing import Tuple, Optional, Dict, List


@dataclass
class ObjectData:
    """A single detected object with all its properties.

    Created by: PerceptionSystem._build_object_data()
    Used by:     ReasoningLayer, send_detections(), RuleEngine

    Contains raw detection data (from YOLO) plus enrichment (depth, position).
    Velocity and direction are filled in later by ReasoningLayer.
    """
    object_id: str                    # Unique ID: "track_{track_id}"
    class_name: str                   # e.g. "person", "car", "chair"
    confidence: float                 # Detection confidence (0.0 to 1.0)
    bbox: Tuple[int, int, int, int]   # Bounding box (x1, y1, x2, y2) in pixels
    centroid: Tuple[int, int]         # Center point (cx, cy) in pixels
    depth_norm: float                 # Normalized depth (0-1, from MiDaS)
    depth_confidence: float           # Depth confidence (0 or 1)
    horizontal_offset_norm: float     # Left/right position (-1 to +1)
    velocity_norm: Optional[float] = None       # Speed toward/away from user (filled by ReasoningLayer)
    direction_vector: Optional[Tuple[float, float]] = None  # Movement direction (filled by ReasoningLayer)
    is_stationary: bool = False       # Whether object is stationary (filled by ReasoningLayer)
    is_moving_towards_user: bool = False  # Whether approaching (filled by ReasoningLayer)
    first_seen_ts: float = 0.0        # Timestamp when first detected
    last_seen_ts: float = 0.0         # Timestamp of most recent detection
    frame_timestamp: float = 0.0      # Timestamp of the frame this was detected in
    last_announced_ts: float = 0.0    # Last TTS announcement timestamp (for cooldown)
    announce_cooldown_sec: float = 5.0  # Minimum seconds between announcements
    track_id: int = -1                # ByteTrack-assigned persistent track ID


@dataclass
class TrackingState:
    """Complete state of all tracked objects in a single frame.

    Created by: PerceptionSystem.process_frame()
    Used by:     Wrapped in SystemEvent → EventBus → ReasoningLayer, send_detections()

    This is the primary output of the Perception Layer.
    """
    active_objects: Dict[str, ObjectData]  # object_id → ObjectData
    frame_id: int                          # Monotonically increasing frame counter
    timestamp: float                       # Frame timestamp (time.time())
    perf: Optional[Dict] = None            # Performance stats (fps, infer_ms, depth_ms)
    frame_width: int = 0                   # Frame width in pixels
    frame_height: int = 0                  # Frame height in pixels


@dataclass
class ThreatAssessment:
    """Threat evaluation for a single detected object.

    Created by: ReasoningLayer._evaluate_threats()
    Used by:     RuleEngine._handle_threat()

    Threat levels:
        0 = Safe (no alert needed)
        1 = Low (minor concern)
        2 = Medium (approaching, worth announcing)
        3 = High (very close, approaching fast, or intercepting — urgent)
    """
    object_id: str                # Which object this threat is about
    class_name: str               # Object class (e.g. "car", "person")
    depth_norm: float             # How close (0-1)
    velocity_norm: float          # Speed toward/away from user
    threat_level: int             # 0-3 (0=safe, 3=urgent)
    reason: str                   # Why this threat level ("approaching", "intercepting", "close")
    priority: int                 # Announcement priority (0=highest, 2=lowest)
    timestamp: float              # When this assessment was made
    horizontal_offset_norm: float # Left/right position
    depth_bucket: str             # "very_close", "near", or "far"


@dataclass
class SceneRelation:
    """A spatial relationship between two objects in the scene.

    Created by: ReasoningLayer._build_scene_graph()
    Used by:     RuleEngine to generate spatial navigation text

    Examples:
        - ("track_1", "left", "USER") — object is to the left of the user
        - ("track_1", "very_close", "USER") — object is very close to the user
    """
    subject_id: str        # The object this relation is about
    relation_type: str     # "left", "right", "ahead", "very_close", "near", "far"
    object_id: str         # Usually "USER" (relative to the camera/user)
    confidence: float      # Confidence in this spatial relationship


@dataclass
class SceneGraph:
    """Complete scene understanding — all objects and their spatial relationships.

    Created by: ReasoningLayer._build_scene_graph()
    Used by:     RuleEngine to generate navigation/speech text

    The scene graph is a structured representation of the 3D scene:
    - objects: all detected objects (including a virtual "USER" object)
    - relations: spatial relationships between objects and the user
    """
    objects: Dict[str, ObjectData]     # All objects (including "USER")
    relations: List[SceneRelation]     # Spatial relationships
    global_summary: Optional[str] = None  # Optional scene summary text
    timestamp: float = 0.0             # When this graph was built


@dataclass
class FrameAnalysis:
    """Combined analysis of a single frame — scene graph + threats.

    Created by: ReasoningLayer._emit_frame_analysis()
    Published as: "FRAME_ANALYSIS_READY" event → RuleEngine

    This is the primary output of the Reasoning Layer.
    It combines spatial understanding (scene graph) with safety assessment (threats).
    """
    frame_id: int                        # Which frame this analysis is for
    timestamp: float                     # Frame timestamp
    scene_graph: SceneGraph              # Spatial relationships
    threats: List[ThreatAssessment]      # Threat evaluations


@dataclass
class ModeState:
    """Current operating mode of the system.

    Updated by: RuleEngine._handle_command() when user sends voice commands
    Used by:     RuleEngine to decide which speech mode to use

    Modes:
        - navigation_mode: describe nearby objects for orientation
        - search_mode: find a specific object type
        - description_mode: describe the scene in detail
        - threat_mode: focus on threat announcements only
    """
    navigation_mode: bool = True
    description_mode: bool = False
    search_mode: bool = False
    threat_mode: bool = False
    search_target: Optional[str] = None  # What to search for (e.g. "chair")
    muted: bool = False
    last_user_command_ts: float = 0.0


@dataclass
class SpeechIntent:
    """A unit of speech to be synthesized and spoken.

    Created by: RuleEngine._create_intent()
    Published as: "SPEECH_INTENT_CREATED" event → SpeechScheduler

    Contains everything needed to synthesize speech:
    - text: what to say
    - priority: ordering (0=highest)
    - category: for deduplication ("threat", "info", "search")
    - expiry: intents expire if not spoken in time
    """
    intent_id: str                      # Unique identifier
    category: str                       # "threat", "info", "search"
    text: str                           # What to say
    priority: int                       # 0=highest, lower number = higher priority
    related_object_id: Optional[str]    # Which object this speech is about
    created_ts: float                   # When this intent was created
    expires_ts: float                   # When this intent expires (too old to speak)
    suppress_if_duplicate: bool = True  # Skip if same text was recently spoken


@dataclass
class SystemEvent:
    """Generic event envelope — the message format for the EventBus.

    Created by: PerceptionSystem, ReasoningLayer, RuleEngine
    Published to: AsyncEventBus → fans out to subscribed handlers

    Every component in the pipeline communicates by creating and
    publishing SystemEvents. The event_type determines which handlers
    receive the event.
    """
    event_id: str       # Unique event identifier (UUID)
    event_type: str     # Determines which handlers run (e.g. "PERCEPTION_FRAME_READY")
    payload: any        # The actual data (TrackingState, FrameAnalysis, SpeechIntent, etc.)
    priority: int       # Event priority (lower = more urgent)
    timestamp: float    # When this event was created
