# Workflow State Machine Specification

## 1. Overview
The agent dialogue flow is governed by a deterministic, guarded finite state machine (`WorkflowStateMachine`). Prompt instructions and exposed tool definitions are dynamically filtered according to the active workflow state.

## 2. State Definitions

| State | Objective | Permitted Tools | Guard Conditions & Exits |
|---|---|---|---|
| **GREETING** | Disclose automated assistant identity, purpose, recording notice | None | Transitions to `IDENTIFY` upon customer acknowledgment |
| **IDENTIFY** | Collect customer ID or registered phone | None | Transitions to `VERIFY` once customer record candidate is located |
| **VERIFY** | Collect last 4 account digits and 6-digit security PIN | `verify_identity`, `escalate_to_human` | Requires `verified = true` to exit to `INTENT`. Max 3 failures force `ESCALATE`. |
| **INTENT** | Determine loan servicing goal | `escalate_to_human` | Transitions to `SERVICE` when intent is classified |
| **SERVICE** | Execute loan balance, payment history, promise, or complaint | `get_loan_summary`, `get_payment_history`, `record_payment_promise`, `request_due_date_change`, `log_complaint`, `escalate_to_human` | Guarded by verification flag in code. Write actions transition to `CONFIRM` or `WRAP_UP`. |
| **CONFIRM** | Read back action parameters and obtain explicit verbal confirmation | `record_payment_promise`, `request_due_date_change`, `escalate_to_human` | Allowed only after explicit confirmation |
| **WRAP_UP** | Offer additional assistance and close | `end_call`, `escalate_to_human` | Transitions to `CLOSED` when caller confirms done |
| **ESCALATE** | Package context and hand off to human queue | `escalate_to_human` | Transitions to `CLOSED` upon handoff completion |
| **CLOSED** | Terminal call state | None | Terminal |

## 3. Transition Rules & Invariants
1. **Precondition Guards**: Forward transitions into `INTENT`, `SERVICE`, or `CONFIRM` are rejected with code enforcement unless `session.verified == True`.
2. **Universal Escalation**: Any state can transition to `ESCALATE` at any time upon explicit human request, severe distress, legal threat, bereavement, or repeated tool failures.
3. **Idempotent Writes**: All write actions executed in `SERVICE` or `CONFIRM` require client-generated or UUID-based idempotency keys.
