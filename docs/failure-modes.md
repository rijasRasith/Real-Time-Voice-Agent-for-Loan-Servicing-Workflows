# Failure Modes Catalogue

| Failure Mode | Observable Symptom | Automated Detection | Mitigation Strategy |
|---|---|---|---|
| **STT Number Misrecognition** | Incorrect amount or date recorded | Readback confirmation mismatch; confidence < 0.5 | Mandatory readback in CONFIRM state; digit-by-digit verification mode; escalate after 2 retries |
| **STT Stream Disconnect** | Dead air from caller side | WebSocket disconnect code; heartbeat timeout | Automatic reconnect loop with exponential backoff; fallback to local STT adapter |
| **Premature End-of-Turn** | Agent cuts off caller mid-sentence | High barge-in rate on first agent word | Completeness heuristics for trailing conjunctions ("and", "because"); 2000 ms adaptive timeout for numbers |
| **Delayed End-of-Turn** | Awkward long pauses after caller finishes | End-of-speech to TTFT > 1500 ms metric | Tuned 800 ms silence timeout; provider endpointing signal prioritization |
| **Acoustic Feedback / False Barge-in** | Agent interrupts itself mid-turn | Barge-in triggered with 0 caller words | Browser WebRTC echo cancellation (`echoCancellation: true`); client audio queue flush; 300 ms minimum speech threshold |
| **Barge-in Audio Bleed** | Caller interrupts but agent audio continues | Client playback latency telemetry > 500 ms | Immediate `clear_playback` event; server cancels in-flight LLM/TTS tasks; turn ID sequence filtering |
| **LLM Provider Timeout / 429** | Agent pauses indefinitely | HTTP 429 / 504 from Anthropic API | Exponential backoff retry; automatic fallback to Claude Sonnet; graceful escalation transition |
| **Hallucinated Financial Details** | Spoken balance differs from DB | Automated groundedness judge | System prompt strips unverified facts; tools return pre-formatted summaries; numbers cross-checked in unit tests |
| **Database Write Duplicate** | Multiple promises saved for single intent | Duplicate database rows | UUIDv4 idempotency keys on `promises_to_pay` table; single commit transaction |
| **Prompt Injection Attack** | Agent ignores BFSI rules | Injection regex match; policy audit event | Input filter regex; strict per-state tool allowlists; immediate escalation to supervisor |
| **Pre-Verification Data Leakage** | Balance spoken before identity check | Unit test failure; session state check | PolicyGuard enforces verification flag in code prior to SQL query; state machine blocks transitions |
| **Session Memory Leak** | Memory growth over extended calls | Concurrency metrics; task tracker leak checks | Explicit `SessionManager.cleanup()` cancelling all tasks and closing provider streams upon disconnect |
