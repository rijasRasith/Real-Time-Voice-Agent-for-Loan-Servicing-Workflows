from app.agent.state_machine import workflow_state_machine
from app.tools.executor import SessionState


def test_valid_state_transitions():
    session = SessionState(session_id="s1", call_id="c1", state="GREETING")

    res = workflow_state_machine.transition(session, "IDENTIFY")
    assert res.allowed is True
    assert session.state == "IDENTIFY"

    res = workflow_state_machine.transition(session, "VERIFY")
    assert res.allowed is True
    assert session.state == "VERIFY"

    session.verified = True
    res = workflow_state_machine.transition(session, "INTENT")
    assert res.allowed is True
    assert session.state == "INTENT"


def test_unverified_transition_blocked():
    session = SessionState(session_id="s2", call_id="c2", state="VERIFY", verified=False)
    res = workflow_state_machine.transition(session, "SERVICE")
    assert res.allowed is False
    assert "requires identity verification" in res.reason
    assert session.state == "VERIFY"


def test_escalation_always_allowed():
    for state in ["GREETING", "IDENTIFY", "VERIFY", "INTENT", "SERVICE", "CONFIRM", "WRAP_UP"]:
        session = SessionState(session_id="s3", call_id="c3", state=state)
        res = workflow_state_machine.transition(session, "ESCALATE")
        assert res.allowed is True
        assert session.state == "ESCALATE"
