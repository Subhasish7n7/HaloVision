# =============================================================================
# FILE: App/api/billing.py
# ROLE: Subscription & billing API — plan management and payment processing.
#
# WHAT THIS FILE DOES:
#   Provides subscription management endpoints:
#   - Public plan catalog (pricing info)
#   - Checkout flow (creates Razorpay order or simulated payment)
#   - Payment verification (Razorpay signature check)
#   - Subscription status
#
# PAYMENT FLOW:
#   1. Frontend calls POST /api/pricing/checkout with plan_id
#   2. If Razorpay is configured: creates a Razorpay order, returns order details
#   3. Frontend completes payment on Razorpay
#   4. Frontend calls POST /api/pricing/verify-payment with signature
#   5. Server verifies signature, activates the plan
#   6. If Razorpay is NOT configured: simulated checkout (instant activation)
#
# PLANS:
#   - free: $0 (basic features)
#   - pro: $5.99/mo (LLM scene descriptions)
#   - pro_plus: $14.99/mo (advanced models, unlimited descriptions)
#
# WHO USES THIS:
#   - Frontend pricing page: GET /api/pricing/plans
#   - Frontend checkout: POST /api/pricing/checkout
#   - Frontend payment verification: POST /api/pricing/verify-payment
#   - main.py: includes billing_router on the FastAPI app
#
# PREFIX: /api
# =============================================================================

"""Subscription & billing API. Plan prices are admin-editable via
`system_settings` (plan_pro_price, plan_pro_plus_price), so UI pricing
changes propagate instantly - no restart needed.

Payments: when Razorpay keys are configured in admin settings, checkout
creates a real Razorpay order and verifies its signature before activating.
Without keys it falls back to a simulated checkout."""

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from App.api.database import SessionLocal
from App.api import models, auth, rbac

logger = logging.getLogger(__name__)

billing_router = APIRouter(prefix="/api", tags=["billing"])

# Plan definitions — prices are read from database (admin-editable)
PLAN_IDS = ("free", "pro", "pro_plus")

PLAN_META = {
    "free": {"name": "Free", "price_key": None, "default_price": 0.0, "features": [
        "Smart object detection & navigation",
        "Rule-based scene description",
        "Voice guidance (edge TTS)",
    ]},
    "pro": {"name": "Pro", "price_key": "plan_pro_price", "default_price": 5.99, "features": [
        "Everything in Free",
        "LLM-powered scene description",
        "Higher detection confidence",
        "Priority support",
    ]},
    "pro_plus": {"name": "Pro+", "price_key": "plan_pro_plus_price", "default_price": 14.99, "features": [
        "Everything in Pro",
        "Advanced vision models",
        "Unlimited descriptions",
        "Early access to new smart features",
        "Premium support (24h)",
    ]},
}


def _db():
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_user(payload: dict, db):
    """Look up a user from a JWT payload."""
    uid = payload.get("user_id")
    if uid is None:
        return None
    return db.query(models.User).filter(models.User.id == uid).first()


def _setting_val(db, key, default):
    """Read a numeric system setting from the database."""
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    return float(row.value) if row and row.value else default


def _setting_str(db, key, default=""):
    """Read a string system setting from the database."""
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    return row.value if row and row.value else default


def _iso(dt):
    """Convert a datetime to ISO format string (or None)."""
    return dt.isoformat() if dt else None


# ---------------- Razorpay helpers ----------------

def _razorpay_config(db):
    """Get Razorpay API credentials from system settings."""
    key_id = _setting_str(db, "razorpay_key_id")
    key_secret = _setting_str(db, "razorpay_key_secret")
    return key_id, key_secret


def _razorpay_enabled(db):
    """Check if Razorpay is configured (both key_id and key_secret present)."""
    key_id, key_secret = _razorpay_config(db)
    return bool(key_id and key_secret)


def _razorpay_order(db, plan_id, user):
    """Create a Razorpay order for the given plan.
    Returns the order response dict or None on failure."""
    key_id, key_secret = _razorpay_config(db)
    if not (key_id and key_secret):
        return None

    meta = PLAN_META[plan_id]
    price = _setting_val(db, meta["price_key"], meta["default_price"])
    currency = _setting_str(db, "payment_currency", "INR").upper()
    amount_paise = int(round(price * 100))

    payload = json.dumps({
        "amount": amount_paise,
        "currency": currency,
        "receipt": f"halo_{plan_id}_{user.id}_{int(time.mktime(datetime.now(timezone.utc).timetuple()))}",
        "notes": {"user_id": str(user.id), "plan": plan_id},
    }).encode("utf-8")

    auth_header = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    req = urllib.request.Request(
        "https://api.razorpay.com/v1/orders",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_header}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _verify_razorpay_signature(key_secret, order_id, payment_id, signature):
    """Verify the Razorpay payment signature using HMAC-SHA256.
    This ensures the payment was actually processed by Razorpay."""
    expected = hmac.new(
        key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _activate_plan(db, user, plan_id, payment_method="checkout", payment_id=None, receipt=None, amount=None):
    """Activate a subscription plan for a user.

    Flow:
        1. Set user.plan and user.plan_expires_at (30 days from now)
        2. Mark any existing active subscriptions as "upgraded"
        3. Create a new Subscription row
        4. Commit to database
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)
    meta = PLAN_META[plan_id]

    user.plan = plan_id
    user.plan_expires_at = expires

    # Mark existing active subscriptions as upgraded
    for sub in db.query(models.Subscription).filter(
        models.Subscription.user_id == user.id,
        models.Subscription.status == "active",
    ).all():
        sub.status = "upgraded"
        sub.expires_at = now

    if amount is None:
        amount = _setting_val(db, meta["price_key"], meta["default_price"])

    sub = models.Subscription(
        user_id=user.id,
        plan=plan_id,
        status="active",
        amount=amount,
        currency=_setting_str(db, "payment_currency", "INR").upper(),
        payment_method=payment_method,
        payment_id=payment_id,
        receipt=receipt,
        started_at=now,
        expires_at=expires,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


# ---------------- public plan catalog ----------------

@billing_router.get("/pricing/plans", tags=["pricing"])
def pricing_plans(db=Depends(_db)):
    """Get all available plans with current pricing.
    Prices are read from the database (admin-editable)."""
    plans = {}
    for pid, meta in PLAN_META.items():
        price = _setting_val(db, meta["price_key"], meta["default_price"])
        plans[pid] = {
            "id": pid,
            "name": meta["name"],
            "price": price,
            "period": "month",
            "features": meta["features"],
        }
    return {"plans": plans}


@billing_router.get("/pricing/plan/{plan_id}", tags=["pricing"])
def pricing_plan(plan_id: str, db=Depends(_db)):
    """Get a single plan's details."""
    if plan_id not in PLAN_META:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Unknown plan")
    meta = PLAN_META[plan_id]
    return {
        "id": plan_id,
        "name": meta["name"],
        "price": _setting_val(db, meta["price_key"], meta["default_price"]),
        "period": "month",
        "features": meta["features"],
    }


# ------------ auth-gated subscription endpoints ------------

def _require_user(authorization: str = Header(None)):
    """Verify JWT token and return the payload."""
    if not authorization:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    payload = auth.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def _current_user(authorization: str = Header(None)):
    return _require_user(authorization)


@billing_router.get("/subscription", tags=["billing"])
def my_subscription(
    token: dict = Depends(_current_user),
    db=Depends(_db),
):
    """Get the current user's subscription status."""
    user = db.query(models.User).filter(models.User.id == token.get("user_id")).first()
    if not user:
        raise HTTPException(401, "User not found") from None
    active = (
        db.query(models.Subscription)
        .filter(models.Subscription.user_id == user.id)
        .order_by(models.Subscription.id.desc())
        .first()
    )
    return {
        "plan": user.plan or "free",
        "status": active.status if active else "none",
        "expires_at": _iso(user.plan_expires_at),
        "amount": active.amount if active else 0.0,
        "started_at": _iso(active.started_at) if active else None,
    }


class CheckoutSchema(BaseModel):
    """Request body for POST /api/pricing/checkout"""
    plan_id: str


@billing_router.post("/pricing/checkout", tags=["billing"])
def checkout(
    body: CheckoutSchema,
    token: dict = Depends(_current_user),
    db=Depends(_db),
):
    """Initiate a subscription checkout.

    Flow:
        1. If plan is "free": cancel subscription immediately
        2. If Razorpay is configured: create order, return order details
        3. If Razorpay is NOT configured: simulated checkout (instant)

    The frontend handles the actual payment flow (Razorpay SDK).
    """
    plan_id = body.plan_id.lower()
    if plan_id not in PLAN_META:
        raise HTTPException(status_code=404, detail="Unknown plan")

    user = db.query(models.User).filter(models.User.id == token.get("user_id")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    now = datetime.now(timezone.utc)

    # Cancel subscription (downgrade to free)
    if plan_id == "free":
        user.plan = "free"
        if user.role not in rbac.ADMIN_ROLES:
            user.role = "free"
        user.plan_expires_at = None
        for sub in db.query(models.Subscription).filter(
            models.Subscription.user_id == user.id,
            models.Subscription.status == "active",
        ).all():
            sub.status = "cancelled"
            sub.expires_at = now
        db.commit()
        _record_admin_activity(db, user, "subscription.cancel", f"user#{user.id}", "plan=free")
        return {"message": "Subscription cancelled", "plan": "free"}

    # Real Razorpay path
    if _razorpay_enabled(db):
        order = _razorpay_order(db, plan_id, user)
        if not order:
            raise HTTPException(status_code=502, detail="Payment provider unavailable")
        return {
            "mode": "razorpay",
            "razorpay": {
                "key_id": _razorpay_config(db)[0],
                "order_id": order.get("id"),
                "amount": order.get("amount"),
                "currency": order.get("currency"),
                "receipt": order.get("receipt"),
            },
        }

    # Simulated checkout (no Razorpay keys configured)
    meta = PLAN_META[plan_id]
    sub = _activate_plan(db, user, plan_id, payment_method="simulated")
    _record_admin_activity(db, user, "subscription.activate", f"user#{user.id}", f"plan={plan_id}")

    return {
        "mode": "simulated",
        "message": f"{meta['name']} activated (simulated)",
        "plan": plan_id,
        "amount": sub.amount,
        "expires_at": _iso(sub.expires_at),
    }


class VerifyPaymentSchema(BaseModel):
    """Request body for POST /api/pricing/verify-payment"""
    plan_id: str
    order_id: str
    payment_id: str
    signature: str


@billing_router.post("/pricing/verify-payment", tags=["billing"])
def verify_payment(
    body: VerifyPaymentSchema,
    token: dict = Depends(_current_user),
    db=Depends(_db),
):
    """Verify a Razorpay payment and activate the subscription.

    Flow:
        1. Verify the payment signature (HMAC-SHA256)
        2. If valid: activate the plan
        3. If invalid: reject with 400 error
    """
    plan_id = body.plan_id.lower()
    if plan_id not in PLAN_META:
        raise HTTPException(status_code=404, detail="Unknown plan")

    user = db.query(models.User).filter(models.User.id == token.get("user_id")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not _razorpay_enabled(db):
        raise HTTPException(status_code=400, detail="Razorpay not configured")

    key_secret = _razorpay_config(db)[1]
    if not _verify_razorpay_signature(key_secret, body.order_id, body.payment_id, body.signature):
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    meta = PLAN_META[plan_id]
    sub = _activate_plan(
        db,
        user,
        plan_id,
        payment_method="razorpay",
        payment_id=body.payment_id,
        receipt=body.order_id,
    )
    _record_admin_activity(db, user, "subscription.activate", f"user#{user.id}", f"plan={plan_id} razorpay={body.payment_id}")

    return {
        "message": f"{meta['name']} activated",
        "plan": plan_id,
        "amount": sub.amount,
        "expires_at": _iso(sub.expires_at),
        "payment_id": body.payment_id,
    }


def _record_admin_activity(db, user, action, target, detail):
    """Record an admin activity for audit purposes."""
    try:
        db.add(models.AdminActivity(
            admin_id=user.id,
            admin_email=user.email,
            action=action,
            target=target,
            detail=detail,
        ))
        db.commit()
    except Exception as e:
        logger.warning(f"activity log failed: {e}")
