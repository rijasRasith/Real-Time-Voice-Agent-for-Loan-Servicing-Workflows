from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional
import aiohttp

from app.config.settings import settings
from app.observability.logger import emit
from app.tts.adapter import AudioChunk, BaseTTSAdapter


class ElevenLabsTTSAdapter(BaseTTSAdapter):
    def __init__(self):
        self._cancelled = False
        self._static_cache: dict[str, bytes] = {}

    async def cancel(self) -> None:
        self._cancelled = True

    async def synthesize_stream(
        self, text: str, turn_id: str
    ) -> AsyncIterator[AudioChunk]:
        self._cancelled = False
        cleaned_text = text.strip()
        if not cleaned_text:
            return

        if cleaned_text in self._static_cache:
            data = self._static_cache[cleaned_text]
            yield AudioChunk(
                data=data,
                turn_id=turn_id,
                sequence_number=0,
                is_last=True,
            )
            return

        if not settings.elevenlabs_api_key:
            return

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}/stream"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": cleaned_text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
            },
        }

        seq = 0
        total_audio = bytearray()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        async for chunk in resp.content.iter_chunked(2048):
                            if self._cancelled:
                                break
                            total_audio.extend(chunk)
                            yield AudioChunk(
                                data=chunk,
                                turn_id=turn_id,
                                sequence_number=seq,
                                is_last=False,
                            )
                            seq += 1

                        if not self._cancelled:
                            yield AudioChunk(
                                data=b"",
                                turn_id=turn_id,
                                sequence_number=seq,
                                is_last=True,
                            )
                            if len(cleaned_text) < 120:
                                self._static_cache[cleaned_text] = bytes(total_audio)
                    else:
                        error_text = await resp.text()
                        emit({"type": "tts_error", "status": resp.status, "detail": error_text})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            emit({"type": "tts_exception", "error": str(e)})
