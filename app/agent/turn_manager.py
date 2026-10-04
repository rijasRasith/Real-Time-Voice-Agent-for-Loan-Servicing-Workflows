from __future__ import annotations

import re
import time
from typing import Optional
from pydantic import BaseModel

from app.config.settings import settings


BACKCHANNEL_WORDS = {"hmm", "mm", "yeah", "uh-huh", "okay", "ok", "right", "sure"}
INCOMPLETE_SUFFIXES = [
    "and",
    "or",
    "because",
    "that",
    "my loan number is",
    "which is",
    "i want to",
    "amount is",
    "date is",
]


class TurnDecision(BaseModel):
    is_end_of_turn: bool
    is_barge_in: bool
    should_extend_timeout: bool
    reason: str


class TurnManager:
    def __init__(self):
        self._last_speech_time = 0.0
        self._current_transcript = ""

    def evaluate_transcript(
        self,
        text: str,
        is_final: bool,
        confidence: float,
        agent_speaking: bool,
        awaiting_digits: bool = False,
    ) -> TurnDecision:
        now = time.monotonic()
        cleaned = text.strip().lower()

        if not cleaned:
            return TurnDecision(
                is_end_of_turn=False,
                is_barge_in=False,
                should_extend_timeout=False,
                reason="Empty transcript",
            )

        words = cleaned.split()

        if agent_speaking:
            if len(words) == 1 and words[0] in BACKCHANNEL_WORDS:
                return TurnDecision(
                    is_end_of_turn=False,
                    is_barge_in=False,
                    should_extend_timeout=False,
                    reason="Backchannel ignored during playback",
                )

            if len(words) >= 2 or len(cleaned) >= 8:
                return TurnDecision(
                    is_end_of_turn=False,
                    is_barge_in=True,
                    should_extend_timeout=False,
                    reason="Barge-in speech detected",
                )

        if not is_final:
            has_digits = bool(re.search(r"\d", cleaned))
            if awaiting_digits or has_digits:
                return TurnDecision(
                    is_end_of_turn=False,
                    is_barge_in=False,
                    should_extend_timeout=True,
                    reason="Awaiting complete digits/number sequence",
                )

            return TurnDecision(
                is_end_of_turn=False,
                is_barge_in=False,
                should_extend_timeout=False,
                reason="Partial transcript received",
            )

        for suffix in INCOMPLETE_SUFFIXES:
            if cleaned.endswith(suffix):
                return TurnDecision(
                    is_end_of_turn=False,
                    is_barge_in=False,
                    should_extend_timeout=True,
                    reason=f"Incomplete trailing phrase '{suffix}'",
                )

        if confidence < settings.end_of_turn_confidence_threshold:
            return TurnDecision(
                is_end_of_turn=True,
                is_barge_in=False,
                should_extend_timeout=False,
                reason="Low confidence final transcript",
            )

        return TurnDecision(
            is_end_of_turn=True,
            is_barge_in=False,
            should_extend_timeout=False,
            reason="Completed user utterance",
        )

    def get_silence_timeout(self, awaiting_digits: bool) -> float:
        if awaiting_digits:
            return settings.number_silence_timeout_ms / 1000.0
        return settings.silence_timeout_ms / 1000.0


turn_manager = TurnManager()
