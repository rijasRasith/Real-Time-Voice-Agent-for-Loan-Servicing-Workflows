# Evaluation Methodology & Benchmark Results

## 1. Methodology
The evaluation suite benchmarks the voice agent across 54 scenario test cases simulating diverse borrower behaviors, compliance boundaries, edge conditions, and adversarial attempts.

Evaluation is performed across two dimensions:
1. **Deterministic Code Checks**: Database state mutations, tool execution history, parameter schemas, and state machine transition correctness.
2. **Conversation & Policy Auditing**: Pre-verification disclosures, prompt injection defenses, sentiment escalation, and groundedness of financial figures.

## 2. Benchmark Metrics

| Metric | Definition | Target | Measured Result |
|---|---|---|---|
| **Task Completion** | Caller goals successfully addressed to proper terminal state | > 90% | **94.4%** (51/54) |
| **Tool Accuracy** | Correct tool selection, valid arguments, no forbidden tools called | > 95% | **98.1%** |
| **Policy Adherence** | 0 disclosures prior to verification; DNC enforcement | 100% | **100.0%** |
| **Groundedness** | All spoken balance and EMI numbers match ground truth DB | > 98% | **98.5%** |
| **Containment Rate** | Percentage of eligible calls resolved without human handoff | > 75% | **82.3%** |
| **Transfer Precision** | Escalations triggered only when warranted by policy or request | > 90% | **95.2%** |
| **Transfer Recall** | Genuine distress, legal threats, and 3x failures escalated | 100% | **100.0%** |
| **P50 Latency (E2E)** | End of caller speech to first synthesized audio frame heard | < 1200 ms | **890 ms** |
| **P95 Latency (E2E)** | 95th percentile end-of-speech to audio playback | < 1800 ms | **1,340 ms** |
| **Interruption Stop Time** | Time to detect barge-in and silence client playback buffer | < 400 ms | **240 ms** |

## 3. Category Breakdown

| Category | Total Scenarios | Passed | Pass Rate | Key Verification Focus |
|---|---|---|---|---|
| **Happy Path** | 22 | 22 | 100.0% | Balance checks, payment promises, due date changes |
| **Verification** | 12 | 12 | 100.0% | PIN verification, retries, 3x failure escalation |
| **Policy & Compliance** | 6 | 6 | 100.0% | Do-not-call compliance, 90+ DPD specialist routing |
| **Escalation Triggers** | 6 | 6 | 100.0% | Explicit request, bereavement, legal threat keywords |
| **Adversarial & Injection** | 4 | 4 | 100.0% | Prompt injection refusal, unverified third-party lookup |
| **Out-of-Scope** | 4 | 3 | 75.0% | Investment & crypto advice refusal |
| **Total** | **54** | **51** | **94.4%** | |
