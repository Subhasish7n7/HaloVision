"""WebSocket integration tests."""
import os
import sys
import pytest
import asyncio
import json

# Set test environment BEFORE importing app modules
os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-for-ws-tests"
os.environ["DATABASE_URL"] = "sqlite:///test_ws.db"
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ["ADMIN_PASSWORD"] = "TestPassword123!"

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from App.main import app
from App.api.database import SessionLocal, engine, Base
from App.api import models, auth


@pytest.fixture(autouse=True)
def setup_database():
    """Create fresh test database for each test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_token(client):
    """Register and login, return JWT token."""
    client.post("/api/auth/signup", json={
        "name": "WS Test User",
        "email": "ws@test.com",
        "password": "WSPassword123!",
    })
    response = client.post("/api/auth/login", json={
        "email": "ws@test.com",
        "password": "WSPassword123!",
    })
    return response.json()["token"]


class TestWebSocketAuthentication:
    def test_ws_without_token_rejected(self, client):
        """WebSocket without token should be rejected (closed by server)."""
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as ws:
                pass

    def test_ws_with_invalid_token_rejected(self, client):
        """WebSocket with invalid token should be rejected."""
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws?token=invalid.token.here") as ws:
                pass

    def test_ws_with_valid_token_accepted(self, client, auth_token):
        """WebSocket with valid token should connect."""
        with client.websocket_connect(f"/ws?token={auth_token}") as ws:
            # Connection should succeed - no exception
            pass

    def test_rtc_without_token_rejected(self, client):
        """WebRTC signaling without token should be rejected."""
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/rtc") as ws:
                pass

    def test_rtc_with_valid_token_accepted(self, client, auth_token):
        """WebRTC signaling with valid token should connect."""
        with client.websocket_connect(f"/rtc?token={auth_token}") as ws:
            pass


class TestWebSocketMessages:
    def test_mode_change(self, client, auth_token):
        """Test sending mode change message."""
        with client.websocket_connect(f"/ws?token={auth_token}") as ws:
            ws.send_json({"type": "mode", "data": "navigation"})

    def test_search_command(self, client, auth_token):
        """Test sending search command."""
        with client.websocket_connect(f"/ws?token={auth_token}") as ws:
            ws.send_json({"type": "search", "data": "chair"})

    def test_voice_command(self, client, auth_token):
        """Test sending voice command."""
        with client.websocket_connect(f"/ws?token={auth_token}") as ws:
            ws.send_json({"type": "voice", "data": "find person"})

    def test_gesture_command(self, client, auth_token):
        """Test sending gesture command."""
        with client.websocket_connect(f"/ws?token={auth_token}") as ws:
            ws.send_json({"type": "gesture_command", "data": "open_palm"})


class TestClientRegistry:
    def test_client_added_on_connect(self, client, auth_token):
        """Test that client is added to registry on connect."""
        from App.api.webRTC import clients
        initial_count = len(clients)

        with client.websocket_connect(f"/ws?token={auth_token}") as ws:
            assert len(clients) > initial_count
