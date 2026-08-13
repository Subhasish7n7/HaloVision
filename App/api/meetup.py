"""Meetup Memory REST API.

Core principle:
    CAPTURE TEMPORARILY -> UNDERSTAND -> ASK USER -> SAVE OR DELETE -> SEARCH

Phase 1 scope: data model + user workflow.
  - People (remembered profiles, face embeddings stored as JSON vectors)
  - Meetups (one row per interaction session — never per frame)
  - Conversation segments (structured, searchable transcript)
  - Memory facts (suggested / confirmed / user-edited)
  - Storage references (media kept out of the DB, referenced by path)
  - Temporary meetup sessions (rolling buffer — expire unless promoted)

Deletion is explicit and cascading: deleting a meetup removes its segments,
facts, storage references and, when the person was created solely from that
event, the person record + face embedding.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import or_, select, func as sqlfunc
from sqlalchemy.orm import Session

from App.api.database import SessionLocal
from App.api import models, auth

logger = logging.getLogger(__name__)

meetup_router = APIRouter(prefix="/api/meetup", tags=["meetup"])


# ---------------------------------------------------------------------------
# pydantic schemas
# ---------------------------------------------------------------------------
class PersonCreate(BaseModel):
    name: str
    birthday: str = None
    notes: str = None
    profile_image: str = None
    face_embedding: list = None  # float vector


class PersonUpdate(BaseModel):
    name: str = None
    birthday: str = None
    notes: str = None
    profile_image: str = None
    face_embedding: list = None


class MeetupCreate(BaseModel):
    person_id: int = None
    started_at: str = None
    ended_at: str = None
    duration_sec: int = None
    status: str = "confirmed"  # confirmed | temporary
    retention_days: int = None
    transcript: str = None
    recording_reference: str = None
    interaction_score: float = None
    source: str = "manual"
    user_notes: str = None


class MeetupPatch(BaseModel):
    person_id: int = None
    user_notes: str = None
    status: str = None        # promote temporary -> confirmed
    retention_until: str = None
    recording_reference: str = None


class SegmentCreate(BaseModel):
    speaker: str = "Person"
    timestamp_sec: float = None
    text: str


class SessionCreate(BaseModel):
    person_id: int = None
    score: float = 0.0
    expires_in_sec: int = None   # rolling buffer default from settings


class SessionPatch(BaseModel):
    person_id: int = None
    transcript_so_far: str = None
    score: float = None


class SessionSave(BaseModel):
    mode: str = "permanent"      # permanent | temporary
    retention_days: int = None
    person_id: int = None
    user_notes: str = None
    recording_reference: str = None


class MemoryFactCreate(BaseModel):
    person_id: int = None
    meetup_id: int = None
    key: str
    value: str
    status: str = "suggested"


class MemoryFactPatch(BaseModel):
    status: str = None
    value: str = None


class SettingUpdate(BaseModel):
    recording: bool = None
    conversation_memory: bool = None
    face_memory: bool = None
    auto_detect: bool = None
    temp_buffer_sec: int = None
    temporary_retention_days: int = None
    saved_retention_days: int = None


# ---------------------------------------------------------------------------
# auth dependency (mirrors main.get_current_user without a circular import)
# ---------------------------------------------------------------------------
def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    payload = auth.verify_token(token)
    if not payload or ("sub" not in payload and "user_id" not in payload):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    uid = payload.get("sub", payload.get("user_id"))
    db = SessionLocal()
    try:
        user = db.get(models.User, int(uid))
    except (TypeError, ValueError):
        user = None
    finally:
        db.close()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _parse_dt(value, default=None):
    if not value:
        return default
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return default


def _person_dict(p: models.Person):
    return {
        "id": p.id,
        "name": p.name,
        "birthday": p.birthday,
        "notes": p.notes,
        "profile_image": p.profile_image,
        "has_face_embedding": bool(p.face_embedding),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _meetup_dict(m: models.Meetup):
    return {
        "id": m.id,
        "person_id": m.person_id,
        "person_name": m.person.name if m.person else None,
        "started_at": m.started_at.isoformat() if m.started_at else None,
        "ended_at": m.ended_at.isoformat() if m.ended_at else None,
        "duration_sec": m.duration_sec,
        "status": m.status,
        "retention_until": m.retention_until.isoformat() if m.retention_until else None,
        "transcript": m.transcript,
        "recording_reference": m.recording_reference,
        "interaction_score": m.interaction_score,
        "source": m.source,
        "user_notes": m.user_notes,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _session_dict(s: models.MeetupSession):
    return {
        "id": s.id,
        "person_id": s.person_id,
        "person_name": None,
        "status": s.status,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        "transcript_so_far": s.transcript_so_far,
        "interaction_score": s.interaction_score,
    }


# ---------------------------------------------------------------------------
# Face snapshot storage (Stage 1: capture).
#
# Images live on local disk under <project>/media/face_snapshots/{user_id}/
# and are served via the /media static mount. The DB only stores the
# reference + detection metadata. Deleting a session removes both the rows
# and the files (no orphaned snapshots).
# ---------------------------------------------------------------------------
_SNAP_ROOT = Path(__file__).resolve().parents[2] / "media" / "face_snapshots"
MAX_FACES_PER_SESSION = 40  # storage stays small — few quality samples


def _face_dict(f: models.MeetupFaceDetection):
    return {
        "id": f.id,
        "session_id": f.session_id,
        "track_id": f.track_id,
        "image_url": f"/media/{f.snapshot_path}",
        "mime": f.mime,
        "size_bytes": f.size_bytes,
        "width": f.width,
        "height": f.height,
        "confidence": f.confidence,
        "quality_score": f.quality_score,
        "first_seen_at": f.first_seen_at.isoformat() if f.first_seen_at else None,
        "last_seen_at": f.last_seen_at.isoformat() if f.last_seen_at else None,
        "status": f.status,
    }


def _delete_session_faces(db: Session, session: models.MeetupSession):
    """Remove every face capture of a session AND its snapshot file on disk."""
    faces = (
        db.query(models.MeetupFaceDetection)
        .filter(models.MeetupFaceDetection.session_id == session.id)
        .all()
    )
    for f in faces:
        try:
            _SNAP_ROOT.joinpath(f.snapshot_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(f)
    return len(faces)


def _delete_meetup_cascade(db: Session, meetup: models.Meetup, user_id: int):
    """Delete a meetup and every derived row (segments, facts, storage refs).
    If the linked person was created solely from this event, remove the
    person (and their face embedding) too."""
    person = db.get(models.Person, meetup.person_id) if meetup.person_id else None

    db.query(models.ConversationSegment).filter(
        models.ConversationSegment.meetup_id == meetup.id
    ).delete(synchronize_session=False)
    db.query(models.MemoryFact).filter(
        models.MemoryFact.meetup_id == meetup.id
    ).delete(synchronize_session=False)
    db.query(models.StorageFile).filter(
        models.StorageFile.meetup_id == meetup.id
    ).delete(synchronize_session=False)

    if person and person.source_meetup_id == meetup.id:
        db.query(models.MemoryFact).filter(
            models.MemoryFact.person_id == person.id
        ).delete(synchronize_session=False)
        db.delete(person)

    db.delete(meetup)
    db.commit()


def _person_counts(db: Session, person_id: int):
    meetup_count = db.query(sqlfunc.count(models.Meetup.id)).filter(
        models.Meetup.person_id == person_id
    ).scalar() or 0
    last = db.query(models.Meetup).filter(
        models.Meetup.person_id == person_id
    ).order_by(models.Meetup.started_at.desc()).first()
    total_sec = db.query(sqlfunc.coalesce(sqlfunc.sum(models.Meetup.duration_sec), 0)).filter(
        models.Meetup.person_id == person_id
    ).scalar() or 0
    return {
        "meetup_count": meetup_count,
        "last_met_at": last.started_at.isoformat() if last and last.started_at else None,
        "total_duration_sec": int(total_sec),
    }


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
@meetup_router.get("/dashboard")
def dashboard(db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    uid = user.id

    people = db.query(models.Person).filter(models.Person.user_id == uid).order_by(models.Person.created_at.desc()).all()
    people_rows = []
    for p in people:
        row = _person_dict(p)
        row.update(_person_counts(db, p.id))
        people_rows.append(row)

    meetups = db.query(models.Meetup).filter(models.Meetup.user_id == uid).order_by(models.Meetup.started_at.desc()).limit(25).all()
    sessions = db.query(models.MeetupSession).filter(
        models.MeetupSession.user_id == uid,
        models.MeetupSession.status.in_(["active", "staged"]),
    ).order_by(models.MeetupSession.started_at.desc()).all()

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    recent = db.query(models.Meetup).filter(
        models.Meetup.user_id == uid,
        models.Meetup.started_at >= week_ago,
    ).count()

    for s in sessions:
        s.person_name = db.get(models.Person, s.person_id).name if s.person_id else None

    settings = db.query(models.MeetupSetting).filter(models.MeetupSetting.user_id == uid).first()
    if not settings:
        settings = models.MeetupSetting(user_id=uid)
        db.add(settings)
        db.commit()

    return {
        "people": people_rows,
        "people_count": len(people_rows),
        "meetups": [_meetup_dict(m) for m in meetups],
        "meetup_count": db.query(sqlfunc.count(models.Meetup.id)).filter(models.Meetup.user_id == uid).scalar(),
        "meetups_this_week": recent,
        "sessions": [_session_dict(s) for s in sessions],
        "settings": {
            "recording": settings.recording,
            "conversation_memory": settings.conversation_memory,
            "face_memory": settings.face_memory,
            "auto_detect": settings.auto_detect,
            "temp_buffer_sec": settings.temp_buffer_sec,
            "temporary_retention_days": settings.temporary_retention_days,
            "saved_retention_days": settings.saved_retention_days,
        },
    }


# ---------------------------------------------------------------------------
# PEOPLE
# ---------------------------------------------------------------------------
@meetup_router.get("/people")
def list_people(q: str = None, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    query = db.query(models.Person).filter(models.Person.user_id == user.id)
    if q:
        query = query.filter(models.Person.name.ilike(f"%{q}%"))
    rows = []
    for p in query.order_by(models.Person.name.asc()).all():
        row = _person_dict(p)
        row.update(_person_counts(db, p.id))
        rows.append(row)
    return {"people": rows}


@meetup_router.post("/people", status_code=201)
def create_person(body: PersonCreate, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    embedding = None
    if body.face_embedding is not None:
        embedding = json.dumps(body.face_embedding)
    person = models.Person(
        user_id=user.id,
        name=body.name.strip(),
        birthday=body.birthday,
        notes=body.notes,
        profile_image=body.profile_image,
        face_embedding=embedding,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    return _person_dict(person)


@meetup_router.get("/people/{person_id}")
def get_person(person_id: int, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    person = db.get(models.Person, person_id)
    if not person or person.user_id != user.id:
        raise HTTPException(status_code=404, detail="Person not found")

    meetups = db.query(models.Meetup).filter(models.Meetup.person_id == person_id).order_by(models.Meetup.started_at.desc()).all()
    facts = db.query(models.MemoryFact).filter(models.MemoryFact.person_id == person_id).order_by(models.MemoryFact.created_at.desc()).all()
    segments = (
        db.query(models.ConversationSegment)
        .join(models.Meetup)
        .filter(models.Meetup.person_id == person_id)
        .order_by(models.ConversationSegment.timestamp_sec.asc())
        .limit(200)
        .all()
    )

    return {
        **_person_dict(person),
        **_person_counts(db, person_id),
        "meetups": [_meetup_dict(m) for m in meetups],
        "facts": [
            {
                "id": f.id,
                "key": f.key,
                "value": f.value,
                "status": f.status,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in facts
        ],
        "conversation": [
            {
                "id": s.id,
                "meetup_id": s.meetup_id,
                "speaker": s.speaker,
                "timestamp_sec": s.timestamp_sec,
                "text": s.text,
            }
            for s in segments
        ],
    }


@meetup_router.patch("/people/{person_id}")
def update_person(person_id: int, body: PersonUpdate, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    person = db.get(models.Person, person_id)
    if not person or person.user_id != user.id:
        raise HTTPException(status_code=404, detail="Person not found")
    if body.name is not None:
        person.name = body.name.strip()
    if body.birthday is not None:
        person.birthday = body.birthday
    if body.notes is not None:
        person.notes = body.notes
    if body.profile_image is not None:
        person.profile_image = body.profile_image
    if body.face_embedding is not None:
        person.face_embedding = json.dumps(body.face_embedding)
    db.commit()
    db.refresh(person)
    return _person_dict(person)


@meetup_router.delete("/people/{person_id}")
def delete_person(person_id: int, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    """Forget Person: removes the profile, face embedding, every meetup and
    all derived facts/conversation/storage."""
    person = db.get(models.Person, person_id)
    if not person or person.user_id != user.id:
        raise HTTPException(status_code=404, detail="Person not found")

    meetups = db.query(models.Meetup).filter(models.Meetup.person_id == person_id).all()
    for m in meetups:
        _delete_meetup_cascade(db, m, user.id)

    db.query(models.MeetupSession).filter(models.MeetupSession.person_id == person_id).delete(synchronize_session=False)
    db.query(models.MemoryFact).filter(models.MemoryFact.person_id == person_id).delete(synchronize_session=False)
    db.delete(person)
    db.commit()
    return {"ok": True, "deleted_person": person_id, "deleted_meetups": len(meetups)}


# ---------------------------------------------------------------------------
# MEETUPS
# ---------------------------------------------------------------------------
@meetup_router.get("/meetups")
def list_meetups(
    person_id: int = None,
    status: str = None,
    limit: int = 50,
    db: Session = Depends(_db),
    user: models.User = Depends(_current_user),
):
    query = db.query(models.Meetup).filter(models.Meetup.user_id == user.id)
    if person_id:
        query = query.filter(models.Meetup.person_id == person_id)
    if status:
        query = query.filter(models.Meetup.status == status)
    rows = query.order_by(models.Meetup.started_at.desc()).limit(min(limit, 200)).all()
    return {"meetups": [_meetup_dict(m) for m in rows]}


@meetup_router.get("/meetups/{meetup_id}")
def get_meetup(meetup_id: int, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    meetup = db.get(models.Meetup, meetup_id)
    if not meetup or meetup.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meetup not found")
    segments = db.query(models.ConversationSegment).filter(
        models.ConversationSegment.meetup_id == meetup_id
    ).order_by(models.ConversationSegment.timestamp_sec.asc()).all()
    facts = db.query(models.MemoryFact).filter(models.MemoryFact.meetup_id == meetup_id).all()
    files = db.query(models.StorageFile).filter(models.StorageFile.meetup_id == meetup_id).all()
    return {
        **_meetup_dict(meetup),
        "segments": [
            {"id": s.id, "speaker": s.speaker, "timestamp_sec": s.timestamp_sec, "text": s.text}
            for s in segments
        ],
        "facts": [{"id": f.id, "key": f.key, "value": f.value, "status": f.status} for f in facts],
        "media": [{"id": f.id, "kind": f.kind, "path": f.path, "mime": f.mime, "size_bytes": f.size_bytes} for f in files],
    }


@meetup_router.post("/meetups", status_code=201)
def create_meetup(body: MeetupCreate, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    if body.person_id:
        person = db.get(models.Person, body.person_id)
        if not person or person.user_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid person_id")

    now = datetime.now(timezone.utc)
    started = _parse_dt(body.started_at, now)
    ended = _parse_dt(body.ended_at, now if body.duration_sec else None)

    retention_until = None
    if body.status == "temporary":
        days = body.retention_days
        if not days:
            setting = db.query(models.MeetupSetting).filter(models.MeetupSetting.user_id == user.id).first()
            days = setting.temporary_retention_days if setting else 1
        retention_until = now + timedelta(days=days)

    meetup = models.Meetup(
        user_id=user.id,
        person_id=body.person_id,
        started_at=started,
        ended_at=ended,
        duration_sec=body.duration_sec,
        status=body.status,
        retention_until=retention_until,
        transcript=body.transcript,
        recording_reference=body.recording_reference,
        interaction_score=body.interaction_score,
        source=body.source,
        user_notes=body.user_notes,
    )
    db.add(meetup)
    db.commit()
    db.refresh(meetup)
    return _meetup_dict(meetup)


@meetup_router.patch("/meetups/{meetup_id}")
def patch_meetup(meetup_id: int, body: MeetupPatch, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    meetup = db.get(models.Meetup, meetup_id)
    if not meetup or meetup.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meetup not found")
    if body.person_id is not None:
        person = db.get(models.Person, body.person_id)
        if not person or person.user_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid person_id")
        meetup.person_id = body.person_id
    if body.user_notes is not None:
        meetup.user_notes = body.user_notes
    if body.recording_reference is not None:
        meetup.recording_reference = body.recording_reference
    if body.status is not None:
        meetup.status = body.status
        if body.status == "confirmed":
            meetup.retention_until = None
        elif body.status == "temporary":
            setting = db.query(models.MeetupSetting).filter(models.MeetupSetting.user_id == user.id).first()
            days = setting.temporary_retention_days if setting else 1
            meetup.retention_until = datetime.now(timezone.utc) + timedelta(days=days)
    if body.retention_until is not None:
        meetup.retention_until = _parse_dt(body.retention_until)
    db.commit()
    db.refresh(meetup)
    return _meetup_dict(meetup)


@meetup_router.delete("/meetups/{meetup_id}")
def delete_meetup(meetup_id: int, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    meetup = db.get(models.Meetup, meetup_id)
    if not meetup or meetup.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meetup not found")
    _delete_meetup_cascade(db, meetup, user.id)
    return {"ok": True, "deleted_meetup": meetup_id}


@meetup_router.post("/meetups/{meetup_id}/segments", status_code=201)
def add_segment(meetup_id: int, body: SegmentCreate, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    meetup = db.get(models.Meetup, meetup_id)
    if not meetup or meetup.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meetup not found")
    seg = models.ConversationSegment(
        meetup_id=meetup_id,
        speaker=body.speaker or "Person",
        timestamp_sec=body.timestamp_sec,
        text=body.text,
    )
    db.add(seg)
    if body.timestamp_sec is not None:
        duration = max(int(body.timestamp_sec), meetup.duration_sec or 0)
        meetup.duration_sec = duration
    meetup.transcript = (meetup.transcript or "") + ("" if not meetup.transcript else "\n") + body.text
    db.commit()
    db.refresh(seg)
    return {"id": seg.id, "speaker": seg.speaker, "timestamp_sec": seg.timestamp_sec, "text": seg.text}


@meetup_router.get("/meetups/{meetup_id}/segments")
def list_segments(meetup_id: int, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    meetup = db.get(models.Meetup, meetup_id)
    if not meetup or meetup.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meetup not found")
    rows = db.query(models.ConversationSegment).filter(
        models.ConversationSegment.meetup_id == meetup_id
    ).order_by(models.ConversationSegment.timestamp_sec.asc()).all()
    return {
        "segments": [
            {"id": s.id, "speaker": s.speaker, "timestamp_sec": s.timestamp_sec, "text": s.text}
            for s in rows
        ]
    }


# ---------------------------------------------------------------------------
# MEMORY FACTS (suggested / confirmed / user-edited)
# ---------------------------------------------------------------------------
@meetup_router.get("/facts")
def list_facts(person_id: int = None, meetup_id: int = None, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    query = db.query(models.MemoryFact).join(models.Meetup).filter(models.Meetup.user_id == user.id)
    if person_id:
        query = query.filter(models.MemoryFact.person_id == person_id)
    if meetup_id:
        query = query.filter(models.MemoryFact.meetup_id == meetup_id)
    rows = query.order_by(models.MemoryFact.created_at.desc()).limit(200).all()
    return {
        "facts": [
            {"id": f.id, "person_id": f.person_id, "meetup_id": f.meetup_id, "key": f.key, "value": f.value, "status": f.status}
            for f in rows
        ]
    }


@meetup_router.post("/facts", status_code=201)
def create_fact(body: MemoryFactCreate, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    if body.person_id:
        person = db.get(models.Person, body.person_id)
        if not person or person.user_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid person_id")
    if body.meetup_id:
        meetup = db.get(models.Meetup, body.meetup_id)
        if not meetup or meetup.user_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid meetup_id")
    fact = models.MemoryFact(
        person_id=body.person_id,
        meetup_id=body.meetup_id,
        key=body.key,
        value=body.value,
        status=body.status or "suggested",
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return {"id": fact.id, "key": fact.key, "value": fact.value, "status": fact.status}


@meetup_router.patch("/facts/{fact_id}")
def patch_fact(fact_id: int, body: MemoryFactPatch, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    fact = db.get(models.MemoryFact, fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")
    if body.status is not None:
        fact.status = body.status
    if body.value is not None:
        fact.value = body.value
    db.commit()
    db.refresh(fact)
    return {"id": fact.id, "key": fact.key, "value": fact.value, "status": fact.status}


# ---------------------------------------------------------------------------
# TEMPORARY SESSIONS (rolling buffer -> confirmation UI)
# ---------------------------------------------------------------------------
@meetup_router.get("/sessions")
def list_sessions(status: str = None, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    query = db.query(models.MeetupSession).filter(models.MeetupSession.user_id == user.id)
    if status:
        query = query.filter(models.MeetupSession.status == status)
    rows = query.order_by(models.MeetupSession.started_at.desc()).limit(50).all()
    out = []
    for s in rows:
        d = _session_dict(s)
        d["person_name"] = db.get(models.Person, s.person_id).name if s.person_id else None
        out.append(d)
    return {"sessions": out}


@meetup_router.post("/sessions", status_code=201)
def create_session(body: SessionCreate, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    if body.person_id:
        person = db.get(models.Person, body.person_id)
        if not person or person.user_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid person_id")

    expires_in = body.expires_in_sec
    if not expires_in:
        setting = db.query(models.MeetupSetting).filter(models.MeetupSetting.user_id == user.id).first()
        expires_in = setting.temp_buffer_sec if setting else 20

    session = models.MeetupSession(
        user_id=user.id,
        person_id=body.person_id,
        interaction_score=body.score or 0.0,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=max(10, expires_in)),
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_dict(session)


@meetup_router.patch("/sessions/{session_id}")
def patch_session(session_id: int, body: SessionPatch, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    session = db.get(models.MeetupSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if body.person_id is not None:
        session.person_id = body.person_id
    if body.transcript_so_far is not None:
        session.transcript_so_far = body.transcript_so_far
    if body.score is not None:
        session.interaction_score = body.score
    session.last_active_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return _session_dict(session)


@meetup_router.post("/sessions/{session_id}/save", status_code=201)
def save_session(session_id: int, body: SessionSave, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    """Promote a temporary interaction into a permanent or temporary Meetup.
    Never happens without the user choosing one of the three options."""
    session = db.get(models.MeetupSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "expired":
        raise HTTPException(status_code=410, detail="Session expired - promote earlier or recreate")

    mode = body.mode if body.mode in ("permanent", "temporary") else "permanent"
    status = "confirmed" if mode == "permanent" else "temporary"

    retention_until = None
    if mode == "temporary":
        days = body.retention_days
        if not days:
            setting = db.query(models.MeetupSetting).filter(models.MeetupSetting.user_id == user.id).first()
            days = setting.temporary_retention_days if setting else 1
        retention_until = datetime.now(timezone.utc) + timedelta(days=days)

    now = datetime.now(timezone.utc)
    meetup = models.Meetup(
        user_id=user.id,
        person_id=body.person_id if body.person_id is not None else session.person_id,
        started_at=session.started_at,
        ended_at=now,
        duration_sec=max(1, int((now - session.started_at.replace(tzinfo=timezone.utc) if session.started_at.tzinfo is None else session.started_at).total_seconds())),
        status=status,
        retention_until=retention_until,
        transcript=session.transcript_so_far,
        recording_reference=body.recording_reference,
        interaction_score=session.interaction_score,
        source="auto",
        user_notes=body.user_notes,
    )
    db.add(meetup)
    session.status = "expired"
    session.expires_at = now
    db.commit()
    db.refresh(meetup)
    return {"meetup": _meetup_dict(meetup), "mode": mode}


@meetup_router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    """DELETE: immediately drop the temporary interaction + derived data
    (face snapshots + their files)."""
    session = db.get(models.MeetupSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    face_count = _delete_session_faces(db, session)
    db.delete(session)
    db.commit()
    return {"ok": True, "deleted_session": session_id, "deleted_faces": face_count}


# ---------------------------------------------------------------------------
# FACE CAPTURE (Stage 1) — snapshot upload + list, tied to a session
# ---------------------------------------------------------------------------
@meetup_router.post("/sessions/{session_id}/faces", status_code=201)
async def upload_session_face(
    session_id: int,
    file: UploadFile = File(...),
    track_id: str = Form(""),
    confidence: float = Form(0.0),
    quality: float = Form(0.0),
    width: int = Form(0),
    height: int = Form(0),
    first_seen_at: str = Form(""),
    last_seen_at: str = Form(""),
    db: Session = Depends(_db),
    user: models.User = Depends(_current_user),
):
    session = db.get(models.MeetupSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    count = (
        db.query(sqlfunc.count(models.MeetupFaceDetection.id))
        .filter(models.MeetupFaceDetection.session_id == session_id)
        .scalar() or 0
    )
    if count >= MAX_FACES_PER_SESSION:
        raise HTTPException(status_code=413, detail="Face snapshot limit reached for this session")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    user_dir = _SNAP_ROOT / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    filename = f"face_{session_id}_{uuid.uuid4().hex[:12]}.jpg"
    try:
        with open(user_dir / filename, "wb") as fh:
            fh.write(data)
    except OSError as e:
        logger.error(f"[Meetup] face snapshot write failed: {e}")
        raise HTTPException(status_code=500, detail="Could not store snapshot")

    row = models.MeetupFaceDetection(
        session_id=session_id,
        user_id=user.id,
        track_id=track_id or None,
        snapshot_path=f"face_snapshots/{user.id}/{filename}",
        mime=file.content_type or "image/jpeg",
        size_bytes=len(data),
        width=width or None,
        height=height or None,
        confidence=confidence or None,
        quality_score=quality or None,
        first_seen_at=_parse_dt(first_seen_at),
        last_seen_at=_parse_dt(last_seen_at),
        status="temporary",
    )
    db.add(row)
    session.last_active_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _face_dict(row)


@meetup_router.get("/sessions/{session_id}/faces")
def list_session_faces(session_id: int, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    session = db.get(models.MeetupSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = (
        db.query(models.MeetupFaceDetection)
        .filter(models.MeetupFaceDetection.session_id == session_id)
        .order_by(models.MeetupFaceDetection.id.asc())
        .all()
    )
    return {"faces": [_face_dict(f) for f in rows]}


# ---------------------------------------------------------------------------
# SEARCH (across people, meetups, transcripts, facts, notes)
# ---------------------------------------------------------------------------
@meetup_router.get("/search")
def search(q: str, limit: int = 20, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    if not q or not q.strip():
        return {"query": q, "people": [], "meetups": [], "segments": [], "facts": []}
    term = f"%{q.strip()}%"
    uid = user.id

    people = (
        db.query(models.Person)
        .filter(models.Person.user_id == uid, or_(models.Person.name.ilike(term), models.Person.notes.ilike(term)))
        .order_by(models.Person.name.asc())
        .limit(limit)
        .all()
    )

    meetups = (
        db.query(models.Meetup)
        .filter(
            models.Meetup.user_id == uid,
            or_(models.Meetup.transcript.ilike(term), models.Meetup.user_notes.ilike(term)),
        )
        .order_by(models.Meetup.started_at.desc())
        .limit(limit)
        .all()
    )

    segments = (
        db.query(models.ConversationSegment)
        .join(models.Meetup)
        .filter(models.Meetup.user_id == uid, models.ConversationSegment.text.ilike(term))
        .order_by(models.Meetup.started_at.desc())
        .limit(limit)
        .all()
    )

    facts = (
        db.query(models.MemoryFact)
        .join(models.Meetup)
        .filter(models.Meetup.user_id == uid, or_(models.MemoryFact.key.ilike(term), models.MemoryFact.value.ilike(term)))
        .order_by(models.MemoryFact.created_at.desc())
        .limit(limit)
        .all()
    )

    def _person_row(p):
        row = _person_dict(p)
        row.update(_person_counts(db, p.id))
        return row

    return {
        "query": q,
        "people": [_person_row(p) for p in people],
        "meetups": [_meetup_dict(m) for m in meetups],
        "segments": [
            {
                "id": s.id,
                "meetup_id": s.meetup_id,
                "speaker": s.speaker,
                "timestamp_sec": s.timestamp_sec,
                "text": s.text,
            }
            for s in segments
        ],
        "facts": [{"id": f.id, "person_id": f.person_id, "meetup_id": f.meetup_id, "key": f.key, "value": f.value, "status": f.status} for f in facts],
    }


# ---------------------------------------------------------------------------
# SETTINGS / PRIVACY CONTROLS
# ---------------------------------------------------------------------------
@meetup_router.get("/settings")
def get_settings(db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    settings = db.query(models.MeetupSetting).filter(models.MeetupSetting.user_id == user.id).first()
    if not settings:
        settings = models.MeetupSetting(user_id=user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return {
        "recording": settings.recording,
        "conversation_memory": settings.conversation_memory,
        "face_memory": settings.face_memory,
        "auto_detect": settings.auto_detect,
        "temp_buffer_sec": settings.temp_buffer_sec,
        "temporary_retention_days": settings.temporary_retention_days,
        "saved_retention_days": settings.saved_retention_days,
    }


@meetup_router.put("/settings")
def update_settings(body: SettingUpdate, db: Session = Depends(_db), user: models.User = Depends(_current_user)):
    settings = db.query(models.MeetupSetting).filter(models.MeetupSetting.user_id == user.id).first()
    if not settings:
        settings = models.MeetupSetting(user_id=user.id)
        db.add(settings)
    for field in (
        "recording",
        "conversation_memory",
        "face_memory",
        "auto_detect",
        "temp_buffer_sec",
        "temporary_retention_days",
        "saved_retention_days",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return {
        "recording": settings.recording,
        "conversation_memory": settings.conversation_memory,
        "face_memory": settings.face_memory,
        "auto_detect": settings.auto_detect,
        "temp_buffer_sec": settings.temp_buffer_sec,
        "temporary_retention_days": settings.temporary_retention_days,
        "saved_retention_days": settings.saved_retention_days,
    }


# ---------------------------------------------------------------------------
# EXPIRY SWEEPER — temporary data that was never promoted must disappear.
# Called at startup; cheap enough to run on demand too.
# ---------------------------------------------------------------------------
def sweep_expired():
    try:
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            expired_sessions = (
                db.query(models.MeetupSession)
                .filter(models.MeetupSession.status != "expired")
                .filter(models.MeetupSession.expires_at < now)
                .all()
            )
            for s in expired_sessions:
                _delete_session_faces(db, s)
                db.delete(s)
            expired_meetups = (
                db.query(models.Meetup)
                .filter(models.Meetup.status == "temporary")
                .filter(models.Meetup.retention_until < now)
                .all()
            )
            for m in expired_meetups:
                _delete_meetup_cascade(db, m, m.user_id)
            if expired_sessions or expired_meetups:
                logger.info(
                    f"[Meetup] swept {len(expired_sessions)} sessions, {len(expired_meetups)} temporary meetups"
                )
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[Meetup] sweep failed: {e}")