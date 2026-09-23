# =============================================================================
# FILE: App/core/llm.py
# ROLE: LLM scene description provider — enhanced descriptions for paid users.
#
# WHAT THIS FILE DOES:
#   Provides LLM-powered scene descriptions for paid (Pro/Pro+) users.
#   Uses OpenAI's GPT-4o-mini model to generate rich, natural-language
#   descriptions of camera scenes.
#
# FLOW:
#   main.py: /scene/analyze endpoint
#       ↓
#   build_scene_description(db, user, frame, rule_description, objects)
#       → check if user is on a paid plan
#       → check if LLM is enabled in settings
#       → check if an API key is configured
#       → if all checks pass: call OpenAI API
#       → return enhanced description (or fall back to rule-based)
#
# FALLBACK BEHAVIOR:
#   Every call is best-effort. On ANY failure (network error, API error,
#   missing key, user not paid), the system falls back to the rule-based
#   description. This ensures free/offline users always get a description.
#
# WHO CALLS THIS:
#   main.py: scene_analyze() calls build_scene_description()
#
# ADMIN CONFIGURATION:
#   All settings are in the system_settings table (admin-editable):
#   - llm_enabled: "true"/"false"
#   - llm_provider: "openai"
#   - llm_model: "gpt-4o-mini"
#   - openai_api_key: the API key
# =============================================================================

"""LLM scene-description provider for paid (Pro / Pro Plus) users.

Reads provider config from `system_settings` (admin-editable, no restart):
    llm_enabled      - "true"/"false"
    llm_provider     - "openai" (others can be added later per Phase 2)
    llm_model        - e.g. "gpt-4o-mini"
    openai_api_key   - secret key (masked in admin UI)

Every call is best-effort: on any failure the caller falls back to the
rule-based description, so free/offline behaviour is never broken.
"""
import base64
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

PAID_PLANS = ("pro", "pro_plus")
SUPPORTED_PROVIDERS = ("openai",)


def _get_setting(db, key, default):
    """Read a system setting from the database.
    Returns the value if found, otherwise returns the default."""
    from App.api import models
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    return row.value if row and row.value else default


def _get_setting_bool(db, key, default):
    """Read a boolean system setting from the database."""
    val = _get_setting(db, key, "true").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def is_paid_plan(plan):
    """Check if a plan is a paid tier (Pro or Pro Plus)."""
    return (plan or "free").lower() in PAID_PLANS


def build_scene_description(db, user, frame, rule_description, objects=None):
    """Build a scene description, using LLM for paid users.

    Input:
        db: database session
        user: User ORM object
        frame: OpenCV frame (numpy array)
        rule_description: fallback rule-based description
        objects: list of detected object dicts

    Output:
        (description, used_llm) tuple — description is the text to return,
        used_llm indicates whether the LLM was used (for tracking).

    Flow:
        1. Check if user is on a paid plan → if not, return rule-based
        2. Check if LLM is enabled in settings → if not, return rule-based
        3. Check if an OpenAI API key is configured → if not, return rule-based
        4. Call OpenAI API with the frame + reference description
        5. Return the LLM response (or fall back to rule-based on failure)
    """
    plan = (user.plan or "free").lower()
    if not is_paid_plan(plan):
        return rule_description, False

    if _get_setting_bool(db, "llm_enabled", True) is False:
        return rule_description, False

    provider = _get_setting(db, "llm_provider", "openai").lower()
    if provider not in SUPPORTED_PROVIDERS:
        return rule_description, False

    api_key = _get_setting(db, "openai_api_key", "")
    if not api_key:
        logger.info("[LLM] paid user, no API key configured - template used")
        return rule_description, False

    try:
        text = _openai_vision(
            api_key=api_key,
            model=_get_setting(db, "llm_model", "gpt-4o-mini"),
            frame=frame,
            reference=rule_description,
            objects=objects or [],
        )
        if text:
            return text, True
    except Exception as e:
        logger.warning(f"[LLM] provider call failed, falling back: {e}")

    return rule_description, False


def _encode_frame(frame):
    """Encode an OpenCV frame as a base64 JPEG string for the OpenAI API."""
    import cv2
    ok, buf = cv2.imencode(".jpg", frame)
    return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None


def _object_labels(objects):
    """Extract unique object labels from the detected objects list."""
    labels = sorted({o.get("label", o.get("class_name", "?")).lower() for o in objects})
    return ", ".join(labels) or "none"


def _openai_vision(api_key, model, frame, reference, objects):
    """Call the OpenAI Vision API to generate a scene description.

    Flow:
        1. Encode the frame as base64 JPEG
        2. Build a prompt with system instructions + user message
        3. Send to OpenAI API (GPT-4o-mini with vision)
        4. Extract and return the response text

    The system prompt is designed for blind/visually impaired users:
    - Focus on objects, layout, direction, distance
    - Speak as instructions (not descriptions)
    - Never mention "the camera"
    """
    image_b64 = _encode_frame(frame)
    if not image_b64:
        return None

    labels = _object_labels(objects)
    system = (
        "You are HaloVision's scene description engine in a wearable vision assistant "
        "for blind and visually impaired users. Describe what matters for safe "
        "orientation: objects, layout, direction (left/right/centre) and rough "
        "distance (very close / nearby / far away). Reply with 2-4 short, calm "
        "sentences spoken as instructions. Never mention 'the camera'."
    )
    user_msg = (
        f"Sensor objects: {labels}.\n"
        f"Sensor reference line: {reference or 'n/a'}\n"
        "Write a natural, spoken scene description."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_msg},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            },
        ],
        "max_tokens": 220,
        "temperature": 0.4,
    }

    # Send request to OpenAI API using urllib (no extra dependencies)
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    text = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return text.strip() or None
