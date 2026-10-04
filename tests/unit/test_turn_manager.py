from app.agent.turn_manager import turn_manager


def test_barge_in_detection():
    decision = turn_manager.evaluate_transcript(
        text="wait please stop I have a question",
        is_final=False,
        confidence=0.9,
        agent_speaking=True,
    )
    assert decision.is_barge_in is True


def test_backchannel_ignored_during_speaking():
    decision = turn_manager.evaluate_transcript(
        text="yeah",
        is_final=False,
        confidence=0.9,
        agent_speaking=True,
    )
    assert decision.is_barge_in is False
    assert "Backchannel" in decision.reason


def test_number_silence_timeout_extended():
    decision = turn_manager.evaluate_transcript(
        text="my loan number is 4",
        is_final=False,
        confidence=0.8,
        agent_speaking=False,
        awaiting_digits=True,
    )
    assert decision.should_extend_timeout is True
    timeout = turn_manager.get_silence_timeout(awaiting_digits=True)
    assert timeout >= 2.0
