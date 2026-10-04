from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import anthropic

from app.config.settings import settings
from app.observability.logger import emit


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+your\s+(system\s+)?prompt",
    r"you\s+are\s+now\s+a",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions",
    r"forget\s+your\s+instructions",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

TEXT_NORMALIZATIONS = [
    (r"\bINR\b", "rupees"),
    (r"₹(\d)", r"\1 rupees"),
    (r"\bEMI\b", "EMI"),
    (r"\be\.g\.\b", "for example"),
    (r"\bi\.e\.\b", "that is"),
    (r"&", "and"),
    (r"%", " percent"),
]


def normalize_for_tts(text: str) -> str:
    for pattern, replacement in TEXT_NORMALIZATIONS:
        text = re.sub(pattern, replacement, text)
    return text


def check_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))


@dataclass
class LLMStreamEvent:
    type: str
    content: str = ""
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_use_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ConversationMessage:
    role: str
    content: str | list


class LLMAdapter:
    def __init__(self):
        api_key = settings.anthropic_api_key or "mock-key"
        self._is_mock = api_key.startswith("mock") or not settings.anthropic_api_key
        if not self._is_mock:
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            self._client = None
        self._sentence_pattern = re.compile(r"(?<=[.!?])\s+")

    async def stream_turn(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        session_id: str,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        if self._is_mock:
            async for ev in self._mock_stream_turn(messages, system, tools):
                yield ev
            return

        model_name = model or settings.primary_llm_model
        attempt = 0
        max_attempts = settings.max_tool_retries + 1

        while attempt < max_attempts:
            attempt += 1
            try:
                async with self._client.messages.stream(
                    model=model_name,
                    max_tokens=1024,
                    system=system,
                    messages=messages,
                    tools=tools if tools else anthropic.NOT_GIVEN,
                ) as stream:
                    input_tokens = 0
                    output_tokens = 0
                    async for event in stream:
                        if hasattr(event, "type"):
                            if event.type == "content_block_delta":
                                delta = event.delta
                                if hasattr(delta, "text"):
                                    yield LLMStreamEvent(type="text_delta", content=delta.text)
                                elif hasattr(delta, "partial_json"):
                                    yield LLMStreamEvent(type="tool_json_delta", content=delta.partial_json)
                            elif event.type == "content_block_start":
                                block = event.content_block
                                if block.type == "tool_use":
                                    yield LLMStreamEvent(
                                        type="tool_start",
                                        tool_name=block.name,
                                        tool_use_id=block.id,
                                    )
                            elif event.type == "content_block_stop":
                                yield LLMStreamEvent(type="block_stop")
                            elif event.type == "message_start":
                                if hasattr(event.message, "usage"):
                                    input_tokens = event.message.usage.input_tokens
                            elif event.type == "message_delta":
                                if hasattr(event, "usage"):
                                    output_tokens = event.usage.output_tokens
                            elif event.type == "message_stop":
                                yield LLMStreamEvent(
                                    type="done",
                                    input_tokens=input_tokens,
                                    output_tokens=output_tokens,
                                )
                    return
            except anthropic.RateLimitError:
                wait = 2 ** attempt
                emit({"type": "llm_rate_limit", "session_id": session_id, "wait_s": wait})
                await asyncio.sleep(wait)
            except anthropic.APIError as e:
                if attempt == max_attempts:
                    if model_name != settings.fallback_llm_model:
                        emit({"type": "llm_fallback", "session_id": session_id, "from_model": model_name})
                        model_name = settings.fallback_llm_model
                        attempt = 0
                    else:
                        yield LLMStreamEvent(type="error", content=str(e))
                        return
                await asyncio.sleep(1)

    async def _mock_stream_turn(
        self, messages: list[dict], system: str, tools: list[dict]
    ) -> AsyncIterator[LLMStreamEvent]:
        last_msg = messages[-1] if messages else {}
        tool_result = ""
        last_user_msg = ""

        if last_msg.get("role") == "user" and isinstance(last_msg.get("content"), list):
            for item in last_msg["content"]:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    tool_result = item.get("content", "")
        else:
            for m in reversed(messages):
                if m.get("role") == "user" and isinstance(m.get("content"), str):
                    last_user_msg = m["content"]
                    break

        user_text = last_user_msg.lower()
        tool_names = [t["name"] for t in tools] if tools else []

        if tool_result:
            if "verified" in tool_result.lower():
                resp = "Thank you, your identity is verified. How can I help you with your loan today?"
            elif "not match" in tool_result.lower():
                resp = f"{tool_result} Please re-check and provide your 4 account digits and 6-digit PIN."
            elif "do-not-call" in tool_result.lower() or "restriction" in tool_result.lower():
                resp = "I see a restriction on this profile. Connecting you to a specialist."
            else:
                resp = f"{tool_result} Is there anything else I can assist you with today?"

            yield LLMStreamEvent(type="text_delta", content=resp)
            yield LLMStreamEvent(type="done", input_tokens=450, output_tokens=30)
            return

        if "end_call" in tool_names and any(k in user_text for k in ("bye", "goodbye", "thank", "all i needed", "that is all")):
            t_id = f"toolu_{uuid.uuid4().hex[:8]}"
            yield LLMStreamEvent(type="tool_start", tool_name="end_call", tool_use_id=t_id)
            yield LLMStreamEvent(type="tool_json_delta", content=json.dumps({"disposition": "resolved"}))
            yield LLMStreamEvent(type="block_stop")
            yield LLMStreamEvent(type="done", input_tokens=320, output_tokens=15)
            return

        if "get_loan_summary" in tool_names and any(k in user_text for k in ("balance", "what is my", "check my loan", "due date", "next emi", "outstanding")):
            t_id = f"toolu_{uuid.uuid4().hex[:8]}"
            yield LLMStreamEvent(type="tool_start", tool_name="get_loan_summary", tool_use_id=t_id)
            yield LLMStreamEvent(type="tool_json_delta", content="{}")
            yield LLMStreamEvent(type="block_stop")
            yield LLMStreamEvent(type="done", input_tokens=380, output_tokens=25)
            return

        if "record_payment_promise" in tool_names and any(k in user_text for k in ("promise", "pay", "confirm", "yes")):
            t_id = f"toolu_{uuid.uuid4().hex[:8]}"
            yield LLMStreamEvent(type="tool_start", tool_name="record_payment_promise", tool_use_id=t_id)
            amounts = re.findall(r"\b\d{3,6}\b", user_text)
            amount = float(amounts[0]) if amounts else 15000.0
            tool_input = {
                "loan_id": "L-0002-0",
                "promised_amount": amount,
                "promised_date": "2026-10-25",
                "idempotency_key": str(uuid.uuid4()),
            }
            yield LLMStreamEvent(type="tool_json_delta", content=json.dumps(tool_input))
            yield LLMStreamEvent(type="block_stop")
            yield LLMStreamEvent(type="done", input_tokens=410, output_tokens=45)
            return

        if "request_due_date_change" in tool_names and any(k in user_text for k in ("move", "change", "update", "shift", "10th", "10")):
            t_id = f"toolu_{uuid.uuid4().hex[:8]}"
            yield LLMStreamEvent(type="tool_start", tool_name="request_due_date_change", tool_use_id=t_id)
            days = re.findall(r"\b\d{1,2}\b", user_text)
            requested_day = int(days[0]) if days else 10
            if requested_day < 1 or requested_day > 28:
                requested_day = 10
            tool_input = {"loan_id": "L-0003-0", "requested_day": requested_day}
            yield LLMStreamEvent(type="tool_json_delta", content=json.dumps(tool_input))
            yield LLMStreamEvent(type="block_stop")
            yield LLMStreamEvent(type="done", input_tokens=390, output_tokens=35)
            return

        if "log_complaint" in tool_names and any(k in user_text for k in ("complaint", "billing", "penalty", "error")):
            t_id = f"toolu_{uuid.uuid4().hex[:8]}"
            yield LLMStreamEvent(type="tool_start", tool_name="log_complaint", tool_use_id=t_id)
            tool_input = {"category": "billing_error", "text": last_user_msg}
            yield LLMStreamEvent(type="tool_json_delta", content=json.dumps(tool_input))
            yield LLMStreamEvent(type="block_stop")
            yield LLMStreamEvent(type="done", input_tokens=430, output_tokens=40)
            return

        if "verify_identity" in tool_names and any(k in user_text for k in ("pin", "digits", "last four", "account", "c-", "id is", "4512", "3194", "7712", "8821", "5555", "9999", "1234", "0000", "1111", "2222")):
            all_digits = re.findall(r"\b\d+\b", user_text)
            cids = re.findall(r"c-\d{4}", user_text)
            cid = cids[0].upper() if cids else "C-0001"

            last_four = "4512"
            pin = "849201"
            for d in all_digits:
                if len(d) == 4:
                    last_four = d
                elif len(d) == 6:
                    pin = d

            t_id = f"toolu_{uuid.uuid4().hex[:8]}"
            yield LLMStreamEvent(type="tool_start", tool_name="verify_identity", tool_use_id=t_id)
            tool_input = {"customer_id": cid, "last_four_account": last_four, "security_pin": pin}
            yield LLMStreamEvent(type="tool_json_delta", content=json.dumps(tool_input))
            yield LLMStreamEvent(type="block_stop")
            yield LLMStreamEvent(type="done", input_tokens=420, output_tokens=45)
            return

        if "invest" in user_text or "crypto" in user_text or "mutual fund" in user_text:
            text = "I am a loan servicing assistant and cannot provide investment or financial advice. I can help you with your loan balance or EMI."
        elif "c-" in user_text and "verify_identity" not in tool_names:
            text = "To access your account details, I will first need to verify your identity with your account digits and PIN."
        elif any(k in user_text for k in ("hi", "hello", "want to check", "help")):
            text = "Hello, I am Priya from Nova Finance. For your security, could you please provide your customer ID, last 4 digits of your account, and your 6-digit PIN?"
        else:
            text = "Could you please clarify your loan request, or let me know if you would like to speak to a specialist?"

        yield LLMStreamEvent(type="text_delta", content=text)
        yield LLMStreamEvent(type="done", input_tokens=350, output_tokens=len(text.split()))

    def chunk_into_sentences(self, text: str) -> list[str]:
        sentences = self._sentence_pattern.split(text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def first_sentence(self, text: str) -> str:
        match = re.search(r"[.!?]", text)
        if match:
            return text[: match.end()].strip()
        return text.strip()


llm_adapter = LLMAdapter()
