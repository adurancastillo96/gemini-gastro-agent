import pytest
from agent.tools import get_venue_info, check_catalog
from core.cache import venue_cache


# We inject a fake venue into the cache before testing the tools
@pytest.fixture(autouse=True)
def setup_mock_venue():
    venue_cache._cache = {
        "rest1": {
            "name": "Restaurant One",
            "system_prompt_context": "Act like a grumpy chef.",
            "catalog": {
                "item-1": {
                    "name": "Spaghetti Bolognese",
                    "price": 12.50,
                    "category": "mains",
                    "ingredients": ["pasta", "beef", "tomato"],
                    "allergens": ["gluten", "dairy"],
                    "available": True,
                },
                "item-2": {
                    "name": "Vegan Salad",
                    "price": 8.00,
                    "category": "starters",
                    "ingredients": ["lettuce", "tomato", "cucumber"],
                    "allergens": [],
                    "available": True,
                },
                "item-3": {
                    "name": "Tiramisu",
                    "price": 6.50,
                    "category": "desserts",
                    "ingredients": ["coffee", "mascarpone", "cocoa"],
                    "allergens": ["dairy", "gluten", "eggs"],
                    "available": False,
                },
            },
        }
    }
    yield
    venue_cache._cache = {}


@pytest.mark.asyncio
async def test_get_venue_info_success():
    result = await get_venue_info("rest1")
    assert result["name"] == "Restaurant One"
    assert result["system_prompt_context"] == "Act like a grumpy chef."


@pytest.mark.asyncio
async def test_get_venue_info_not_found():
    result = await get_venue_info("unknown")
    assert "error" in result


@pytest.mark.asyncio
async def test_check_catalog_empty_search():
    # If the LLM just asks to see the catalog without query
    result = await check_catalog("rest1")
    assert result["message"] == "Found 3 items."
    assert len(result["items"]) == 3


@pytest.mark.asyncio
async def test_check_catalog_by_name():
    result = await check_catalog("rest1", query="spaghetti")
    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == "Spaghetti Bolognese"


@pytest.mark.asyncio
async def test_check_catalog_by_ingredient():
    result = await check_catalog("rest1", query="tomato")
    # Both Spaghetti and Salad have tomato in ingredients
    assert len(result["items"]) == 2


@pytest.mark.asyncio
async def test_check_catalog_by_category():
    # Both direct query string or category filter should work
    result = await check_catalog("rest1", category="desserts")
    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == "Tiramisu"
    assert result["items"][0]["available"] is False


@pytest.mark.asyncio
async def test_check_catalog_no_match():
    result = await check_catalog("rest1", query="sushi")
    assert "message" in result
    assert result["items"] == []
    assert "No items matched" in result["message"]
