from __future__ import annotations

import asyncio
from typing import AsyncIterator
from app.tts.adapter import AudioChunk, BaseTTSAdapter


class LocalTTSAdapter(BaseTTSAdapter):
    def __init__(self):
        self._cancelled = False

    async def cancel(self) -> None:
        self._cancelled = True

    async def synthesize_stream(
        self, text: str, turn_id: str
    ) -> AsyncIterator[AudioChunk]:
        self._cancelled = False
        sample_audio = b"\x00\x00" * 320
        for seq in range(3):
            if self._cancelled:
                break
            await asyncio.sleep(0.02)
            yield AudioChunk(
                data=sample_audio,
                turn_id=turn_id,
                sequence_number=seq,
                is_last=(seq == 2),
            )
