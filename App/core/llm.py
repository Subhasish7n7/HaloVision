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
    from App.api import models
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    return row.value if row and row.value else default


def _get_setting_bool(db, key, default):
    val = _get_setting(db, key, "true").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def is_paid_plan(plan):
    return (plan or "free").lower() in PAID_PLANS


def build_scene_description(db, user, frame, rule_description, objects=None):
    """Return (description, used_llm). Falls back to the rule description
    when the user is not paid, the LLM is disabled, or the call fails."""
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
    import cv2
    ok, buf = cv2.imencode(".jpg", frame)
    return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None


def _object_labels(objects):
    labels = sorted({o.get("label", o.get("class_name", "?")).lower() for o in objects})
    return ", ".join(labels) or "none"


def _openai_vision(api_key, model, frame, reference, objects):
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