from __future__ import annotations

from typing import Optional, Set
from pydantic import BaseModel

from app.config.settings import settings
from app.tools.executor import SessionState


VALID_STATES: Set[str] = {
    "GREETING",
    "IDENTIFY",
    "VERIFY",
    "INTENT",
    "SERVICE",
    "CONFIRM",
    "WRAP_UP",
    "ESCALATE",
    "CLOSED",
}

TRANSITIONS: dict[str, Set[str]] = {
    "GREETING": {"IDENTIFY", "VERIFY", "ESCALATE", "CLOSED"},
    "IDENTIFY": {"VERIFY", "ESCALATE", "CLOSED"},
    "VERIFY": {"INTENT", "SERVICE", "ESCALATE", "CLOSED"},
    "INTENT": {"SERVICE", "WRAP_UP", "ESCALATE", "CLOSED"},
    "SERVICE": {"CONFIRM", "WRAP_UP", "SERVICE", "ESCALATE", "CLOSED"},
    "CONFIRM": {"SERVICE", "WRAP_UP", "ESCALATE", "CLOSED"},
    "WRAP_UP": {"INTENT", "SERVICE", "CLOSED", "ESCALATE"},
    "ESCALATE": {"CLOSED"},
    "CLOSED": set(),
}


class TransitionResult(BaseModel):
    allowed: bool
    from_state: str
    to_state: str
    reason: str


class WorkflowStateMachine:
    def can_transition(
        self, session: SessionState, target_state: str
    ) -> TransitionResult:
        current = session.state

        if target_state not in VALID_STATES:
            return TransitionResult(
                allowed=False,
                from_state=current,
                to_state=target_state,
                reason=f"Invalid target state: {target_state}",
            )

        if target_state == "ESCALATE":
            return TransitionResult(
                allowed=True,
                from_state=current,
                to_state=target_state,
                reason="Escalation is universally accessible",
            )

        if target_state not in TRANSITIONS.get(current, set()):
            return TransitionResult(
                allowed=False,
                from_state=current,
                to_state=target_state,
                reason=f"Illegal state transition from {current} to {target_state}",
            )

        if target_state in {"INTENT", "SERVICE", "CONFIRM"}:
            if not session.verified:
                return TransitionResult(
                    allowed=False,
                    from_state=current,
                    to_state=target_state,
                    reason="State requires identity verification",
                )

        if target_state == "VERIFY":
            if session.verification_attempts >= settings.max_verification_attempts:
                return TransitionResult(
                    allowed=False,
                    from_state=current,
                    to_state=target_state,
                    reason="Verification attempt limit exceeded",
                )

        return TransitionResult(
            allowed=True,
            from_state=current,
            to_state=target_state,
            reason="Transition allowed",
        )

    def transition(self, session: SessionState, target_state: str) -> TransitionResult:
        result = self.can_transition(session, target_state)
        if result.allowed:
            session.state = target_state
        return result


workflow_state_machine = WorkflowStateMachine()
