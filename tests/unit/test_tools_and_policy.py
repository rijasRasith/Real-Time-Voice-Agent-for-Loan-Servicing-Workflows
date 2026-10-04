import uuid
import pytest
from app.data.models import Base, seed_database
from app.data.repository import get_engine, loan_repo
from app.tools.executor import (
    GetLoanSummaryInput,
    RecordPaymentPromiseInput,
    RequestDueDateChangeInput,
    SessionState,
    VerifyIdentityInput,
    tool_executor,
)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    seed_database(engine)


def test_tool_rejection_prior_to_verification():
    unverified_session = SessionState(
        session_id="test-session",
        call_id="test-call",
        verified=False,
    )
    result = tool_executor.get_loan_summary(
        unverified_session, GetLoanSummaryInput()
    )
    assert result.status == "not_allowed"
    assert "verification is required" in result.message.lower()


def test_promise_to_pay_idempotency():
    session = SessionState(
        session_id="test-session",
        call_id="test-call",
        customer_id="C-0001",
        verified=True,
    )
    loans = loan_repo.get_active_loans("C-0001")
    assert len(loans) > 0
    loan_id = loans[0].id

    idempotency_key = str(uuid.uuid4())
    promise_input = RecordPaymentPromiseInput(
        loan_id=loan_id,
        promised_amount=5000.0,
        promised_date="2026-10-20",
        idempotency_key=idempotency_key,
    )

    res1 = tool_executor.record_payment_promise(session, promise_input)
    assert res1.status == "success"
    assert res1.data["created"] is True

    res2 = tool_executor.record_payment_promise(session, promise_input)
    assert res2.status == "success"
    assert res2.data["created"] is False
    assert res2.data["promise_id"] == res1.data["promise_id"]


def test_due_date_change_range_policy():
    session = SessionState(
        session_id="test-session",
        call_id="test-call",
        customer_id="C-0001",
        verified=True,
    )
    loans = loan_repo.get_active_loans("C-0001")
    loan = loans[0]
    current_day = loan.emi_due_date or 5

    invalid_day = (current_day + 15) % 28 or 1
    req = RequestDueDateChangeInput(loan_id=loan.id, requested_day=invalid_day)
    res = tool_executor.request_due_date_change(session, req)
    assert res.status == "invalid_input"
    assert "can only be changed by up to" in res.message
