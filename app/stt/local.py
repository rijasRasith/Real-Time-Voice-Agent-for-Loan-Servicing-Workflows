from __future__ import annotations

import asyncio
from typing import AsyncIterator
from app.stt.adapter import BaseSTTAdapter, STTEvent


class LocalSTTAdapter(BaseSTTAdapter):
    def __init__(self):
        self._queue: asyncio.Queue[STTEvent] = asyncio.Queue()
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def send_audio(self, audio_chunk: bytes) -> None:
        pass

    async def inject_transcript(
        self, text: str, is_final: bool = True, confidence: float = 0.95
    ) -> None:
        await self._queue.put(
            STTEvent(
                type="final" if is_final else "partial",
                text=text,
                is_final=is_final,
                confidence=confidence,
            )
        )

    async def events(self) -> AsyncIterator[STTEvent]:
        while self._running or not self._queue.empty():
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        self._running = False
