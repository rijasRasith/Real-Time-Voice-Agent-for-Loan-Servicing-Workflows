from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict, Optional, Set
from fastapi import WebSocket

from app.agent.orchestrator import agent_orchestrator
from app.audio.framing import AudioFramer
from app.audio.vad import EnergyVAD
from app.config.settings import settings
from app.data.models import CallDisposition
from app.data.repository import call_record_repo
from app.observability.logger import emit
from app.stt import get_stt_adapter
from app.tools.executor import SessionState
from app.tts import get_tts_adapter


class SessionConnection:
    def __init__(self, websocket: WebSocket, session_id: str, call_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self.call_id = call_id
        self.created_at = time.monotonic()
        self.last_activity = time.monotonic()

        self.session_state = SessionState(
            session_id=session_id,
            call_id=call_id,
            state="GREETING",
        )

        self.conversation_history: list[dict] = []
        self.stt_adapter = get_stt_adapter()
        self.tts_adapter = get_tts_adapter()
        self.framer = AudioFramer(sample_rate=settings.audio_sample_rate)
        self.vad = EnergyVAD()

        self.incoming_audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self.is_agent_speaking = False
        self.current_turn_task: Optional[asyncio.Task] = None
        self.current_tts_task: Optional[asyncio.Task] = None
        self.tasks: Set[asyncio.Task] = set()

    def touch(self):
        self.last_activity = time.monotonic()

    def is_expired(self) -> bool:
        now = time.monotonic()
        if (now - self.created_at) > settings.max_call_duration_seconds:
            return True
        if (now - self.last_activity) > settings.max_idle_seconds:
            return True
        return False

    async def cancel_ongoing_generation(self):
        if self.current_turn_task and not self.current_turn_task.done():
            self.current_turn_task.cancel()
        if self.current_tts_task and not self.current_tts_task.done():
            self.current_tts_task.cancel()
        await self.tts_adapter.cancel()
        self.is_agent_speaking = False

    async def cleanup(self):
        await self.cancel_ongoing_generation()
        for t in list(self.tasks):
            if not t.done():
                t.cancel()
        await self.stt_adapter.close()
        call_record_repo.close(
            self.call_id,
            CallDisposition.RESOLVED
            if self.session_state.state in ("WRAP_UP", "CLOSED")
            else (
                CallDisposition.ESCALATED
                if self.session_state.is_escalated
                else CallDisposition.ABANDONED
            ),
        )


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, SessionConnection] = {}

    def active_count(self) -> int:
        return len(self._sessions)

    def create_session(self, websocket: WebSocket) -> Optional[SessionConnection]:
        if len(self._sessions) >= settings.max_concurrent_sessions:
            return None

        session_id = str(uuid.uuid4())
        call_id = f"CALL-{uuid.uuid4().hex[:8].upper()}"
        call_record_repo.create(call_id=call_id)

        session = SessionConnection(websocket, session_id, call_id)
        self._sessions[session_id] = session
        emit({"type": "session_created", "session_id": session_id, "call_id": call_id})
        return session

    def get_session(self, session_id: str) -> Optional[SessionConnection]:
        return self._sessions.get(session_id)

    async def remove_session(self, session_id: str):
        session = self._sessions.pop(session_id, None)
        if session:
            await session.cleanup()
            emit({"type": "session_removed", "session_id": session_id})


session_manager = SessionManager()
