# WebSocket Protocol Specification

## 1. Overview
The WebSocket endpoint `/ws` operates a full-duplex communication channel transmitting raw binary PCM audio frames alongside JSON-encoded control events.

## 2. Audio Specifications
- **Format**: Linear PCM 16-bit signed, little-endian.
- **Sampling Rate**: 16,000 Hz (16 kHz).
- **Channels**: Mono (1 channel).
- **Frame Duration**: 20 ms to 100 ms (default: 20 ms / 640 bytes per frame).

## 3. Client-to-Server Messages

### 3.1 Binary Audio Frame
Raw bytes representing microphone audio sampled at 16 kHz PCM 16-bit mono.

### 3.2 JSON Control Messages

#### Start Session
```json
{
  "type": "start",
  "auth_token": "optional_bearer_token",
  "customer_id": "optional_initial_id",
  "sample_rate": 16000,
  "channels": 1
}
```

#### Playback Progress
Sent periodically by the client to report how many milliseconds of agent audio have played:
```json
{
  "type": "playback_progress",
  "turn_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "played_ms": 1250,
  "words_spoken": 6
}
```

#### Interruption Hint
```json
{
  "type": "interrupt_hint",
  "energy": 0.82
}
```

#### End Call
```json
{
  "type": "end",
  "reason": "client_hangup"
}
```

## 4. Server-to-Client Messages

### 4.1 Binary Audio Frame
Raw bytes of agent speech synthesized by the TTS engine (MP3 or Linear PCM chunks).

### 4.2 JSON Control Events

#### Session Ready
```json
{
  "type": "session_ready",
  "data": {
    "session_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
    "call_id": "CALL-A1B2C3D4",
    "agent_name": "Priya",
    "company_name": "Nova Finance"
  }
}
```

#### Transcript Events
```json
{
  "type": "transcript_partial",
  "data": { "text": "I would like to check my" }
}
```
```json
{
  "type": "transcript_final",
  "data": {
    "text": "I would like to check my loan balance.",
    "confidence": 0.96
  }
}
```

#### Agent Output & State
```json
{
  "type": "agent_state",
  "data": { "state": "listening | thinking | speaking" }
}
```
```json
{
  "type": "agent_text",
  "data": {
    "text": "Your outstanding balance is 45,000 rupees.",
    "turn_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
  }
}
```

#### Barge-In Clear Playback
Instructs the browser to instantly purge its audio playback queue:
```json
{
  "type": "clear_playback"
}
```

#### Escalation & Session Closure
```json
{
  "type": "escalation_started",
  "data": { "state": "ESCALATE" }
}
```
```json
{
  "type": "session_ended",
  "data": { "reason": "normal_closure | timeout | max_duration" }
}
```
