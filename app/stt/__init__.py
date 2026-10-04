from app.config.settings import settings
from app.stt.adapter import BaseSTTAdapter, STTEvent
from app.stt.deepgram import DeepgramSTTAdapter
from app.stt.local import LocalSTTAdapter


def get_stt_adapter() -> BaseSTTAdapter:
    if settings.stt_provider == "deepgram" and settings.deepgram_api_key:
        return DeepgramSTTAdapter()
    return LocalSTTAdapter()


__all__ = [
    "BaseSTTAdapter",
    "STTEvent",
    "DeepgramSTTAdapter",
    "LocalSTTAdapter",
    "get_stt_adapter",
]
