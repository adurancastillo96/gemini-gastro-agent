import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
from unittest.mock import patch, MagicMock, AsyncMock

from main import app
from core.cache import venue_cache

# Using TestClient automatically handles the ASGI lifecycle
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_venue():
    # Inject a test venue for WebSocket acceptance
    venue_cache._cache = {
        "rest1": {"name": "Restaurant One", "system_prompt_context": "", "catalog": {}}
    }
    # Seed the escalation map because TestClient doesn't run the lifespan
    app.state.active_escalation_map = {}
    yield
    venue_cache._cache = {}
    app.state.active_escalation_map = {}


def test_health_endpoint():
    # TestClient doesn't need to be async for simple HTTP endpoints
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_websocket_rejects_invalid_venue():
    # We attempt to connect to a venue not in the local mock cache
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/invalid_venue") as websocket:
            # First, the backend sends a JSON explaining the error
            error_msg = websocket.receive_json()
            assert error_msg["type"] == "error"

            # Second, it closes the connection, which raises Starlette's WebSocketDisconnect
            websocket.receive_text()

    assert excinfo.value.code == 4004


@patch("main.GeminiLiveSession")
def test_websocket_accepts_valid_venue(mock_gemini_session_class):
    """
    Test that connecting to a valid venue establishes the pipeline
    and instantiates the GeminiLiveSession.
    """
    mock_session_instance = MagicMock()
    # We must use AsyncMock for methods that are awaited in main.py
    mock_session_instance.receive_loop = AsyncMock()
    mock_session_instance.send_audio = AsyncMock()
    mock_session_instance.close = AsyncMock()

    mock_gemini_session_class.return_value = mock_session_instance

    # Send a query param to test auth parsing
    with client.websocket_connect("/ws/rest1?uid=testuser123") as websocket:
        # If it reaches here without raising, it connected successfully
        websocket.send_bytes(b"fake audio data")

    # Verify our dependencies were called
    mock_gemini_session_class.assert_called_once()
    assert mock_gemini_session_class.call_args.kwargs["venue_id"] == "rest1"

    # Ensure cleanup was called at least once (it might be called in multiple finally blocks)
    assert mock_session_instance.close.call_count >= 1
