from __future__ import annotations

import audioop
import math


class AudioResampler:
    @staticmethod
    def resample_pcm16(
        data: bytes, input_rate: int, output_rate: int = 16000, input_channels: int = 1
    ) -> bytes:
        if not data:
            return b""

        if input_channels > 1:
            data = audioop.tomono(data, 2, 0.5, 0.5)

        if input_rate == output_rate:
            return data

        converted, _ = audioop.ratecv(data, 2, 1, input_rate, output_rate, None)
        return converted
