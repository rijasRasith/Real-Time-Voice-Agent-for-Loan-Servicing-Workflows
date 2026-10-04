import pytest
from app.data.models import Base, LoanStatus, seed_database
from app.data.repository import customer_repo, get_engine, loan_repo, promise_repo


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    seed_database(engine)


def test_customer_verification_success():
    customer = customer_repo.find_by_id("C-0001")
    assert customer is not None
    ok, reason = customer_repo.verify_identity(
        "C-0001", customer.last_four_account, customer.security_pin
    )
    assert ok is True
    assert reason == "verified"


def test_customer_verification_mismatch():
    ok, reason = customer_repo.verify_identity("C-0001", "0000", "000000")
    assert ok is False
    assert reason == "mismatch"


def test_do_not_call_customer_flag():
    customer = customer_repo.find_by_id("C-0005")
    assert customer is not None
    assert customer.do_not_call is True
    ok, reason = customer_repo.verify_identity(
        "C-0005", customer.last_four_account, customer.security_pin
    )
    assert ok is False
    assert reason == "do_not_call"


def test_overdue_and_closed_loans():
    loans = loan_repo.get_by_customer("C-0009")
    assert len(loans) > 0
    assert any(l.days_past_due > 90 for l in loans)

    closed_loans = loan_repo.get_by_customer("C-0016")
    assert len(closed_loans) > 0
    assert any(l.status == LoanStatus.CLOSED for l in closed_loans)
