import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.database import init_firebase
from core.cache import venue_cache
from core.config import settings
from agent.session import GeminiLiveSession
from webhooks.telegram import router as telegram_router

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Handles startup initialization and graceful shutdown.
    """
    logger.info("Starting up Gemini Gastro-Agent backend...")

    # Phase 3: Initialise the HITL escalation session map.
    # Key: venue_id — Value: asyncio.Queue to deliver owner responses.
    app.state.active_escalation_map: Dict[str, asyncio.Queue] = {}

    # Phase 1: Initialize Firebase Admin SDK
    try:
        init_firebase()
    except Exception as e:
        logger.warning(f"Firebase initialization failed: {e}")
        logger.warning("Database-dependent endpoints will be unavailable.")

    # Phase 1: Load all venue data into the RAM cache
    try:
        from core.database import get_db

        get_db()  # Raises RuntimeError if Firebase init failed
        venue_cache.load_all_venues()
    except RuntimeError:
        logger.warning("Skipping cache load — Firestore is not initialized.")
        # Inject a dummy venue so local WebSocket testing still works
        venue_cache._cache["test-venue"] = {
            "name": "Test Venue",
            "catalog": {},
            "owners": [],
            "employees": [],
        }
        logger.warning("Loaded dummy 'test-venue' for local development.")
    except Exception as e:
        logger.error(f"Failed to load venue cache: {e}")

    logger.info("Application startup complete.")
    yield
    logger.info("Shutting down Gemini Gastro-Agent backend...")
    app.state.active_escalation_map.clear()


# ── FastAPI application ────────────────────────────────────────────────────

app = FastAPI(
    title="Gemini Gastro-Agent API",
    description="Multimodal Live Agent backend for restaurants and coffee shops.",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS — restrict origins to the Firebase Hosting URL in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 3: Mount the Telegram webhook router
app.include_router(telegram_router)


# ── REST endpoints ─────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check for Cloud Run and monitoring tools."""
    return JSONResponse(
        content={
            "status": "healthy",
            "environment": settings.environment,
            "venues_loaded": len(venue_cache._cache),
        },
        status_code=200,
    )


# ── WebSocket endpoint ─────────────────────────────────────────────────────


@app.websocket("/ws/{venue_id}")
async def gemini_live_websocket(websocket: WebSocket, venue_id: str):
    """
    Primary WebSocket endpoint.
    Bridges the React frontend ↔ FastAPI ↔ Gemini Live API.
    Also handles HITL escalation relay via the active_escalation_map.
    """
    await websocket.accept()

    # FR8: Validate venue existence before opening a Gemini session
    if not venue_cache.is_valid_venue(venue_id):
        logger.warning(f"Connection rejected: venue '{venue_id}' not found.")
        await websocket.send_json({"type": "error", "message": "Venue not found"})
        await websocket.close(code=4004)
        return

    logger.info(f"WebSocket accepted for venue='{venue_id}'")

    # FR9: Optional authenticated UID for HITL feature gating
    user_uid = websocket.query_params.get("uid")
    if user_uid:
        logger.info(f"Authenticated user uid={user_uid}")

    # ── Callbacks from GeminiLiveSession → frontend ──────────────────────

    async def on_audio_out(audio_data: bytes) -> None:
        try:
            await websocket.send_bytes(audio_data)
        except Exception as e:
            logger.error(f"[{venue_id}] Error relaying audio to client: {e}")

    async def on_json_out(json_str: str) -> None:
        try:
            await websocket.send_text(json_str)
        except Exception as e:
            logger.error(f"[{venue_id}] Error sending JSON to client: {e}")

    async def on_close() -> None:
        try:
            await websocket.close()
        except Exception:
            pass

    # ── Initialise the Gemini Live session ───────────────────────────────

    venue_data = venue_cache.get_venue(venue_id) or {}
    system_instruction = venue_data.get("system_prompt_context", "")

    gemini_session = GeminiLiveSession(
        venue_id=venue_id,
        system_instruction=system_instruction,
        on_audio_out=on_audio_out,
        on_json_out=on_json_out,
        on_close=on_close,
    )

    # Phase 3: Register a queue in the escalation map so that Telegram
    # responses can be delivered to this specific WebSocket connection.
    active_escalation_map: Dict[str, asyncio.Queue] = app.state.active_escalation_map
    escalation_queue: asyncio.Queue = asyncio.Queue()
    active_escalation_map[venue_id] = escalation_queue

    try:
        # ── HITL relay loop ───────────────────────────────────────────────
        # Runs concurrently; polls the queue for owner responses from Telegram
        # and forwards them to the frontend as structured JSON messages.

        async def hitl_relay_loop() -> None:
            while True:
                try:
                    message = await asyncio.wait_for(
                        escalation_queue.get(), timeout=1.0
                    )
                    await websocket.send_text(__import__("json").dumps(message))
                    logger.info(f"[{venue_id}] HITL message relayed to client.")
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"[{venue_id}] HITL relay error: {e}")
                    break

        # ── Client receive loop ───────────────────────────────────────────
        # Reads PCM audio bytes from the frontend and forwards to Gemini.

        async def client_receive_loop() -> None:
            try:
                while True:
                    data = await websocket.receive_bytes()
                    await gemini_session.send_audio(data)
            except WebSocketDisconnect:
                logger.info(f"[{venue_id}] Client disconnected.")
            except Exception as e:
                logger.error(f"[{venue_id}] Client receive loop error: {e}")
            finally:
                await gemini_session.close()

        # Gather all three concurrent loops
        await asyncio.gather(
            client_receive_loop(),
            gemini_session.receive_loop(),
            hitl_relay_loop(),
        )

    except WebSocketDisconnect:
        logger.info(f"[{venue_id}] WebSocket disconnected.")
    except Exception as e:
        logger.error(f"[{venue_id}] WebSocket error: {e}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        # Cleanup: remove escalation slot and close Gemini session
        active_escalation_map.pop(venue_id, None)
        await gemini_session.close()
        logger.info(f"[{venue_id}] Session cleaned up.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
