import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from core.cache import venue_cache

client = TestClient(app)

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def setup_mock_venue():
    """Inject a realistic venue with owners and employees into the RAM cache."""
    venue_cache._cache = {
        "rest1": {
            "name": "Restaurant One",
            "system_prompt_context": "",
            "catalog": {
                "coffee": {
                    "name": "Coffee",
                    "price": 2.50,
                    "available": True,
                    "category": "beverages",
                    "allergens": [],
                    "ingredients": ["espresso"],
                }
            },
            "owners": [111111],
            "employees": [222222],
            "invite_pins": {},
        }
    }
    # Ensure the app escalation map is empty between tests
    app.state.active_escalation_map = {}
    yield
    venue_cache._cache = {}
    app.state.active_escalation_map = {}


def _make_telegram_payload(chat_id: int, text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id, "type": "private"},
            "date": 0,
            "text": text,
        },
    }


# ── Authorization tests ──────────────────────────────────────────────────


def test_unauthorized_sender_is_silently_ignored():
    """Telegram sends 200 even for unknown chat_ids — we just do nothing."""
    unknown_chat_id = 999999
    payload = _make_telegram_payload(unknown_chat_id, "/update coffee available=false")
    response = client.post("/webhooks/telegram", json=payload)
    assert response.status_code == 200


# ── Catalog update tests ─────────────────────────────────────────────────


@patch("core.database.get_db")
@patch("webhooks.telegram.send_telegram_message", new_callable=AsyncMock)
def test_authorized_catalog_update_available(mock_send, mock_get_db):
    """Owner can toggle item availability via /update command."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    mock_item_doc = MagicMock()
    mock_item_doc.exists = True
    mock_item_doc.to_dict.return_value = {"name": "Coffee", "available": True}
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = mock_item_doc

    with patch("core.cache.VenueCacheManager.update_venue_cache"):
        payload = _make_telegram_payload(111111, "/update coffee available=false")
        response = client.post("/webhooks/telegram", json=payload)

    assert response.status_code == 200
    mock_send.assert_called_once()
    sent_text = (
        mock_send.call_args[1]["text"]
        if mock_send.call_args[1]
        else mock_send.call_args[0][1]
    )
    assert "Coffee" in sent_text or "coffee" in sent_text.lower()


@patch("core.database.get_db")
@patch("webhooks.telegram.send_telegram_message", new_callable=AsyncMock)
def test_catalog_update_item_not_found(mock_send, mock_get_db):
    """Sending /update for a non-existent item returns an error notification."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    mock_item_doc = MagicMock()
    mock_item_doc.exists = False
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = mock_item_doc

    payload = _make_telegram_payload(111111, "/update ghost_item available=true")
    response = client.post("/webhooks/telegram", json=payload)

    assert response.status_code == 200
    mock_send.assert_called_once()
    error_text = mock_send.call_args[1].get("text", "") or mock_send.call_args[0][1]
    assert "not found" in error_text.lower() or "❌" in error_text


# ── HITL relay tests ─────────────────────────────────────────────────────


def test_hitl_response_is_queued_for_client():
    """
    When a known escalation is open, an owner's message is put into the queue
    and the escalation is removed from the map.
    """
    # Pre-register a fake escalation queue for our test venue
    test_queue: asyncio.Queue = asyncio.Queue()
    app.state.active_escalation_map["rest1"] = test_queue

    owner_chat_id = 111111
    payload = _make_telegram_payload(
        owner_chat_id, "Yes, we can do gluten-free on request!"
    )
    response = client.post("/webhooks/telegram", json=payload)

    assert response.status_code == 200
    # Escalation map entry should be consumed / removed
    assert "rest1" not in app.state.active_escalation_map
    # The queue should have exactly one message
    assert not test_queue.empty()
    msg = test_queue.get_nowait()
    assert msg["type"] == "owner_message"
    assert "gluten-free" in msg["message"]
    assert msg["role"] == "owner"


def test_employee_hitl_response_includes_correct_role():
    """Employee responses are tagged with 'employee' role."""
    test_queue: asyncio.Queue = asyncio.Queue()
    app.state.active_escalation_map["rest1"] = test_queue

    employee_chat_id = 222222
    payload = _make_telegram_payload(employee_chat_id, "The kitchen closes at 10pm.")
    client.post("/webhooks/telegram", json=payload)

    msg = test_queue.get_nowait()
    assert msg["role"] == "employee"


# ── /join onboarding tests ───────────────────────────────────────────────


@patch("core.database.get_db")
@patch("webhooks.telegram.send_telegram_message", new_callable=AsyncMock)
def test_join_with_invalid_pin(mock_send, mock_get_db):
    """An unknown PIN should trigger an 'invalid' error message."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Mock Firestore stream returning our venue with no matching PIN
    mock_venue_doc = MagicMock()
    mock_venue_doc.id = "rest1"
    mock_venue_doc.to_dict.return_value = {"invite_pins": {}}
    mock_db.collection.return_value.stream.return_value = [mock_venue_doc]

    payload = _make_telegram_payload(999999, "/join 0000")
    response = client.post("/webhooks/telegram", json=payload)

    assert response.status_code == 200
    mock_send.assert_called_once()
    error_text = mock_send.call_args[1].get("text", "") or mock_send.call_args[0][1]
    assert "invalid" in error_text.lower() or "❌" in error_text


@patch("core.database.get_db")
@patch("webhooks.telegram.send_telegram_message", new_callable=AsyncMock)
@patch("core.cache.VenueCacheManager.update_venue_cache")
def test_join_with_valid_pin(mock_cache_update, mock_send, mock_get_db):
    """A valid, unexpired PIN should add the user as an employee."""
    from datetime import datetime, timezone, timedelta

    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    future_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    mock_venue_doc = MagicMock()
    mock_venue_doc.id = "rest1"
    mock_venue_doc.to_dict.return_value = {
        "invite_pins": {"4815": {"expires_at": future_expiry, "role": "employee"}},
        "employees": [],
    }
    mock_db.collection.return_value.stream.return_value = [mock_venue_doc]

    payload = _make_telegram_payload(333333, "/join 4815")
    response = client.post("/webhooks/telegram", json=payload)

    assert response.status_code == 200
    # Should have updated Firestore with the new employee
    mock_db.collection.return_value.document.return_value.update.assert_called()
    # Cache should be refreshed
    mock_cache_update.assert_called_once_with("rest1")
    # Should send a confirmation message
    mock_send.assert_called_once()
    success_text = mock_send.call_args[1].get("text", "") or mock_send.call_args[0][1]
    assert "employee" in success_text.lower() or "✅" in success_text
