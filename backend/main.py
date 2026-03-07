import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.database import init_firebase
from core.cache import venue_cache
from core.config import settings

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan events for the FastAPI application.
    Handles startup and shutdown logic.
    """
    logger.info("Starting up Gemini Gastro-Agent backend...")

    # Initialize Firebase
    try:
        init_firebase()
    except Exception as e:
        logger.warning(f"Could not initialize Firebase natively: {e}")
        logger.warning(
            "Application will start, but database-dependent endpoints will fail."
        )

    # Load all venues into memory (cache) if DB is available
    try:
        from core.database import get_db

        # This will raise RuntimeError if init_firebase failed
        get_db()
        venue_cache.load_all_venues()
    except RuntimeError:
        logger.warning("Skipping cache load because Firestore is not initialized.")
        # Insert a dummy venue for local WebSocket testing
        venue_cache._cache["test-venue"] = {"name": "Test Venue", "catalog": {}}
        logger.warning(
            "Loaded dummy 'test-venue' for local WebSocket testing without database."
        )
    except Exception as e:
        logger.error(f"Failed to load venue cache: {e}")
        # Not exiting here so we can still test /health

    logger.info("Application startup complete.")

    yield  # The application runs while yielding

    logger.info("Shutting down Gemini Gastro-Agent backend...")
    # Any cleanup operations go here


# Initialize FastAPI application
app = FastAPI(
    title="Gemini Gastro-Agent API",
    description="Multimodal Live Agent backend for restaurants and coffee shops.",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS (Important for the React frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to the Firebase Hosting URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Basic health check endpoint for Cloud Run and external monitoring.
    """
    return JSONResponse(
        content={"status": "healthy", "environment": settings.environment},
        status_code=200,
    )


@app.websocket("/ws/{venue_id}")
async def gemini_live_websocket(websocket: WebSocket, venue_id: str):
    """
    WebSocket endpoint for the frontend to connect to the Gemini Live API.
    """
    await websocket.accept()

    # 1. Validate that the venue exists in our cache
    if not venue_cache.is_valid_venue(venue_id):
        logger.warning(f"Connection rejected: Venue '{venue_id}' not found.")
        await websocket.send_json({"type": "error", "message": "Venue not found"})
        await websocket.close(code=4004)
        return

    logger.info(f"WebSocket connection established for venue: {venue_id}")

    try:
        # 2. Extract user ID if provided (for authenticated features)
        # Note: In a real implementation, you'd likely pass a token via headers
        # or the initial frame, but query params are common for WebSockets.
        user_uid = websocket.query_params.get("uid")
        if user_uid:
            logger.info(f"Authenticated user: {user_uid}")

        # 3. TODO: Establish connection with google-genai SDK (Phase 2)
        # 4. TODO: Start the bidirectional pump (Client <-> FastAPI <-> Gemini)

        # Placeholder loop just to keep connection alive for testing
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")
            # Echo back for testing
            await websocket.send_text(f"Echo: {data}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for venue: {venue_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # Try to close gracefully if possible
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        # 5. TODO: Clean up Gemini Live Session and HITL Escalation Map (Phase 2/3)
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
