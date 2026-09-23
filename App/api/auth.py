# =============================================================================
# FILE: App/api/auth.py
# ROLE: Authentication utilities — JWT tokens and password hashing.
#
# WHAT THIS FILE DOES:
#   Provides two core auth functions:
#   1. Password hashing/verification (bcrypt)
#   2. JWT token creation/verification (HS256)
#
# WHO USES THIS:
#   - main.py: signup/login routes use hash_password, create_token, verify_token
#   - main.py: get_current_user dependency uses verify_token
#   - admin.py: _current_admin dependency uses verify_token
#   - billing.py: _require_user dependency uses verify_token
#
# SECURITY FLOW:
#   Signup: password → hash_password() → stored in DB
#   Login:  password → verify_password() against DB hash → create_token()
#   Auth:   token → verify_token() → payload with user_id
# =============================================================================

import os
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError

# bcrypt password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration — loaded from environment variables
# In production, SECRET_KEY MUST be set via environment variable.
# For local development, a safe default is used only when APP_ENV is not "production".
_env = os.getenv("APP_ENV", "development").lower()
_default_secret = None if _env == "production" else "dev-only-not-for-production"
SECRET_KEY = os.getenv("SECRET_KEY") or _default_secret
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is required in production. "
        "Set it to a random string (e.g. openssl rand -hex 32)."
    )
ALGORITHM = "HS256"           # HMAC-SHA256 signing algorithm
TOKEN_EXPIRE_HOURS = 1        # Tokens expire after 1 hour

def hash_password(password: str):
    """Hash a plaintext password using bcrypt.
    Called during signup and password change."""
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    """Verify a plaintext password against a bcrypt hash.
    Called during login to check if the password is correct."""
    return pwd_context.verify(plain, hashed)

def create_token(data: dict):
    """Create a JWT token with the given payload and 1-hour expiry.
    The payload typically contains {"user_id": <id>}.

    The token is returned to the client and included in the
    Authorization header for subsequent requests."""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload["exp"] = expire
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    """Verify and decode a JWT token.
    Returns the payload dict (with user_id) if valid, None if expired/invalid.

    Called by get_current_user() and other auth dependencies."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
