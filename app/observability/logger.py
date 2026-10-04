from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

from app.config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(message)s",
)
_root_logger = logging.getLogger("voice_agent")


def _mask(value: Any, key: str = "") -> Any:
    sensitive_keys = {"pin", "security_pin", "last_four", "phone", "date_of_birth", "account"}
    if isinstance(value, dict):
        return {k: _mask(v, k) for k, v in value.items()}
    if isinstance(key, str) and any(s in key.lower() for s in sensitive_keys):
        return "***"
    return value


def _serialize(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def emit(record: dict):
    _root_logger.info(json.dumps(record, default=_serialize))


@dataclass
class SpanContext:
    name: str
    start_time: float = field(default_factory=time.monotonic)
    tags: dict = field(default_factory=dict)

    def elapsed_ms(self) -> float:
        return round((time.monotonic() - self.start_time) * 1000, 2)


@dataclass
class TurnLatency:
    end_of_speech_to_transcript_ms: Optional[float] = None
    transcript_to_llm_first_token_ms: Optional[float] = None
    llm_first_token_to_tts_audio_ms: Optional[float] = None
    end_of_speech_to_first_audio_ms: Optional[float] = None
    tool_durations_ms: list[dict] = field(default_factory=list)
    total_turn_ms: Optional[float] = None


@dataclass
class TurnLog:
    session_id: str
    call_id: str
    turn_id: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    agent_version: str = "1.0.0"
    primary_model: str = settings.primary_llm_model

    state_before: str = ""
    state_after: str = ""
    transitions_fired: list[str] = field(default_factory=list)
    guards_blocked: list[str] = field(default_factory=list)

    final_transcript: str = ""
    stt_confidence: float = 0.0
    partial_count: int = 0
    word_count: int = 0

    text_spoken: str = ""
    text_generated_not_spoken: str = ""
    interrupted: bool = False

    tools_called: list[dict] = field(default_factory=list)
    latency: TurnLatency = field(default_factory=TurnLatency)

    retries: int = 0
    fallbacks_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    policy_flags: list[str] = field(default_factory=list)
    escalation_reason: Optional[str] = None

    input_tokens: int = 0
    output_tokens: int = 0
    tts_characters: int = 0
    stt_seconds: float = 0.0
    estimated_cost_usd: float = 0.0

    def add_tool_call(
        self,
        tool_name: str,
        arg_summary: dict,
        result_status: str,
        duration_ms: float,
    ):
        self.tools_called.append(
            {
                "tool": tool_name,
                "args": _mask(arg_summary),
                "result_status": result_status,
                "duration_ms": duration_ms,
            }
        )
        self.latency.tool_durations_ms.append(
            {"tool": tool_name, "duration_ms": duration_ms}
        )

    def estimate_cost(self):
        haiku_input_per_mtok = 0.00025
        haiku_output_per_mtok = 0.00125
        deepgram_per_minute = 0.0059
        elevenlabs_per_char = 0.000030

        self.estimated_cost_usd = round(
            (self.input_tokens / 1_000_000) * haiku_input_per_mtok * 1_000_000
            + (self.output_tokens / 1_000_000) * haiku_output_per_mtok * 1_000_000
            + (self.stt_seconds / 60) * deepgram_per_minute
            + self.tts_characters * elevenlabs_per_char,
            6,
        )

    def emit(self):
        self.estimate_cost()
        record = asdict(self)
        record["type"] = "turn_log"
        emit(record)


class ReplayStore:
    def __init__(self):
        self.path = settings.replay_store_path
        os.makedirs(self.path, exist_ok=True)

    def _call_path(self, call_id: str) -> str:
        return os.path.join(self.path, f"{call_id}.jsonl")

    def append(self, call_id: str, record: dict):
        with open(self._call_path(call_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=_serialize) + "\n")

    def load(self, call_id: str) -> list[dict]:
        path = self._call_path(call_id)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def list_calls(self) -> list[str]:
        return [
            f.replace(".jsonl", "")
            for f in os.listdir(self.path)
            if f.endswith(".jsonl")
        ]


replay_store = ReplayStore()
