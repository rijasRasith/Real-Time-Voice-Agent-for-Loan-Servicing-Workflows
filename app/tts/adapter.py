from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass
class AudioChunk:
    data: bytes
    turn_id: str
    sequence_number: int
    is_last: bool = False


class BaseTTSAdapter(abc.ABC):
    @abc.abstractmethod
    async def synthesize_stream(
        self, text: str, turn_id: str
    ) -> AsyncIterator[AudioChunk]:
        pass

    @abc.abstractmethod
    async def cancel(self) -> None:
        pass
