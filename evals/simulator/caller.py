from __future__ import annotations

import asyncio
from typing import List, Tuple
from app.agent.orchestrator import agent_orchestrator
from app.tools.executor import SessionState


class ScenarioSimulator:
    async def run_scenario(
        self, scenario: dict
    ) -> Tuple[SessionState, List[str], List[dict]]:
        session_id = f"eval-{scenario['id']}"
        call_id = f"CALL-{scenario['id']}"

        session = SessionState(
            session_id=session_id,
            call_id=call_id,
            state="GREETING",
        )

        history: List[dict] = []
        agent_responses: List[str] = []

        for turn_text in scenario["script"]:
            response_chunks = []
            async for chunk in agent_orchestrator.process_turn(
                session=session,
                user_utterance=turn_text,
                conversation_history=history,
            ):
                response_chunks.append(chunk)

            full_agent_reply = "".join(response_chunks)
            agent_responses.append(full_agent_reply)

            if session.is_escalated or session.state == "CLOSED":
                break

        return session, agent_responses, history
