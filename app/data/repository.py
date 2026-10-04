from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.data.models import (
    Base,
    CallDisposition,
    CallRecord,
    Complaint,
    ComplaintStatus,
    Customer,
    EscalationPriority,
    EscalationQueue,
    EscalationStatus,
    Loan,
    LoanStatus,
    Payment,
    PromiseToPay,
    PromiseStatus,
    seed_database,
)

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(_engine)
        seed_database(_engine)
    return _engine


def get_session() -> Session:
    return Session(get_engine())


class CustomerRepository:
    def find_by_id(self, customer_id: str) -> Optional[Customer]:
        with get_session() as s:
            return s.query(Customer).filter(Customer.id == customer_id).first()

    def find_by_name(self, full_name: str) -> list[Customer]:
        with get_session() as s:
            return (
                s.query(Customer)
                .filter(Customer.full_name.ilike(f"%{full_name}%"))
                .all()
            )

    def find_by_phone(self, phone: str) -> Optional[Customer]:
        with get_session() as s:
            return s.query(Customer).filter(Customer.phone == phone).first()

    def verify_identity(
        self, customer_id: str, last_four: str, pin: str
    ) -> tuple[bool, str]:
        with get_session() as s:
            c = s.query(Customer).filter(Customer.id == customer_id).first()
            if not c:
                return False, "customer_not_found"
            if c.do_not_call:
                return False, "do_not_call"
            if c.last_four_account == last_four and c.security_pin == pin:
                return True, "verified"
            return False, "mismatch"


class LoanRepository:
    def get_by_customer(self, customer_id: str) -> list[Loan]:
        with get_session() as s:
            return s.query(Loan).filter(Loan.customer_id == customer_id).all()

    def get_by_id(self, loan_id: str) -> Optional[Loan]:
        with get_session() as s:
            return s.query(Loan).filter(Loan.id == loan_id).first()

    def get_active_loans(self, customer_id: str) -> list[Loan]:
        with get_session() as s:
            return (
                s.query(Loan)
                .filter(
                    Loan.customer_id == customer_id,
                    Loan.status != LoanStatus.CLOSED,
                )
                .all()
            )

    def get_payments(self, loan_id: str, limit: int = 10) -> list[Payment]:
        with get_session() as s:
            return (
                s.query(Payment)
                .filter(Payment.loan_id == loan_id)
                .order_by(Payment.payment_date.desc())
                .limit(limit)
                .all()
            )


class PromiseRepository:
    def create(
        self,
        loan_id: str,
        promised_amount: float,
        promised_date: date,
        channel: str,
        idempotency_key: str,
    ) -> tuple[PromiseToPay, bool]:
        with get_session() as s:
            existing = (
                s.query(PromiseToPay)
                .filter(PromiseToPay.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return existing, False
            p = PromiseToPay(
                id=str(uuid.uuid4()),
                loan_id=loan_id,
                promised_amount=promised_amount,
                promised_date=promised_date,
                channel=channel,
                idempotency_key=idempotency_key,
            )
            s.add(p)
            s.commit()
            s.refresh(p)
            return p, True

    def get_pending(self, loan_id: str) -> list[PromiseToPay]:
        with get_session() as s:
            return (
                s.query(PromiseToPay)
                .filter(
                    PromiseToPay.loan_id == loan_id,
                    PromiseToPay.status == PromiseStatus.PENDING,
                )
                .all()
            )


class CallRecordRepository:
    def create(self, call_id: str, customer_id: Optional[str] = None) -> CallRecord:
        with get_session() as s:
            cr = CallRecord(
                id=call_id,
                customer_id=customer_id,
                started_at=datetime.utcnow(),
                disposition=CallDisposition.IN_PROGRESS,
            )
            s.add(cr)
            s.commit()
            s.refresh(cr)
            return cr

    def close(
        self,
        call_id: str,
        disposition: CallDisposition,
        summary: Optional[str] = None,
        escalation_flag: bool = False,
    ):
        with get_session() as s:
            cr = s.query(CallRecord).filter(CallRecord.id == call_id).first()
            if cr:
                cr.ended_at = datetime.utcnow()
                cr.disposition = disposition
                cr.escalation_flag = escalation_flag
                cr.summary = summary
                s.commit()

    def update_customer(self, call_id: str, customer_id: str):
        with get_session() as s:
            cr = s.query(CallRecord).filter(CallRecord.id == call_id).first()
            if cr:
                cr.customer_id = customer_id
                s.commit()


class ComplaintRepository:
    def create(
        self,
        customer_id: str,
        category: str,
        text: str,
    ) -> Complaint:
        with get_session() as s:
            c = Complaint(
                id=str(uuid.uuid4()),
                customer_id=customer_id,
                category=category,
                text=text,
                status=ComplaintStatus.OPEN,
            )
            s.add(c)
            s.commit()
            s.refresh(c)
            return c


class EscalationRepository:
    def enqueue(
        self,
        call_id: str,
        reason_code: str,
        priority: EscalationPriority,
        packaged_context: str,
    ) -> EscalationQueue:
        with get_session() as s:
            eq = EscalationQueue(
                id=str(uuid.uuid4()),
                call_id=call_id,
                reason_code=reason_code,
                priority=priority,
                packaged_context=packaged_context,
                status=EscalationStatus.QUEUED,
            )
            s.add(eq)
            s.commit()
            s.refresh(eq)
            return eq

    def list_queued(self) -> list[EscalationQueue]:
        with get_session() as s:
            return (
                s.query(EscalationQueue)
                .filter(EscalationQueue.status == EscalationStatus.QUEUED)
                .order_by(EscalationQueue.created_at.asc())
                .all()
            )


customer_repo = CustomerRepository()
loan_repo = LoanRepository()
promise_repo = PromiseRepository()
call_record_repo = CallRecordRepository()
complaint_repo = ComplaintRepository()
escalation_repo = EscalationRepository()
