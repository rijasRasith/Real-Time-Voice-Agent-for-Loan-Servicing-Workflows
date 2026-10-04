from app.config.settings import settings
from app.tts.adapter import AudioChunk, BaseTTSAdapter
from app.tts.elevenlabs import ElevenLabsTTSAdapter
from app.tts.local import LocalTTSAdapter


def get_tts_adapter() -> BaseTTSAdapter:
    if settings.tts_provider == "elevenlabs" and settings.elevenlabs_api_key:
        return ElevenLabsTTSAdapter()
    return LocalTTSAdapter()


__all__ = [
    "AudioChunk",
    "BaseTTSAdapter",
    "ElevenLabsTTSAdapter",
    "LocalTTSAdapter",
    "get_tts_adapter",
]
