from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import AsyncIterator, Optional, Tuple

from app.agent.state_machine import workflow_state_machine
from app.config.settings import settings
from app.llm.adapter import (
    LLMStreamEvent,
    check_injection,
    llm_adapter,
    normalize_for_tts,
)
from app.llm.prompt_builder import build_system_prompt
from app.observability.logger import TurnLatency, TurnLog, emit, replay_store
from app.tools.definitions import get_tools_for_state
from app.tools.executor import (
    EndCallInput,
    EscalateToHumanInput,
    GetLoanSummaryInput,
    GetPaymentHistoryInput,
    LogComplaintInput,
    RecordPaymentPromiseInput,
    RequestDueDateChangeInput,
    SessionState,
    VerifyIdentityInput,
    tool_executor,
)


ESCALATION_KEYWORDS = {
    "human",
    "agent",
    "representative",
    "manager",
    "supervisor",
    "lawyer",
    "attorney",
    "sue",
    "legal",
    "court",
    "harassment",
    "suicide",
    "death",
    "funeral",
    "hardship",
    "bankrupt",
    "insolvent",
}


class AgentOrchestrator:
    def __init__(self):
        pass

    async def execute_tool(
        self, session: SessionState, tool_name: str, tool_args: dict
    ) -> Tuple[str, dict]:
        start = time.monotonic()
        try:
            if tool_name == "verify_identity":
                parsed_args = VerifyIdentityInput(**tool_args)
                res = tool_executor.verify_identity(session, parsed_args)
                if res.status == "success":
                    workflow_state_machine.transition(session, "INTENT")
                elif "do-not-call" in res.message.lower() or session.verification_attempts >= settings.max_verification_attempts:
                    reason = (
                        "repeated_failure"
                        if session.verification_attempts >= settings.max_verification_attempts
                        else "policy_trigger"
                    )
                    tool_executor.escalate_to_human(
                        session,
                        EscalateToHumanInput(
                            reason_code=reason,
                            summary=res.message,
                        ),
                    )
                    workflow_state_machine.transition(session, "ESCALATE")
            elif tool_name == "get_loan_summary":
                parsed_args = GetLoanSummaryInput(**tool_args)
                res = tool_executor.get_loan_summary(session, parsed_args)
                if res.status == "success":
                    summaries = res.data.get("loans", [])
                    if any(l.get("days_past_due", 0) > settings.overdue_escalation_days for l in summaries):
                        tool_executor.escalate_to_human(
                            session,
                            EscalateToHumanInput(
                                reason_code="policy_trigger",
                                summary="Account exceeds 90 days past due delinquency threshold.",
                            ),
                        )
                        workflow_state_machine.transition(session, "ESCALATE")
            elif tool_name == "get_payment_history":
                parsed_args = GetPaymentHistoryInput(**tool_args)
                res = tool_executor.get_payment_history(session, parsed_args)
            elif tool_name == "record_payment_promise":
                parsed_args = RecordPaymentPromiseInput(**tool_args)
                res = tool_executor.record_payment_promise(session, parsed_args)
                if res.status == "success":
                    workflow_state_machine.transition(session, "WRAP_UP")
            elif tool_name == "request_due_date_change":
                parsed_args = RequestDueDateChangeInput(**tool_args)
                res = tool_executor.request_due_date_change(session, parsed_args)
                if res.status == "success":
                    workflow_state_machine.transition(session, "WRAP_UP")
            elif tool_name == "log_complaint":
                parsed_args = LogComplaintInput(**tool_args)
                res = tool_executor.log_complaint(session, parsed_args)
                if res.status == "success":
                    workflow_state_machine.transition(session, "WRAP_UP")
            elif tool_name == "escalate_to_human":
                parsed_args = EscalateToHumanInput(**tool_args)
                res = tool_executor.escalate_to_human(session, parsed_args)
                workflow_state_machine.transition(session, "ESCALATE")
            elif tool_name == "end_call":
                parsed_args = EndCallInput(**tool_args)
                res = tool_executor.end_call(session, parsed_args)
                workflow_state_machine.transition(session, "CLOSED")
            else:
                res = tool_executor.ToolResult(
                    status="not_allowed", message=f"Unknown tool: {tool_name}"
                )

            duration_ms = round((time.monotonic() - start) * 1000, 2)
            return res.message, {
                "status": res.status,
                "data": res.data,
                "duration_ms": duration_ms,
            }
        except Exception as e:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            return f"Error executing tool: {str(e)}", {
                "status": "error",
                "error": str(e),
                "duration_ms": duration_ms,
            }

    async def process_turn(
        self,
        session: SessionState,
        user_utterance: str,
        conversation_history: list[dict],
        stt_confidence: float = 1.0,
        eos_time: Optional[float] = None,
    ) -> AsyncIterator[str]:
        turn_start = time.monotonic()
        turn_id = str(uuid.uuid4())
        session.turn_count += 1
        state_before = session.state

        turn_log = TurnLog(
            session_id=session.session_id,
            call_id=session.call_id,
            turn_id=turn_id,
            state_before=state_before,
            final_transcript=user_utterance,
            stt_confidence=stt_confidence,
            word_count=len(user_utterance.split()),
        )

        if eos_time:
            turn_log.latency.end_of_speech_to_transcript_ms = round(
                (turn_start - eos_time) * 1000, 2
            )

        if check_injection(user_utterance):
            turn_log.policy_flags.append("prompt_injection_detected")
            turn_log.escalation_reason = "policy_trigger"
            workflow_state_machine.transition(session, "ESCALATE")
            tool_executor.escalate_to_human(
                session,
                EscalateToHumanInput(
                    reason_code="policy_trigger",
                    summary="Security policy violation: prompt injection attempt.",
                ),
            )
            conversation_history.append({
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": str(uuid.uuid4()),
                        "name": "escalate_to_human",
                        "input": {"reason_code": "policy_trigger", "summary": "Prompt injection blocked"},
                    }
                ],
            })
            msg = "I am unable to process that instruction. For your safety, I am connecting you to a supervisor."
            turn_log.text_spoken = msg
            turn_log.state_after = session.state
            turn_log.latency.total_turn_ms = round(
                (time.monotonic() - turn_start) * 1000, 2
            )
            turn_log.emit()
            replay_store.append(session.call_id, {"turn_log": turn_log.__dict__})
            yield msg
            return

        cleaned_input = user_utterance.lower()
        if any(kw in cleaned_input for kw in ESCALATION_KEYWORDS):
            turn_log.policy_flags.append("escalation_keyword_detected")
            workflow_state_machine.transition(session, "ESCALATE")
            tool_executor.escalate_to_human(
                session,
                EscalateToHumanInput(
                    reason_code="explicit_request",
                    summary=f"Caller requested human transfer: '{user_utterance}'",
                ),
            )
            conversation_history.append({
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": str(uuid.uuid4()),
                        "name": "escalate_to_human",
                        "input": {"reason_code": "explicit_request", "summary": user_utterance},
                    }
                ],
            })
            msg = "I understand. I am transferring your call to a representative right now. Please hold on."
            turn_log.text_spoken = msg
            turn_log.state_after = session.state
            turn_log.latency.total_turn_ms = round(
                (time.monotonic() - turn_start) * 1000, 2
            )
            turn_log.emit()
            replay_store.append(session.call_id, {"turn_log": turn_log.__dict__})
            yield msg
            return

        if session.state == "GREETING":
            if any(term in cleaned_input for term in ("c-", "balance", "loan", "promise", "due date", "complaint", "help", "check")):
                workflow_state_machine.transition(session, "IDENTIFY")
                workflow_state_machine.transition(session, "VERIFY")
        elif session.state == "IDENTIFY":
            workflow_state_machine.transition(session, "VERIFY")
        elif session.state == "INTENT" and session.verified:
            workflow_state_machine.transition(session, "SERVICE")
        elif session.state in ("SERVICE", "CONFIRM"):
            if any(term in cleaned_input for term in ("bye", "goodbye", "thank", "all i needed", "that is all")):
                workflow_state_machine.transition(session, "WRAP_UP")

        conversation_history.append({"role": "user", "content": user_utterance})

        max_loops = 3
        loop_count = 0
        full_generated_text = ""
        first_token_time = None

        while loop_count < max_loops:
            loop_count += 1
            system_prompt = build_system_prompt(session)
            tools = get_tools_for_state(session.state)

            current_tool_name = None
            current_tool_id = None
            current_tool_input_json = ""
            current_assistant_text = ""

            async for event in llm_adapter.stream_turn(
                messages=conversation_history,
                system=system_prompt,
                tools=tools,
                session_id=session.session_id,
            ):
                if event.type == "text_delta":
                    if first_token_time is None:
                        first_token_time = time.monotonic()
                        turn_log.latency.transcript_to_llm_first_token_ms = round(
                            (first_token_time - turn_start) * 1000, 2
                        )
                    current_assistant_text += event.content
                    full_generated_text += event.content
                    yield event.content

                elif event.type == "tool_start":
                    current_tool_name = event.tool_name
                    current_tool_id = event.tool_use_id
                    current_tool_input_json = ""

                elif event.type == "tool_json_delta":
                    current_tool_input_json += event.content

                elif event.type == "done":
                    turn_log.input_tokens += event.input_tokens
                    turn_log.output_tokens += event.output_tokens

            if current_tool_name and current_tool_id:
                try:
                    tool_args = json.loads(current_tool_input_json) if current_tool_input_json else {}
                except json.JSONDecodeError:
                    tool_args = {}

                tool_result_msg, tool_meta = await self.execute_tool(
                    session, current_tool_name, tool_args
                )
                turn_log.add_tool_call(
                    current_tool_name,
                    tool_args,
                    tool_meta.get("status", "unknown"),
                    tool_meta.get("duration_ms", 0.0),
                )

                conversation_history.append({
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": current_tool_id,
                            "name": current_tool_name,
                            "input": tool_args,
                        }
                    ],
                })
                conversation_history.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": current_tool_id,
                            "content": tool_result_msg,
                        }
                    ],
                })
                if session.is_escalated:
                    conversation_history.append({
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": str(uuid.uuid4()),
                                "name": "escalate_to_human",
                                "input": {"reason_code": "policy_trigger"},
                            }
                        ],
                    })
                continue

            break

        if full_generated_text:
            conversation_history.append({
                "role": "assistant",
                "content": full_generated_text,
            })

        turn_log.text_spoken = full_generated_text
        turn_log.state_after = session.state
        turn_log.tts_characters = len(full_generated_text)
        turn_log.latency.total_turn_ms = round((time.monotonic() - turn_start) * 1000, 2)
        turn_log.emit()
        replay_store.append(session.call_id, {"turn_log": turn_log.__dict__})


agent_orchestrator = AgentOrchestrator()
