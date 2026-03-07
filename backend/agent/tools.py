import logging
from typing import Any, Dict, Optional
from core.cache import venue_cache

logger = logging.getLogger(__name__)

# Note: The google-genai SDK in Live API mode automatically infers the
# JSON Schema from the Python function signature (types and docstrings).
# Thus, clear type hints and docstrings are strictly required.


async def get_venue_info(venue_id: str) -> Dict[str, Any]:
    """
    Retrieves the basic details and system context for a specific venue.
    Call this to understand what venue you are assisting with if needed.

    Args:
        venue_id: The unique identifier for the venue.

    Returns:
        A dictionary containing the venue's name and any special context.
    """
    logger.info(f"Tool Call: get_venue_info(venue_id='{venue_id}')")

    venue_data = venue_cache.get_venue(venue_id)
    if not venue_data:
        return {"error": f"Venue {venue_id} not found."}

    return {
        "name": venue_data.get("name", "Unknown Venue"),
        "system_prompt_context": venue_data.get("system_prompt_context", ""),
    }


async def check_catalog(
    venue_id: str,
    query: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Searches the venue's catalog for food, drinks, or other items.
    Use this to check prices, ingredients, allergens, and if an item is available.

    Args:
        venue_id: The unique identifier for the venue.
        query: Optional search term (e.g., "coffee", "vegan", "burger").
        category: Optional category to filter by (e.g., "beverages", "mains", "desserts").

    Returns:
        A dictionary containing a list of matched items and a summary message.
    """
    logger.info(
        f"Tool Call: check_catalog(venue_id='{venue_id}', query='{query}', category='{category}')"
    )

    venue_data = venue_cache.get_venue(venue_id)
    if not venue_data:
        return {"error": f"Venue {venue_id} not found."}

    catalog = venue_data.get("catalog", {})
    if not catalog:
        return {"message": "The catalog is currently empty.", "items": []}

    results = []

    # Simple in-memory search
    for item_id, item_data in catalog.items():
        match = True

        if category and item_data.get("category", "").lower() != category.lower():
            match = False

        if match and query:
            q = query.lower()
            name_match = q in item_data.get("name", "").lower()
            ing_match = any(
                q in ing.lower() for ing in item_data.get("ingredients", [])
            )
            cat_match = q in item_data.get("category", "").lower()

            if not (name_match or ing_match or cat_match):
                match = False

        if match:
            # Explicitly include only the data the LLM needs to answer
            # to keep context window usage optimal.
            results.append(
                {
                    "item_id": item_id,
                    "name": item_data.get("name"),
                    "price": item_data.get("price"),
                    "available": item_data.get("available"),
                    "allergens": item_data.get("allergens", []),
                    "category": item_data.get("category"),
                    "image_url": item_data.get(
                        "image_url"
                    ),  # Sent to UI, LLM can ignore
                }
            )

    if not results:
        return {"message": "No items matched the search criteria.", "items": []}

    return {"message": f"Found {len(results)} items.", "items": results}


async def escalate_to_owner(venue_id: str, customer_query: str) -> Dict[str, Any]:
    """
    Escalates an unresolved customer query to the venue's owner or employees via Telegram.
    Call this ONLY when you cannot answer the customer's question from the catalog or your
    knowledge, and the question is important enough to warrant human assistance.
    After calling this, tell the customer you are contacting the business and to wait.

    Args:
        venue_id: The unique identifier for the venue.
        customer_query: A concise summary of what the customer is asking that couldn't be resolved.

    Returns:
        A status message confirming whether the notification was sent successfully.
    """
    logger.info(
        f"Tool Call: escalate_to_owner(venue_id='{venue_id}', query='{customer_query}')"
    )

    # Import here to avoid circular imports (telegram.py also imports tools.py indirectly)
    from webhooks.telegram import send_telegram_message

    venue_data = venue_cache.get_venue(venue_id)
    if not venue_data:
        return {"error": f"Venue {venue_id} not found."}

    # Gather all authorized chat_ids (owners + employees)
    owners = venue_data.get("owners", [])
    employees = venue_data.get("employees", [])
    all_chat_ids = list(set(owners + employees))

    if not all_chat_ids:
        return {
            "status": "not_sent",
            "reason": "No owners or employees configured for this venue.",
        }

    message_text = (
        f"⚠️ *HITL Escalation — {venue_data.get('name', venue_id)}*\n\n"
        f"A customer needs help with:\n_{customer_query}_\n\n"
        f"Please reply directly to this message within 60 seconds."
    )

    try:
        await send_telegram_message(chat_ids=all_chat_ids, text=message_text)
        logger.info(
            f"HITL escalation sent to {len(all_chat_ids)} contact(s) for venue '{venue_id}'"
        )
        return {
            "status": "sent",
            "message": "The business has been notified. I will relay their response to you shortly.",
        }
    except Exception as e:
        logger.error(f"Failed to send Telegram HITL notification: {e}")
        return {
            "status": "failed",
            "reason": "Could not reach the business. Please try again or ask differently.",
        }


# Export the functions for the SDK declarations
agent_tools = [get_venue_info, check_catalog, escalate_to_owner]
