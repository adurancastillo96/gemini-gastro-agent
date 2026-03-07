import logging
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Client

from core.config import settings

logger = logging.getLogger(__name__)

# Global variable to hold the Firestore client
_db: Client | None = None


def init_firebase() -> None:
    """
    Initialize the Firebase Admin SDK and Firestore client.
    Should be called during the FastAPI lifespan startup.
    """
    global _db

    if firebase_admin._apps:
        logger.info("Firebase app already initialized.")
        _db = firestore.client()
        return

    logger.info("Initializing Firebase app...")
    try:
        if settings.firebase_credentials_path:
            # Local development with explicit service account key
            cred = credentials.Certificate(settings.firebase_credentials_path)
            firebase_admin.initialize_app(cred)
            logger.info(
                f"Initialized Firebase with credentials file: {settings.firebase_credentials_path}"
            )
        else:
            # Production (Cloud Run) using Application Default Credentials
            firebase_admin.initialize_app(
                options={"projectId": settings.firebase_project_id}
            )
            logger.info(
                f"Initialized Firebase with Default Credentials for project: {settings.firebase_project_id}"
            )

        _db = firestore.client()
        logger.info("Firestore client successfully created.")

    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise


def get_db() -> Client:
    """
    Dependency to get the Firestore client.
    """
    if _db is None:
        raise RuntimeError(
            "Firestore client has not been initialized. Call init_firebase() first."
        )
    return _db
