# Production Runbook & Operations Guide

## 1. System Health & Diagnostics

### 1.1 Health Check Endpoint
To inspect service availability and active provider configuration:
```bash
curl -i http://localhost:8000/health
```
Expected response:
```json
{
  "status": "healthy",
  "agent": "Priya",
  "company": "Nova Finance",
  "primary_model": "claude-haiku-4-5",
  "stt_provider": "deepgram",
  "tts_provider": "elevenlabs"
}
```

### 1.2 Inspect Escalation Queue
To review callers transferred to the human queue:
```bash
curl http://localhost:8000/api/escalations
```

## 2. Call Inspection & Replay

### 2.1 List Recorded Calls
```bash
python scripts/replay_call.py --list
```

### 2.2 Inspect Call Timeline
Renders structured turns, transitions, tool calls, and latencies for a specific call ID:
```bash
python scripts/replay_call.py CALL-XXXXXXXX
```

### 2.3 Re-Execute Call Utterances
Re-runs caller utterances through the live orchestrator to debug logic or prompt changes:
```bash
python scripts/replay_call.py CALL-XXXXXXXX --reexecute
```

## 3. Incident Playbooks

### Incident A: LLM Provider Latency Spike or Outage
- **Symptoms**: `transcript_to_llm_first_token_ms` exceeds 2000 ms; log alerts for `llm_rate_limit`.
- **Immediate Action**:
  1. The system automatically shifts to `FALLBACK_LLM_MODEL` (`claude-sonnet-4-5`) upon repeated retries.
  2. If upstream Anthropic service is degraded, verify status on `status.anthropic.com`.
  3. Temporarily decrease max conversation history window in `AgentOrchestrator`.

### Incident B: False Barge-in Spikes
- **Symptoms**: High rate of `barge_in_detected` with caller utterances containing silence or single non-words.
- **Immediate Action**:
  1. Verify browser users are using headphones to eliminate speaker-to-mic acoustic bleed.
  2. Increase `BARGE_IN_MIN_DURATION_MS` in `.env` from 300 ms to 450 ms.
  3. Increase Energy VAD threshold in `app/audio/vad.py` if background noise is elevated.

### Incident C: Database Connection Failure
- **Symptoms**: 500 error logged during tool execution (`verify_identity` or `record_payment_promise`).
- **Immediate Action**:
  1. Verify SQLite / PostgreSQL file permissions or connection pool capacity.
  2. Re-run `python scripts/seed_db.py` to restore deterministic schema and records in staging.

## 4. Deployment & Rollback (Google Cloud Run)

### 4.1 Deployment Command
```bash
gcloud run deploy voice-loan-agent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 1 \
  --concurrency 20 \
  --timeout 600
```

### 4.2 Rollback
```bash
gcloud run services update-traffic voice-loan-agent \
  --to-revisions=PREVIOUS_REVISION_NAME=100
```
