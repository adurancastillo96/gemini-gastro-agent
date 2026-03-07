import pytest
from unittest.mock import MagicMock, patch
from core.cache import VenueCacheManager


@pytest.fixture
def empty_cache_manager():
    return VenueCacheManager()


@pytest.fixture
def populated_cache_manager():
    manager = VenueCacheManager()
    manager._cache = {
        "test-venue": {
            "name": "Test Venue",
            "system_prompt_context": "You are a test assistant.",
            "catalog": {
                "item-1": {
                    "name": "Coffee",
                    "price": 2.50,
                    "available": True,
                    "category": "beverages",
                }
            },
        }
    }
    return manager


def test_cache_initial_state(empty_cache_manager):
    assert empty_cache_manager._cache == {}
    assert empty_cache_manager.get_venue("any") is None
    assert empty_cache_manager.is_valid_venue("any") is False


def test_cache_retrieval(populated_cache_manager):
    assert populated_cache_manager.is_valid_venue("test-venue") is True

    venue = populated_cache_manager.get_venue("test-venue")
    assert venue is not None
    assert venue["name"] == "Test Venue"
    assert "catalog" in venue
    assert venue["catalog"]["item-1"]["name"] == "Coffee"


@patch("core.cache.get_db")
def test_venue_update_cache_success(mock_get_db, populated_cache_manager):
    """Test that update_venue_cache correctly queries Firestore and updates memory."""
    # Setup mock Firestore client and document
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    mock_venue_doc = MagicMock()
    mock_venue_doc.exists = True
    mock_venue_doc.to_dict.return_value = {"name": "Updated Venue Name"}

    mock_item_doc = MagicMock()
    mock_item_doc.id = "new-item"
    mock_item_doc.to_dict.return_value = {"name": "Tea", "price": 3.00}

    # Deep mock chaining for db.collection().document().get()
    mock_db.collection.return_value.document.return_value.get.return_value = (
        mock_venue_doc
    )
    # Mocking the subcollection stream db.collection().document().collection().stream()
    mock_db.collection.return_value.document.return_value.collection.return_value.stream.return_value = [
        mock_item_doc
    ]

    # Execute update
    populated_cache_manager.update_venue_cache("test-venue")

    # Verify the cache has been updated to the new mock state
    venue = populated_cache_manager.get_venue("test-venue")
    assert venue["name"] == "Updated Venue Name"
    assert "new-item" in venue["catalog"]
    assert venue["catalog"]["new-item"]["name"] == "Tea"
    assert "item-1" not in venue["catalog"]  # It was purely rewritten


@patch("core.cache.get_db")
def test_venue_update_cache_not_found(mock_get_db, populated_cache_manager):
    """Test that updating a deleted venue removes it from cache."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    mock_venue_doc = MagicMock()
    mock_venue_doc.exists = False
    mock_db.collection.return_value.document.return_value.get.return_value = (
        mock_venue_doc
    )

    # Assert venue exists initially
    assert populated_cache_manager.is_valid_venue("test-venue") is True

    populated_cache_manager.update_venue_cache("test-venue")

    # Assert venue was removed
    assert populated_cache_manager.is_valid_venue("test-venue") is False
