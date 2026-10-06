"""Unit tests for authentication utilities (JWT + password hashing)."""
import os
from datetime import datetime, timedelta, timezone

# Set test environment before importing app modules
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["APP_ENV"] = "development"

from App.api.auth import (
    hash_password,
    verify_password,
    create_token,
    verify_token,
    SECRET_KEY,
    ALGORITHM,
)
from jose import jwt


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        hashed = hash_password("mypassword")
        assert hashed.startswith("$2")  # bcrypt prefix

    def test_verify_password_correct(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("mypassword")
        h2 = hash_password("mypassword")
        assert h1 != h2  # bcrypt uses random salt

    def test_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_long_password(self):
        long_pw = "a" * 1000
        hashed = hash_password(long_pw)
        assert verify_password(long_pw, hashed) is True


class TestJWTTokenCreation:
    def test_create_token_returns_string(self):
        token = create_token({"user_id": 1})
        assert isinstance(token, str)

    def test_create_token_contains_user_id(self):
        token = create_token({"user_id": 42})
        payload = verify_token(token)
        assert payload is not None
        assert payload["user_id"] == 42

    def test_create_token_has_expiry(self):
        token = create_token({"user_id": 1})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_create_token_preserves_extra_data(self):
        token = create_token({"user_id": 1, "role": "admin"})
        payload = verify_token(token)
        assert payload["role"] == "admin"


class TestJWTTokenVerification:
    def test_valid_token(self):
        token = create_token({"user_id": 1})
        payload = verify_token(token)
        assert payload is not None
        assert payload["user_id"] == 1

    def test_invalid_token(self):
        payload = verify_token("invalid.token.here")
        assert payload is None

    def test_empty_token(self):
        payload = verify_token("")
        assert payload is None

    def test_tampered_token(self):
        token = create_token({"user_id": 1})
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        payload = verify_token(tampered)
        assert payload is None

    def test_token_with_wrong_secret(self):
        token = jwt.encode(
            {"user_id": 1, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret",
            algorithm=ALGORITHM,
        )
        payload = verify_token(token)
        assert payload is None

    def test_expired_token(self):
        payload_data = {
            "user_id": 1,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(payload_data, SECRET_KEY, algorithm=ALGORITHM)
        result = verify_token(token)
        assert result is None

    def test_token_with_missing_user_id(self):
        token = create_token({"role": "admin"})
        payload = verify_token(token)
        assert payload is not None
        assert "user_id" not in payload  # No error, just missing key
