import logging
from typing import Any, Dict

from google.cloud.firestore import Client
from core.database import get_db

logger = logging.getLogger(__name__)


class VenueCacheManager:
    """
    Manages the in-memory cache of venue data to ensure ultra-low latency
    for the Gemini Live Agent tool calls.
    """

    def __init__(self):
        # Format: { "venue_id": { "name": "...", "catalog": { ... } } }
        self._cache: Dict[str, Dict[str, Any]] = {}

    def load_all_venues(self) -> None:
        """
        Loads all venues and their catalogs from Firestore into memory.
        This blocking operation should only happen during startup.
        """
        logger.info("Starting Venue RAM Cache load...")
        try:
            db: Client = get_db()
            venues_ref = db.collection("venues")
            venues = venues_ref.stream()

            loaded_count = 0
            for venue_doc in venues:
                venue_id = venue_doc.id
                venue_data = venue_doc.to_dict() or {}

                # Load the catalog subcollection for this venue
                catalog_ref = venues_ref.document(venue_id).collection("catalog")
                catalog_docs = catalog_ref.stream()

                catalog_data = {}
                for item_doc in catalog_docs:
                    catalog_data[item_doc.id] = item_doc.to_dict()

                # Combine into the cached structure
                venue_data["catalog"] = catalog_data
                self._cache[venue_id] = venue_data
                loaded_count += 1

            logger.info(f"Loaded {loaded_count} venues into RAM Cache.")

        except Exception as e:
            logger.error(f"Failed to load venues into cache: {e}")
            # Depending on strictness, we might want to raise here
            # raise

    def get_venue(self, venue_id: str) -> Dict[str, Any] | None:
        """
        Retrieves a venue from the cache instantly.
        """
        return self._cache.get(venue_id)

    def is_valid_venue(self, venue_id: str) -> bool:
        """
        Quick check if a venue exists in the system.
        """
        return venue_id in self._cache

    def update_venue_cache(self, venue_id: str) -> None:
        """
        Forces a reload of a specific venue's data from Firestore into the cache.
        Usually called by the Telegram Webhook after an update.
        """
        logger.info(f"Reloading cache for venue: {venue_id}")
        try:
            db: Client = get_db()
            venue_doc = db.collection("venues").document(venue_id).get()

            if not venue_doc.exists:
                logger.warning(
                    f"Venue {venue_id} not found in Firestore during cache update."
                )
                if venue_id in self._cache:
                    del self._cache[venue_id]
                return

            venue_data = venue_doc.to_dict() or {}

            catalog_docs = (
                db.collection("venues")
                .document(venue_id)
                .collection("catalog")
                .stream()
            )
            catalog_data = {doc.id: doc.to_dict() for doc in catalog_docs}

            venue_data["catalog"] = catalog_data
            self._cache[venue_id] = venue_data

            logger.info(f"Successfully updated cache for venue: {venue_id}")

        except Exception as e:
            logger.error(f"Failed to update cache for venue {venue_id}: {e}")


# Global singleton instance
venue_cache = VenueCacheManager()
