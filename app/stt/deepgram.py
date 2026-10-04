from __future__ import annotations

import asyncio
import json
import urllib.parse
from typing import AsyncIterator, Optional
import aiohttp

from app.config.settings import settings
from app.observability.logger import emit
from app.stt.adapter import BaseSTTAdapter, STTEvent


KEYWORDS = [
    "EMI:3",
    "loan:2",
    "due date:2",
    "principal:2",
    "payment:2",
    "promise to pay:3",
    "Nova Finance:3",
    "interest rate:2",
    "rupees:2",
]


class DeepgramSTTAdapter(BaseSTTAdapter):
    def __init__(self):
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._event_queue: asyncio.Queue[STTEvent] = asyncio.Queue()
        self._running = False
        self._read_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if not settings.deepgram_api_key:
            return

        params = {
            "model": settings.deepgram_model,
            "language": settings.deepgram_language,
            "punctuate": "true",
            "interim_results": "true",
            "endpointing": str(settings.silence_timeout_ms),
            "encoding": "linear16",
            "sample_rate": str(settings.audio_sample_rate),
            "channels": str(settings.audio_channels),
            "keywords": KEYWORDS,
        }
        query_string = urllib.parse.urlencode(params, doseq=True)
        url = f"wss://api.deepgram.com/v1/listen?{query_string}"

        headers = {"Authorization": f"Token {settings.deepgram_api_key}"}

        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(url, headers=headers)
        self._running = True
        self._read_task = asyncio.create_task(self._reader_loop())

    async def _reader_loop(self) -> None:
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])
                    if alternatives:
                        alt = alternatives[0]
                        transcript = alt.get("transcript", "")
                        confidence = alt.get("confidence", 1.0)
                        is_final = data.get("is_final", False)
                        start_time = data.get("start", 0.0)
                        duration = data.get("duration", 0.0)

                        if transcript.strip():
                            event = STTEvent(
                                type="final" if is_final else "partial",
                                text=transcript,
                                is_final=is_final,
                                confidence=confidence,
                                start_time=start_time,
                                end_time=start_time + duration,
                            )
                            await self._event_queue.put(event)

                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            emit({"type": "stt_error", "error": str(e)})

    async def send_audio(self, audio_chunk: bytes) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_bytes(audio_chunk)

    async def events(self) -> AsyncIterator[STTEvent]:
        while self._running or not self._event_queue.empty():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        self._running = False
        if self._read_task:
            self._read_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
