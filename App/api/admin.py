"""Enterprise admin REST API. Requires an admin role (checked from DB, not JWT)."""

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from App.api.database import SessionLocal
from App.api import models, auth, rbac

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

# ---------------- pydantic schemas ----------------


class UserAdminPatch(BaseModel):
    role: str = None
    plan: str = None
    is_active: bool = None
    is_banned: bool = None
    is_email_verified: bool = None
    plan_expires_at: str = None


class FlagPatch(BaseModel):
    key: str
    enabled: bool


class SettingsPatch(BaseModel):
    values: dict


# ---------------- auth dependency ----------------


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _current_admin(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    payload = auth.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if not rbac.is_admin_role(user.role):
            raise HTTPException(status_code=403, detail="Administrator access required")
        return user
    finally:
        db.close()


def require_admin():
    return _current_admin


def _require_power(access_key):
    def dep(admin: models.User = Depends(_current_admin)):
        access = rbac.build_access(admin.role)
        if not access.get(access_key, False):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return admin
    return dep


def _log(db, admin, action, target=None, detail=None):
    db.add(models.AdminActivity(
        admin_id=admin.id,
        admin_email=admin.email,
        action=action,
        target=target,
        detail=detail,
    ))


def _iso(dt):
    return dt.isoformat() if dt else None


def _count_relations(db, user):
    det = db.query(models.Detection).filter(models.Detection.user_id == user.id).count()
    sess = db.query(models.Session).filter(models.Session.user_id == user.id).count()
    alerts = db.query(models.Alert).filter(models.Alert.user_id == user.id).count()
    searches = db.query(models.SearchQuery).filter(models.SearchQuery.user_id == user.id).count()
    return det, sess, alerts, searches


def _user_brief(db, u):
    det, sess, alerts, searches = _count_relations(db, u)
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role or "free",
        "plan": u.plan or "free",
        "is_active": bool(u.is_active),
        "is_banned": bool(u.is_banned),
        "is_email_verified": bool(u.is_email_verified),
        "plan_expires_at": _iso(u.plan_expires_at),
        "last_login_at": _iso(u.last_login_at),
        "created_at": _iso(u.created_at),
        "detections": det,
        "sessions": sess,
        "alerts": alerts,
        "search_queries": searches,
    }


# ---------------- dashboard ----------------


@admin_router.get("/stats")
def dashboard_stats(
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)

    total_users = db.query(models.User).count()
    free_users = db.query(models.User).filter(models.User.role.in_(["free", None])).count()
    active_users = db.query(models.User).filter(
        models.User.is_active.is_(True), models.User.is_banned.is_(False)
    ).count()
    banned_users = db.query(models.User).filter(models.User.is_banned.is_(True)).count()
    signups_24h = db.query(models.User).filter(models.User.created_at >= day_ago).count()

    detections_total = db.query(models.Detection).count()
    detections_24h = db.query(models.Detection).filter(models.Detection.timestamp >= day_ago).count()
    sessions_total = db.query(models.Session).count()
    sessions_24h = db.query(models.Session).filter(models.Session.start_time >= day_ago).count()
    alerts_total = db.query(models.Alert).count()
    alerts_24h = db.query(models.Alert).filter(models.Alert.timestamp >= day_ago).count()
    searches_total = db.query(models.SearchQuery).count()

    detections_7d = []
    for offset in range(6, -1, -1):
        start = (now - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        count = db.query(models.Detection).filter(
            models.Detection.timestamp >= start, models.Detection.timestamp < end
        ).count()
        detections_7d.append({"date": start.strftime("%b %d"), "detections": count})

    server = {"cpu": None, "ram": None, "gpu": None, "uptime_sec": None}
    try:
        import psutil
        server.update({
            "cpu": psutil.cpu_percent(interval=0.2),
            "ram": psutil.virtual_memory().percent,
            "uptime_sec": int(time.time() - psutil.boot_time()),
        })
    except Exception:
        pass
    try:
        import torch
        server["gpu"] = {
            "available": torch.cuda.is_available(),
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "memory_used_mb": round(torch.cuda.memory_allocated(0) / 1024 / 1024) if torch.cuda.is_available() else None,
        }
    except Exception:
        server["gpu"] = {"available": False}

    return {
        "totals": {
            "users": total_users,
            "active": active_users,
            "banned": banned_users,
            "free": free_users,
            "paid": total_users - free_users,
            "signups_24h": signups_24h,
            "detections": detections_total,
            "detections_24h": detections_24h,
            "sessions": sessions_total,
            "sessions_24h": sessions_24h,
            "alerts": alerts_total,
            "alerts_24h": alerts_24h,
            "searches": searches_total,
        },
        "detections_7d": detections_7d,
        "server": server,
        "generated_at": now.isoformat(),
    }


# ---------------- users ----------------


@admin_router.get("/users")
def list_users(
    search: str = "",
    role: str = "",
    status: str = "",
    sort: str = "-id",
    page: int = 1,
    per_page: int = 20,
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    q = db.query(models.User)
    if search:
        like = f"%{search}%"
        q = q.filter((models.User.name.ilike(like)) | (models.User.email.ilike(like)))
    if role:
        q = q.filter(models.User.role == role)
    if status == "active":
        q = q.filter(models.User.is_active.is_(True), models.User.is_banned.is_(False))
    elif status == "banned":
        q = q.filter(models.User.is_banned.is_(True))

    col_map = {
        "id": models.User.id,
        "name": models.User.name,
        "email": models.User.email,
        "last_login_at": models.User.last_login_at,
        "created_at": models.User.created_at,
    }
    reverse = sort.startswith("-")
    col_name = sort.lstrip("-")
    order_col = col_map.get(col_name, models.User.id)
    order = order_col.desc() if reverse else order_col.asc()

    total = q.count()
    users = q.order_by(order).offset((max(page, 1) - 1) * per_page).limit(per_page).all()
    return {
        "total": total,
        "page": max(page, 1),
        "per_page": per_page,
        "users": [_user_brief(db, u) for u in users],
    }


@admin_router.get("/users/{user_id}")
def get_user(
    user_id: int,
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    logins = (
        db.query(models.LoginAttempt)
        .filter(models.LoginAttempt.user_id == user_id)
        .order_by(models.LoginAttempt.timestamp.desc())
        .limit(20)
        .all()
    )
    return {
        **_user_brief(db, u),
        "logins": [
            {
                "success": l.success,
                "ip": l.ip,
                "user_agent": l.user_agent,
                "timestamp": _iso(l.timestamp),
            }
            for l in logins
        ],
    }


@admin_router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    patch: UserAdminPatch,
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    if admin.id == user_id and patch.role and rbac.role_power(patch.role) > rbac.role_power(admin.role):
        raise HTTPException(status_code=403, detail="Cannot self-promote")

    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    if u.role == rbac.ROLE_SUPER_ADMIN and patch.role and patch.role != rbac.ROLE_SUPER_ADMIN:
        super_count = db.query(models.User).filter(models.User.role == rbac.ROLE_SUPER_ADMIN).count()
        if super_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last super admin")

    prev = {k: getattr(u, k) for k in ("role", "plan", "is_active", "is_banned", "is_email_verified")}
    for field in ("role", "plan", "is_active", "is_banned", "is_email_verified"):
        val = getattr(patch, field)
        if val is not None and val != "":
            setattr(u, field, val)
    if patch.plan_expires_at:
        try:
            u.plan_expires_at = datetime.fromisoformat(patch.plan_expires_at.replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid plan_expires_at")

    db.add(u)
    _log(db, admin, "user.update", target=f"user#{u.id} {u.email}", detail=str(prev))
    db.commit()
    return _user_brief(db, u)


@admin_router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.role == rbac.ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=400, detail="Cannot delete a super admin")
    email = u.email
    db.delete(u)
    db.commit()
    _log(db, admin, "user.delete", target=f"#{user_id} {email}", detail="cascade")
    return {"message": "User deleted", "id": user_id}


@admin_router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    import secrets
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    tmp = secrets.token_urlsafe(10)
    u.password = auth.hash_password(tmp)
    db.add(u)
    db.commit()
    _log(db, admin, "user.reset_password", target=f"#{user_id} {u.email}")
    return {"message": "Password reset", "temp_password": tmp}


# ---------------- feature flags / settings ----------------


@admin_router.get("/feature-flags")
def list_flags(
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    flags = db.query(models.FeatureFlag).order_by(models.FeatureFlag.category, models.FeatureFlag.key).all()
    return [
        {"key": f.key, "label": f.label, "category": f.category, "enabled": bool(f.enabled)}
        for f in flags
    ]


@admin_router.patch("/feature-flags/{key}")
def set_flag(
    key: str,
    patch: FlagPatch,
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    flag = db.query(models.FeatureFlag).filter(models.FeatureFlag.key == key).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    flag.enabled = patch.enabled
    db.add(flag)
    db.commit()
    _log(db, admin, "flag.update", target=key, detail=f"enabled={patch.enabled}")
    return {"key": key, "enabled": bool(flag.enabled)}


@admin_router.get("/settings")
def get_settings(
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    settings = db.query(models.SystemSetting).all()
    return {
        "settings": [
            {
                "key": s.key,
                "value": "••••••••••" if s.is_secret and s.value else (s.value or ""),
                "is_secret": s.is_secret,
            }
            for s in settings
        ]
    }


@admin_router.put("/settings")
def put_settings(
    body: SettingsPatch,
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    updated = []
    for key, value in (body.values or {}).items():
        existing = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
        if not existing:
            continue
        if existing.is_secret and value in ("••••••••••", "", None):
            continue
        existing.value = str(value)
        db.add(existing)
        updated.append(key)
    db.commit()
    _log(db, admin, "settings.update", detail=",".join(updated) or "none")
    return {"updated": updated}


# ---------------- activity log ----------------


@admin_router.get("/activity")
def activity(
    limit: int = 50,
    admin: models.User = Depends(require_admin()),
    db=Depends(_db),
):
    rows = db.query(models.AdminActivity).order_by(models.AdminActivity.timestamp.desc()).limit(min(limit, 200)).all()
    return {
        "activities": [
            {
                "id": a.id,
                "admin_email": a.admin_email,
                "action": a.action,
                "target": a.target,
                "detail": a.detail,
                "timestamp": _iso(a.timestamp),
            }
            for a in rows
        ]
    }