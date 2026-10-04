from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass
class STTEvent:
    type: str
    text: str = ""
    is_final: bool = False
    confidence: float = 1.0
    start_time: float = 0.0
    end_time: float = 0.0


class BaseSTTAdapter(abc.ABC):
    @abc.abstractmethod
    async def start(self) -> None:
        pass

    @abc.abstractmethod
    async def send_audio(self, audio_chunk: bytes) -> None:
        pass

    @abc.abstractmethod
    async def events(self) -> AsyncIterator[STTEvent]:
        pass

    @abc.abstractmethod
    async def close(self) -> None:
        pass
