# Architecture Decision Record 001: Provider Selection & Unit Economics

## Context
A real-time voice agent in the BFSI / loan servicing domain requires:
1. Ultra-low end-to-end latency (< 1.2s from caller speech stop to audio response).
2. Natural speech prosody for clear articulation of financial numbers and polite tone.
3. Strict adherence to identity verification and regulatory recovery policies.
4. Robust fallback handling for local offline testing and cost efficiency.

## Decisions

### 1. Speech-to-Text: Deepgram Nova-2 (Hosted) with Local Fallback
- **Choice**: Deepgram Nova-2 streaming WebSocket API (`wss://api.deepgram.com/v1/listen`).
- **Rationale**: Best-in-class latency (< 250 ms), streaming interim transcripts, endpointing signals, and domain keyword biasing (`EMI`, `loan`, `due date`, `Nova Finance`).
- **Fallback**: In-memory `LocalSTTAdapter` for offline testing and deterministic CI runs.

### 2. LLM: Claude Haiku 4.5 with Claude Sonnet 4.5 Fallback
- **Choice**: Anthropic Claude Haiku 4.5 as primary conversational engine.
- **Rationale**: Minimal time-to-first-token (TTFT ~ 300 ms), high structured tool calling reliability, strict instruction following for BFSI constraints, and favorable cost economics (~$0.25 / MTok input).
- **Fallback**: Claude Sonnet 4.5 activated automatically upon provider errors or complex escalation reviews.

### 3. Text-to-Speech: ElevenLabs Turbo v2 with Local Fallback & Phrase Caching
- **Choice**: ElevenLabs Turbo v2 streaming endpoint with custom voice persona (`Priya`).
- **Rationale**: Low latency streaming chunks, high naturalness and human-like empathy.
- **Optimization**: Static audio phrase caching for greetings and disclosure disclaimers eliminates TTS latency and API costs on standard conversational milestones.

### 4. Concurrency & Transport: FastAPI WebSocket with Asyncio Task Isolation
- **Choice**: Single WebSocket connection per call managing separate concurrent asyncio tasks for audio ingestion, STT streaming, LLM generation, and TTS playback.
- **Rationale**: Enables sub-300 ms barge-in interruptions by instantly cancelling downstream tasks without tearing down the underlying connection.
