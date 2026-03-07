import json
import logging
from typing import Any, Awaitable, Callable

from google import genai
from google.genai import types

from core.config import settings
from agent.tools import agent_tools

logger = logging.getLogger(__name__)


class GeminiLiveSession:
    """
    Manages a multimodal WebSocket connection with the Gemini Live API using
    the official google-genai SDK.
    """

    MODEL = "gemini-live-2.5-flash-native-audio"

    def __init__(
        self,
        venue_id: str,
        system_instruction: str,
        on_audio_out: Callable[[bytes], Awaitable[None]],
        on_json_out: Callable[[str], Awaitable[None]],
        on_close: Callable[[], Awaitable[None]],
    ):
        self.venue_id = venue_id

        if not settings.gemini_api_key:
            logger.warning(
                "GEMINI_API_KEY is missing! The session will fail to connect."
            )

        self.client = genai.Client(api_key=settings.gemini_api_key)

        # Configure the Live session:
        # - The SDK auto-generates JSON Schema from the Python function signatures.
        # - We pass the list of functions directly — NOT wrapped in a dict.
        self.config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=system_instruction)]
            ),
            tools=agent_tools,
        )

        # Callbacks to relay data back to the FastAPI WebSocket loop
        self.on_audio_out = on_audio_out
        self.on_json_out = on_json_out
        self.on_close = on_close

        self.session = None
        self._is_active = False

    async def send_audio(self, pcm_data: bytes) -> None:
        """
        Sends raw PCM audio chunks from the user to Gemini.
        Assumes 16kHz, 16-bit mono PCM as required by the API.
        """
        if not self._is_active or not self.session:
            logger.debug(
                f"[{self.venue_id}] Attempted to send audio but session is inactive."
            )
            return

        try:
            await self.session.send(
                input=types.LiveClientContent(
                    realtime_input=types.LiveClientRealtimeInput(
                        media_chunks=[types.Blob(data=pcm_data, mime_type="audio/pcm")]
                    )
                )
            )
        except Exception as e:
            logger.error(f"[{self.venue_id}] Error sending audio to Gemini: {e}")
            await self.close()

    async def close(self) -> None:
        """Gracefully marks the session as inactive."""
        if not self._is_active:
            return
        self._is_active = False
        logger.info(f"[{self.venue_id}] Gemini Live session closed.")
        try:
            await self.on_close()
        except Exception:
            pass

    async def receive_loop(self) -> None:
        """
        Opens the connection to the Gemini Live API and continuously processes
        incoming events: audio output and native tool calls.
        """
        try:
            async with self.client.aio.live.connect(
                model=self.MODEL,
                config=self.config,
            ) as session:
                self.session = session
                self._is_active = True
                logger.info(
                    f"[{self.venue_id}] Gemini Live Session connected successfully."
                )

                async for response in session.receive():
                    if not self._is_active:
                        break

                    # 1. Handle audio output from Gemini (relay to frontend)
                    server_content = response.server_content
                    if server_content and server_content.model_turn:
                        for part in server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                await self.on_audio_out(part.inline_data.data)

                    # 2. Handle native function calls (tools)
                    if response.tool_call:
                        await self._handle_tool_call(response.tool_call, session)

        except Exception as e:
            logger.error(f"[{self.venue_id}] Gemini Live session error: {e}")
        finally:
            await self.close()

    async def _handle_tool_call(self, tool_call: Any, session: Any) -> None:
        """
        Executes the requested tool locally against the RAM cache and sends
        the result back to Gemini. Also emits UI JSON payloads to the frontend
        when catalog data is returned (FR3).
        """
        function_responses = []

        for fc in tool_call.function_calls:
            func_name = fc.name
            args = dict(fc.args or {})
            logger.info(f"[{self.venue_id}] Tool requested: {func_name}({args})")

            # Enforce tenant isolation — always inject the correct venue_id
            args["venue_id"] = self.venue_id

            try:
                target_func = next(
                    (f for f in agent_tools if f.__name__ == func_name), None
                )
                if target_func:
                    result = await target_func(**args)

                    # FR3: When catalog items are returned, emit a structured
                    # JSON payload to the frontend so it can render ProductCards.
                    if func_name == "check_catalog" and result.get("items"):
                        ui_payload = json.dumps(
                            {"type": "catalog_update", "items": result["items"]}
                        )
                        await self.on_json_out(ui_payload)

                    function_responses.append(
                        types.FunctionResponse(
                            id=fc.id, name=func_name, response=result
                        )
                    )
                else:
                    logger.warning(f"[{self.venue_id}] Unknown tool: {func_name}")
                    function_responses.append(
                        types.FunctionResponse(
                            id=fc.id,
                            name=func_name,
                            response={"error": "Function not implemented"},
                        )
                    )
            except Exception as e:
                logger.error(
                    f"[{self.venue_id}] Tool execution failed for '{func_name}': {e}"
                )
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id, name=func_name, response={"error": str(e)}
                    )
                )

        if function_responses:
            await session.send(
                input=types.LiveClientContent(
                    tool_response=types.LiveClientToolResponse(
                        function_responses=function_responses
                    )
                )
            )
