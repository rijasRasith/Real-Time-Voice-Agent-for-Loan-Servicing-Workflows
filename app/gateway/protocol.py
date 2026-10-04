from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class StartMessage(BaseModel):
    type: Literal["start"] = "start"
    auth_token: Optional[str] = None
    customer_id: Optional[str] = None
    sample_rate: int = 16000
    channels: int = 1


class PlaybackProgressMessage(BaseModel):
    type: Literal["playback_progress"] = "playback_progress"
    turn_id: str
    played_ms: int
    words_spoken: Optional[int] = None


class InterruptHintMessage(BaseModel):
    type: Literal["interrupt_hint"] = "interrupt_hint"
    energy: Optional[float] = None


class EndMessage(BaseModel):
    type: Literal["end"] = "end"
    reason: Optional[str] = "client_hangup"


class ServerEvent(BaseModel):
    type: str
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    data: Optional[Any] = None
    message: Optional[str] = None
