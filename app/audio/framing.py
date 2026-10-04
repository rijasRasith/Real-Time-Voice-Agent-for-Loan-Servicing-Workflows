from __future__ import annotations

import struct
from typing import Generator, List


class AudioFramer:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, frame_ms: int = 20):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_ms = frame_ms
        self.bytes_per_sample = 2
        self.bytes_per_frame = int(sample_rate * channels * (frame_ms / 1000.0) * self.bytes_per_sample)
        self._buffer = bytearray()

    def add_chunk(self, data: bytes) -> Generator[bytes, None, None]:
        self._buffer.extend(data)
        while len(self._buffer) >= self.bytes_per_frame:
            frame = bytes(self._buffer[: self.bytes_per_frame])
            del self._buffer[: self.bytes_per_frame]
            yield frame

    def flush(self) -> bytes:
        remaining = bytes(self._buffer)
        self._buffer.clear()
        return remaining

    def reset(self):
        self._buffer.clear()
