from __future__ import annotations

import asyncio
import json
import time
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.orchestrator import agent_orchestrator
from app.agent.turn_manager import turn_manager
from app.config.settings import settings
from app.gateway.protocol import PlaybackProgressMessage, ServerEvent, StartMessage
from app.gateway.session_manager import SessionConnection, session_manager
from app.llm.adapter import normalize_for_tts
from app.observability.logger import emit


router = APIRouter()


async def send_json_event(ws: WebSocket, event_type: str, data: dict = None, **kwargs):
    payload = {"type": event_type, "data": data or {}, **kwargs}
    await ws.send_text(json.dumps(payload))


async def run_stt_consumer(session: SessionConnection):
    try:
        async for event in session.stt_adapter.events():
            session.touch()
            if not event.text.strip():
                continue

            if event.is_final:
                await send_json_event(
                    session.websocket,
                    "transcript_final",
                    {"text": event.text, "confidence": event.confidence},
                )
            else:
                await send_json_event(
                    session.websocket,
                    "transcript_partial",
                    {"text": event.text},
                )

            decision = turn_manager.evaluate_transcript(
                text=event.text,
                is_final=event.is_final,
                confidence=event.confidence,
                agent_speaking=session.is_agent_speaking,
            )

            if decision.is_barge_in and session.is_agent_speaking:
                barge_in_time = time.monotonic()
                emit({
                    "type": "barge_in_detected",
                    "session_id": session.session_id,
                    "trigger_text": event.text,
                })
                await session.cancel_ongoing_generation()
                await send_json_event(session.websocket, "clear_playback")
                await send_json_event(
                    session.websocket, "agent_state", {"state": "listening"}
                )
                continue

            if decision.is_end_of_turn and not session.is_agent_speaking:
                await send_json_event(
                    session.websocket, "agent_state", {"state": "thinking"}
                )
                session.current_turn_task = asyncio.create_task(
                    execute_agent_turn(session, event.text, event.confidence)
                )

    except asyncio.CancelledError:
        pass
    except Exception as e:
        emit({"type": "stt_consumer_error", "session_id": session.session_id, "error": str(e)})


async def execute_agent_turn(
    session: SessionConnection, user_text: str, confidence: float
):
    turn_id = str(uuid.uuid4())
    try:
        session.is_agent_speaking = True
        await send_json_event(session.websocket, "agent_state", {"state": "speaking"})

        full_response = ""
        sentence_buffer = ""

        async for chunk in agent_orchestrator.process_turn(
            session=session.session_state,
            user_utterance=user_text,
            conversation_history=session.conversation_history,
            stt_confidence=confidence,
        ):
            full_response += chunk
            sentence_buffer += chunk

            await send_json_event(
                session.websocket,
                "agent_text",
                {"text": chunk, "turn_id": turn_id},
            )

            if any(punct in sentence_buffer for punct in (".", "?", "!")):
                norm_chunk = normalize_for_tts(sentence_buffer)
                sentence_buffer = ""
                async for audio_chunk in session.tts_adapter.synthesize_stream(
                    norm_chunk, turn_id
                ):
                    if audio_chunk.data:
                        await session.websocket.send_bytes(audio_chunk.data)

        if sentence_buffer.strip():
            norm_chunk = normalize_for_tts(sentence_buffer)
            async for audio_chunk in session.tts_adapter.synthesize_stream(
                norm_chunk, turn_id
            ):
                if audio_chunk.data:
                    await session.websocket.send_bytes(audio_chunk.data)

        if session.session_state.is_escalated:
            await send_json_event(
                session.websocket,
                "escalation_started",
                {"state": session.session_state.state},
            )

        if session.session_state.state == "CLOSED":
            await send_json_event(
                session.websocket,
                "session_ended",
                {"reason": "normal_closure"},
            )

    except asyncio.CancelledError:
        emit({"type": "turn_cancelled", "session_id": session.session_id, "turn_id": turn_id})
    except Exception as e:
        emit({"type": "turn_error", "session_id": session.session_id, "error": str(e)})
    finally:
        session.is_agent_speaking = False
        await send_json_event(session.websocket, "agent_state", {"state": "listening"})


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    session = session_manager.create_session(websocket)
    if not session:
        await websocket.close(code=1008, reason="Max concurrent sessions reached")
        return

    try:
        await session.stt_adapter.start()
        stt_task = asyncio.create_task(run_stt_consumer(session))
        session.tasks.add(stt_task)

        await send_json_event(
            websocket,
            "session_ready",
            {
                "session_id": session.session_id,
                "call_id": session.call_id,
                "agent_name": settings.agent_name,
                "company_name": settings.company_name,
            },
        )

        async for message in websocket.iter_bytes():
            session.touch()
            if len(message) > settings.max_frame_bytes:
                continue

            for frame in session.framer.add_chunk(message):
                await session.stt_adapter.send_audio(frame)

    except WebSocketDisconnect:
        emit({"type": "client_disconnected", "session_id": session.session_id})
    except Exception as e:
        emit({"type": "websocket_error", "session_id": session.session_id, "error": str(e)})
    finally:
        await session_manager.remove_session(session.session_id)
