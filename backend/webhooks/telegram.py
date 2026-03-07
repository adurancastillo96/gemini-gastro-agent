"""
Telegram Bot Webhook — Phase 3: Human-in-the-Loop (HITL)

Handles incoming Telegram bot messages for:
  1. HITL response relay: Routes owner/employee answers back to the waiting client WebSocket.
  2. Catalog updates (FR7): Authorized users update item availability or price via text commands.
  3. Employee onboarding: The /join <PIN> command links a new employee's chat_id to a venue.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Request, Response
from google.cloud.firestore import SERVER_TIMESTAMP

from core.cache import venue_cache
from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def send_telegram_message(chat_ids: List[int], text: str) -> None:
    """
    Sends a text message to one or more Telegram chat_ids via the Bot API.
    Uses Markdown parse mode for formatting.
    """
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set. Skipping message send.")
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        for chat_id in chat_ids:
            try:
                resp = await client.post(
                    url,
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                )
                resp.raise_for_status()
                logger.info(f"Telegram message sent to chat_id={chat_id}")
            except Exception as e:
                logger.error(f"Failed to send Telegram message to {chat_id}: {e}")


def _find_venue_for_chat_id(chat_id: int) -> tuple[str | None, str | None]:
    """
    Scans the RAM cache to find which venue a given Telegram chat_id belongs to,
    and what their role is (owner | employee).
    Returns (venue_id, role) or (None, None) if not authorized.
    """
    for venue_id, venue_data in venue_cache._cache.items():
        if chat_id in venue_data.get("owners", []):
            return venue_id, "owner"
        if chat_id in venue_data.get("employees", []):
            return venue_id, "employee"
    return None, None


# ---------------------------------------------------------------------------
# Telegram Webhook endpoint
# ---------------------------------------------------------------------------


@router.post("/telegram")
async def telegram_webhook(request: Request) -> Response:
    """
    Receives updates from the Telegram Bot API (webhook mode).
    Telegram expects a 200 OK response immediately, regardless of processing outcome.
    """
    # Always respond 200 to Telegram first to avoid retries
    payload: Dict[str, Any] = await request.json()
    message = payload.get("message") or payload.get("edited_message")

    if not message:
        return Response(status_code=200)

    chat_id: int = message.get("chat", {}).get("id")
    text: str = message.get("text", "").strip()

    if not chat_id or not text:
        return Response(status_code=200)

    logger.info(f"Telegram update from chat_id={chat_id}: '{text}'")

    # Retrieve the active_escalation_map injected into the app state at startup
    active_escalation_map: Dict[str, asyncio.Queue] = (
        request.app.state.active_escalation_map
    )

    # ---- 1. Handle /join <PIN> (employee onboarding) ----
    if text.lower().startswith("/join"):
        await _handle_join(chat_id, text)
        return Response(status_code=200)

    # ---- 2. Authorize the sender ----
    venue_id, role = _find_venue_for_chat_id(chat_id)
    if not venue_id:
        logger.warning(
            f"Unauthorized Telegram message from chat_id={chat_id}. Ignoring."
        )
        return Response(status_code=200)

    # ---- 3. Handle HITL response (if any open escalation for this venue) ----
    escalation_queue = active_escalation_map.get(venue_id)
    if escalation_queue:
        logger.info(f"HITL response from {role} for venue '{venue_id}': '{text}'")
        await escalation_queue.put(
            {
                "type": "owner_message",
                "role": role,
                "message": text,
            }
        )
        # Remove the escalation after receiving a response
        active_escalation_map.pop(venue_id, None)
        return Response(status_code=200)

    # ---- 4. Handle catalog update commands (FR7) ----
    if text.lower().startswith("/update"):
        await _handle_catalog_update(venue_id, role, text, chat_id)
        return Response(status_code=200)

    # ---- 5. Unknown command — send a help message ----
    venue_name = venue_cache.get_venue(venue_id).get("name", venue_id)
    help_text = (
        f"👋 Hi! I'm connected to *{venue_name}*.\n\n"
        "Available commands:\n"
        "• `/update <item_id> available=true|false` — Toggle availability\n"
        "• `/update <item_id> price=<number>` — Update price\n\n"
        "To reply to a customer escalation, simply send your message when notified."
    )
    await send_telegram_message([chat_id], help_text)
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Sub-handlers
# ---------------------------------------------------------------------------


async def _handle_join(chat_id: int, text: str) -> None:
    """
    Handles the /join <PIN> command for employee onboarding.
    Validates the PIN against Firestore invite_pins, links chat_id if valid.
    """
    from core.database import get_db

    parts = text.split()
    if len(parts) != 2:
        await send_telegram_message(
            [chat_id], "Usage: `/join <PIN>` — e.g., `/join 4815`"
        )
        return

    pin = parts[1].strip()

    # Check all venues for a matching PIN
    try:
        db = get_db()
        venues_ref = db.collection("venues")
        venues = venues_ref.stream()

        for venue_doc in venues:
            venue_data = venue_doc.to_dict() or {}
            invite_pins: dict = venue_data.get("invite_pins", {})

            if pin not in invite_pins:
                continue

            pin_info = invite_pins[pin]
            expires_at = pin_info.get("expires_at")

            # Check expiry
            if expires_at and expires_at < datetime.now(timezone.utc):
                await send_telegram_message(
                    [chat_id],
                    "❌ This PIN has expired. Ask your manager for a new one.",
                )
                return

            role = pin_info.get("role", "employee")
            venue_id = venue_doc.id

            # Add chat_id to the correct role list and remove the PIN
            role_array = "owners" if role == "owner" else "employees"
            venue_ref = venues_ref.document(venue_id)
            current_list = venue_data.get(role_array, [])
            if chat_id not in current_list:
                current_list.append(chat_id)
                venue_ref.update({role_array: current_list})

            # Expire the PIN
            invite_pins.pop(pin)
            venue_ref.update({"invite_pins": invite_pins})

            # Refresh the RAM cache for this venue
            venue_cache.update_venue_cache(venue_id)

            venue_name = venue_cache.get_venue(venue_id).get("name", venue_id)
            await send_telegram_message(
                [chat_id], f"✅ You've been granted *{role}* access to *{venue_name}*!"
            )
            logger.info(f"chat_id={chat_id} joined venue '{venue_id}' as {role}")
            return

        await send_telegram_message(
            [chat_id], "❌ Invalid PIN. Please check and try again."
        )

    except Exception as e:
        logger.error(f"Error during /join for chat_id={chat_id}: {e}")
        await send_telegram_message(
            [chat_id], "⚠️ An error occurred. Please try again later."
        )


async def _handle_catalog_update(
    venue_id: str, role: str, text: str, chat_id: int
) -> None:
    """
    Parses and applies a /update command to a catalog item.
    Syntax: /update <item_id> <field>=<value> [<field>=<value> ...]
    Supported fields: available (true|false), price (number)
    """
    from core.database import get_db

    parts = text.split()
    # Minimum: /update item_id field=value
    if len(parts) < 3:
        await send_telegram_message(
            [chat_id],
            "Usage: `/update <item_id> available=true|false` or `/update <item_id> price=2.50`",
        )
        return

    item_id = parts[1]
    updates: Dict[str, Any] = {}

    for token in parts[2:]:
        if "=" not in token:
            continue
        field, value = token.split("=", 1)
        field = field.lower().strip()
        value = value.strip()

        if field == "available":
            updates["available"] = value.lower() in ("true", "1", "yes")
        elif field == "price":
            try:
                updates["price"] = float(value)
            except ValueError:
                await send_telegram_message(
                    [chat_id], f"❌ Invalid price value: `{value}`"
                )
                return
        else:
            await send_telegram_message(
                [chat_id],
                f"❌ Unknown field: `{field}`. Supported: `available`, `price`",
            )
            return

    if not updates:
        await send_telegram_message([chat_id], "❌ No valid fields to update.")
        return

    updates["updated_at"] = SERVER_TIMESTAMP

    try:
        db = get_db()
        item_ref = (
            db.collection("venues")
            .document(venue_id)
            .collection("catalog")
            .document(item_id)
        )
        item_doc = item_ref.get()

        if not item_doc.exists:
            await send_telegram_message(
                [chat_id], f"❌ Item `{item_id}` not found in the catalog."
            )
            return

        item_ref.update(updates)
        # Invalidate and reload the RAM cache for this venue (FR7)
        venue_cache.update_venue_cache(venue_id)

        item_name = item_doc.to_dict().get("name", item_id)
        changes = ", ".join(
            f"`{k}={v}`" for k, v in updates.items() if k != "updated_at"
        )
        await send_telegram_message([chat_id], f"✅ *{item_name}* updated: {changes}")
        logger.info(
            f"[{venue_id}] Catalog item '{item_id}' updated by {role} chat_id={chat_id}: {updates}"
        )

    except Exception as e:
        logger.error(
            f"Error updating catalog for venue '{venue_id}', item '{item_id}': {e}"
        )
        await send_telegram_message(
            [chat_id], "⚠️ Failed to update the catalog. Please try again."
        )
