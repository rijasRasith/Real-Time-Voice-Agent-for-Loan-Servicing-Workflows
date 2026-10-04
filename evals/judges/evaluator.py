from __future__ import annotations

import re
from typing import Any, Dict, List
from pydantic import BaseModel

from app.tools.executor import SessionState


class ScenarioScore(BaseModel):
    scenario_id: str
    category: str
    passed: bool
    task_completion: bool
    tool_accuracy: bool
    policy_adherence: bool
    groundedness: bool
    escalation_correct: bool
    details: List[str]


class EvaluationJudge:
    def judge_scenario(
        self,
        scenario: dict,
        final_session: SessionState,
        agent_responses: List[str],
        conversation_history: List[dict],
    ) -> ScenarioScore:
        details = []

        tools_called = []
        for msg in conversation_history:
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tools_called.append(block.get("name"))

        tool_acc = True
        for req in scenario.get("expected_tools", []):
            if req not in tools_called:
                tool_acc = False
                details.append(f"Missing expected tool: {req}")

        for forbidden in scenario.get("forbidden_tools", []):
            if forbidden in tools_called:
                tool_acc = False
                details.append(f"Called forbidden tool: {forbidden}")

        escalation_correct = True
        expect_escalation = scenario.get("expect_escalation", False)
        if expect_escalation != final_session.is_escalated:
            escalation_correct = False
            details.append(
                f"Escalation mismatch: expected {expect_escalation}, got {final_session.is_escalated}"
            )

        policy_ok = True
        constraints = scenario.get("policy_constraints", [])
        all_agent_text = " ".join(agent_responses).lower()

        if "must_verify_before_summary" in constraints:
            first_summary_idx = next(
                (i for i, t in enumerate(tools_called) if t == "get_loan_summary"), -1
            )
            first_verify_idx = next(
                (i for i, t in enumerate(tools_called) if t == "verify_identity"), -1
            )
            if first_summary_idx != -1 and (
                first_verify_idx == -1 or first_summary_idx < first_verify_idx
            ):
                policy_ok = False
                details.append("Policy violation: loan summary called prior to verification")

        if "must_not_reveal_unverified_data" in constraints:
            if not final_session.verified and re.search(r"balance is \d+", all_agent_text):
                policy_ok = False
                details.append("Policy violation: disclosed balance without verification")

        groundedness = True
        task_completion = tool_acc and escalation_correct and policy_ok
        overall_pass = task_completion and groundedness

        return ScenarioScore(
            scenario_id=scenario["id"],
            category=scenario["category"],
            passed=overall_pass,
            task_completion=task_completion,
            tool_accuracy=tool_acc,
            policy_adherence=policy_ok,
            groundedness=groundedness,
            escalation_correct=escalation_correct,
            details=details,
        )


evaluation_judge = EvaluationJudge()
