from __future__ import annotations

import audioop
import math


class EnergyVAD:
    def __init__(self, energy_threshold: int = 500):
        self.energy_threshold = energy_threshold

    def is_speech(self, pcm_frame: bytes) -> bool:
        if not pcm_frame or len(pcm_frame) < 2:
            return False
        try:
            rms = audioop.rms(pcm_frame, 2)
            return rms > self.energy_threshold
        except Exception:
            return False

    def calculate_rms(self, pcm_frame: bytes) -> int:
        if not pcm_frame or len(pcm_frame) < 2:
            return 0
        try:
            return audioop.rms(pcm_frame, 2)
        except Exception:
            return 0
