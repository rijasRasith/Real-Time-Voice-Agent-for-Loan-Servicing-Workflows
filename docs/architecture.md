# Architecture Specification

## 1. High-Level Data Flow

```
 Browser (mic + speaker)
        |   audio frames (up)      audio frames (down) + control events
        v                                  ^
 +--------------------------------------------------------+
 |              FastAPI WebSocket Gateway                 |
 |   session manager | protocol | auth token | limits     |
 +--------------------------------------------------------+
        |                                  ^
        v                                  |
 +-------------+   transcripts   +------------------+   text chunks   +-------------+
 |  STT stream | --------------> |  Orchestrator    | --------------> | TTS stream  |
 |  (Deepgram) |   partial/final |  (turn manager + |                 | (ElevenLabs)|
 +-------------+                 |   state machine) |                 +-------------+
                                 +------------------+
                                    |            ^
                         tool calls |            | tool results
                                    v            |
                              +------------------------+
                              |  Tool layer + policy   |
                              |  guard (validation,    |
                              |  allowlists, audit)    |
                              +------------------------+
                                    |
                                    v
                              +------------------------+
                              | Mock loan / CRM DB     |
                              | (PostgreSQL / SQLite)  |
                              +------------------------+

 Side channels: structured logger, telemetry metrics, replay store, escalation queue
```

## 2. Concurrency and Session Model

Each inbound call is managed as an independent `SessionConnection` with several concurrent asynchronous tasks:
1. **Audio Ingestion Task**: reads binary audio frames from the client WebSocket, passes them through framing and energy VAD, and streams into the STT provider.
2. **STT Event Consumer**: consumes partial and final transcripts from STT, passes them into the `TurnManager` to determine end-of-turn or interruption events.
3. **Turn Execution Loop**: upon an end-of-turn decision, builds the state-gated system prompt, executes the streaming LLM with tool calling, and chunks output into natural sentence boundaries.
4. **TTS Streaming Pipeline**: translates text chunks into audio streams tagged with turn ID and sequence numbers, sending raw audio bytes to the client.
5. **Supervisor & Interruption Cancel**: upon barge-in detection, cancels both the in-flight LLM stream and the TTS synthesis stream immediately, flushes client playback buffers via `clear_playback`, and resets conversation state to listening.

## 3. Component Responsibilities

| Component | Responsibility | Forbidden Actions |
|---|---|---|
| **Gateway** | Manages WebSocket connections, protocol validation, timeouts, and concurrency bounds | No direct business logic |
| **Session Manager** | Tracks connection state, orchestrates clean task teardown, and avoids leaks | No domain loan logic |
| **STT Adapter** | Streams audio to provider and normalizes partial/final transcripts with confidence scores | Does not decide end-of-turn |
| **Turn Manager** | End-of-turn detection, backchannel filtering, adaptive timeouts for digits, barge-in | Does not invoke LLM |
| **Orchestrator** | Coordinates state machine, prompt construction, tool execution loops, and turn logging | Does not talk directly to audio hardware |
| **Tool Executor** | Validates Pydantic schemas, enforces policy preconditions, executes idempotently, audits | Does not format conversational responses |
| **TTS Adapter** | Synthesizes text chunks to audio frames, provides static phrase cache, instant cancellation | Does not generate dialogue |
| **Escalation Service** | Packages call context, sets priority, enqueues handoff for human operator review | Does not drop calls silently |
