from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent.orchestrator import agent_orchestrator
from app.observability.logger import replay_store
from app.tools.executor import SessionState


def render_timeline(call_id: str):
    records = replay_store.load(call_id)
    if not records:
        print(f"No records found for Call ID: {call_id}")
        return

    print("=" * 80)
    print(f"CALL REPLAY TIMELINE: {call_id}")
    print("=" * 80)

    for idx, item in enumerate(records, 1):
        turn = item.get("turn_log", item)
        print(f"\n--- Turn #{idx} [{turn.get('turn_id', '')[:8]}] ---")
        print(f"Timestamp: {turn.get('timestamp')}")
        print(f"Workflow State: {turn.get('state_before')} -> {turn.get('state_after')}")
        print(f"Caller Utterance: \"{turn.get('final_transcript', '')}\"")

        tools = turn.get("tools_called", [])
        if tools:
            for t in tools:
                print(f"  [Tool Executed]: {t.get('tool')} ({t.get('result_status')}) in {t.get('duration_ms')}ms")

        print(f"Agent Spoken: \"{turn.get('text_spoken', '')}\"")

        latency = turn.get("latency", {})
        total_ms = latency.get("total_turn_ms")
        ttft_ms = latency.get("transcript_to_llm_first_token_ms")
        print(f"Latency: Total={total_ms}ms | TTFT={ttft_ms}ms | Cost=${turn.get('estimated_cost_usd', 0.0):.6f}")

    print("\n" + "=" * 80)


async def reexecute_call(call_id: str):
    records = replay_store.load(call_id)
    if not records:
        print(f"No records found for Call ID: {call_id}")
        return

    print(f"\nRe-executing call {call_id} through live AgentOrchestrator...")

    session = SessionState(
        session_id=f"replay-{call_id}",
        call_id=f"REPLAY-{call_id}",
        state="GREETING",
    )
    history = []

    for idx, item in enumerate(records, 1):
        turn = item.get("turn_log", item)
        caller_text = turn.get("final_transcript", "")
        if not caller_text:
            continue

        print(f"\n[Turn {idx}] Caller: {caller_text}")
        chunks = []
        async for chunk in agent_orchestrator.process_turn(
            session=session,
            user_utterance=caller_text,
            conversation_history=history,
        ):
            chunks.append(chunk)

        print(f"[Turn {idx}] New Agent Output: {''.join(chunks)}")
        print(f"[Turn {idx}] Original Output:  {turn.get('text_spoken', '')}")


def main():
    parser = argparse.ArgumentParser(description="Voice Loan Agent Call Replay & Debug Utility")
    parser.add_argument("call_id", nargs="?", help="Call ID to inspect or re-execute")
    parser.add_argument("--list", action="store_true", help="List available recorded calls")
    parser.add_argument("--reexecute", action="store_true", help="Re-execute recorded caller utterances")

    args = parser.parse_args()

    if args.list:
        calls = replay_store.list_calls()
        print(f"Recorded calls ({len(calls)}):")
        for c in calls:
            print(f" - {c}")
        return

    if not args.call_id:
        calls = replay_store.list_calls()
        if calls:
            args.call_id = calls[0]
            print(f"No Call ID specified. Using latest: {args.call_id}")
        else:
            print("No recorded calls available in replay store.")
            return

    if args.reexecute:
        asyncio.run(reexecute_call(args.call_id))
    else:
        render_timeline(args.call_id)


if __name__ == "__main__":
    main()
