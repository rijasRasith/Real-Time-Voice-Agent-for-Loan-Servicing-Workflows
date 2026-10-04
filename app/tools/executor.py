from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.config.settings import settings
from app.data.repository import (
    call_record_repo,
    complaint_repo,
    customer_repo,
    escalation_repo,
    loan_repo,
    promise_repo,
)
from app.data.models import (
    CallDisposition,
    EscalationPriority,
    LoanStatus,
)
from app.observability.logger import emit


ToolStatus = Literal["success", "not_found", "not_allowed", "invalid_input", "error"]


class ToolResult(BaseModel):
    status: ToolStatus
    message: str
    data: Optional[dict] = None


class SessionState(BaseModel):
    session_id: str
    call_id: str
    customer_id: Optional[str] = None
    verified: bool = False
    verification_attempts: int = 0
    current_intent: Optional[str] = None
    current_loan_id: Optional[str] = None
    state: str = "GREETING"
    is_escalated: bool = False
    turn_count: int = 0


class VerifyIdentityInput(BaseModel):
    customer_id: str = Field(..., min_length=1)
    last_four_account: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    security_pin: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class GetLoanSummaryInput(BaseModel):
    loan_id: Optional[str] = None


class GetPaymentHistoryInput(BaseModel):
    loan_id: str
    limit: int = Field(default=5, ge=1, le=20)


class RecordPaymentPromiseInput(BaseModel):
    loan_id: str
    promised_amount: float = Field(..., gt=0)
    promised_date: str = Field(..., description="ISO date YYYY-MM-DD")
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @field_validator("promised_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v


class RequestDueDateChangeInput(BaseModel):
    loan_id: str
    requested_day: int = Field(..., ge=1, le=28)


class LogComplaintInput(BaseModel):
    category: str = Field(..., min_length=2, max_length=100)
    text: str = Field(..., min_length=5, max_length=2000)


class EscalateToHumanInput(BaseModel):
    reason_code: str
    summary: str = ""


class EndCallInput(BaseModel):
    disposition: str = Field(default="resolved")


def _audit(session: SessionState, tool_name: str, args: dict, result: ToolResult, duration_ms: float):
    emit({
        "type": "tool_audit",
        "session_id": session.session_id,
        "call_id": session.call_id,
        "tool": tool_name,
        "args_summary": {k: v for k, v in args.items() if k not in ("security_pin", "last_four_account")},
        "result_status": result.status,
        "timestamp": datetime.utcnow().isoformat(),
        "duration_ms": duration_ms,
    })


class PolicyGuard:
    def check_verified(self, session: SessionState) -> Optional[ToolResult]:
        if not session.verified:
            return ToolResult(
                status="not_allowed",
                message="Identity verification is required before accessing account information.",
            )
        return None

    def check_verification_attempts(self, session: SessionState) -> Optional[ToolResult]:
        if session.verification_attempts >= settings.max_verification_attempts:
            return ToolResult(
                status="not_allowed",
                message="Maximum verification attempts reached. Transferring to a specialist.",
            )
        return None

    def check_customer_set(self, session: SessionState) -> Optional[ToolResult]:
        if not session.customer_id:
            return ToolResult(
                status="not_allowed",
                message="Customer identity has not been established yet.",
            )
        return None


policy_guard = PolicyGuard()


class ToolExecutor:
    def verify_identity(
        self, session: SessionState, args: VerifyIdentityInput
    ) -> ToolResult:
        start = time.monotonic()
        guard = policy_guard.check_verification_attempts(session)
        if guard:
            return guard

        session.verification_attempts += 1
        ok, reason = customer_repo.verify_identity(
            args.customer_id, args.last_four_account, args.security_pin
        )

        if reason == "do_not_call":
            self.escalate_to_human(
                session,
                EscalateToHumanInput(
                    reason_code="policy_trigger",
                    summary="Customer profile has do-not-call restriction.",
                ),
            )
            result = ToolResult(
                status="not_allowed",
                message="This account has a do-not-call restriction. Connecting you to a specialist.",
            )
        elif ok:
            session.verified = True
            session.customer_id = args.customer_id
            call_record_repo.update_customer(session.call_id, args.customer_id)

            loans = loan_repo.get_active_loans(args.customer_id)
            if any(l.days_past_due > settings.overdue_escalation_days for l in loans):
                self.escalate_to_human(
                    session,
                    EscalateToHumanInput(
                        reason_code="policy_trigger",
                        summary="Account is 90+ days past due. Routing to collections specialist.",
                    ),
                )
                result = ToolResult(
                    status="not_allowed",
                    message="Your account has a special status. Connecting you to a specialist.",
                )
            else:
                result = ToolResult(
                    status="success",
                    message="Identity verified successfully.",
                    data={"customer_id": args.customer_id},
                )
        else:
            remaining = settings.max_verification_attempts - session.verification_attempts
            if remaining <= 0:
                self.escalate_to_human(
                    session,
                    EscalateToHumanInput(
                        reason_code="repeated_failure",
                        summary="Three failed identity verification attempts.",
                    ),
                )
            result = ToolResult(
                status="not_allowed",
                message=f"Verification details do not match. You have {max(0, remaining)} attempt(s) remaining.",
            )

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _audit(session, "verify_identity", {"customer_id": args.customer_id}, result, duration_ms)
        return result

    def get_loan_summary(
        self, session: SessionState, args: GetLoanSummaryInput
    ) -> ToolResult:
        start = time.monotonic()
        guard = policy_guard.check_verified(session)
        if guard:
            return guard

        loans = loan_repo.get_active_loans(session.customer_id)
        if not loans:
            result = ToolResult(status="not_found", message="No active loans found for this account.")
        else:
            if args.loan_id:
                target = next((l for l in loans if l.id == args.loan_id), None)
                if not target:
                    result = ToolResult(status="not_found", message="Loan not found.")
                    duration_ms = round((time.monotonic() - start) * 1000, 2)
                    _audit(session, "get_loan_summary", {"loan_id": args.loan_id}, result, duration_ms)
                    return result
                loans = [target]

            summaries = []
            for loan in loans:
                summaries.append({
                    "loan_id": loan.id,
                    "product": loan.product_type.value,
                    "outstanding_balance": round(loan.outstanding_balance, 2),
                    "emi_amount": round(loan.emi_amount, 2),
                    "emi_due_date": loan.emi_due_date,
                    "status": loan.status.value,
                    "days_past_due": loan.days_past_due,
                })
            result = ToolResult(
                status="success",
                message="Loan summary retrieved.",
                data={"loans": summaries},
            )

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _audit(session, "get_loan_summary", {"loan_id": args.loan_id}, result, duration_ms)
        return result

    def get_payment_history(
        self, session: SessionState, args: GetPaymentHistoryInput
    ) -> ToolResult:
        start = time.monotonic()
        guard = policy_guard.check_verified(session)
        if guard:
            return guard

        loan = loan_repo.get_by_id(args.loan_id)
        if not loan or loan.customer_id != session.customer_id:
            active_loans = loan_repo.get_active_loans(session.customer_id)
            if active_loans:
                loan = active_loans[0]
            else:
                result = ToolResult(status="not_found", message="Loan not found for this account.")
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                _audit(session, "get_payment_history", {"loan_id": args.loan_id}, result, duration_ms)
                return result

        payments = loan_repo.get_payments(loan.id, args.limit)
        history = [
            {
                "payment_id": p.id,
                "amount": round(p.amount, 2),
                "date": p.payment_date.isoformat(),
                "mode": p.mode,
                "status": p.status.value,
            }
            for p in payments
        ]
        result = ToolResult(
            status="success",
            message=f"Last {len(history)} payment(s) retrieved.",
            data={"payments": history},
        )
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _audit(session, "get_payment_history", {"loan_id": args.loan_id}, result, duration_ms)
        return result

    def record_payment_promise(
        self, session: SessionState, args: RecordPaymentPromiseInput
    ) -> ToolResult:
        start = time.monotonic()
        guard = policy_guard.check_verified(session)
        if guard:
            return guard

        loan = loan_repo.get_by_id(args.loan_id)
        if not loan or loan.customer_id != session.customer_id:
            active_loans = loan_repo.get_active_loans(session.customer_id)
            if active_loans:
                loan = active_loans[0]
            else:
                result = ToolResult(status="not_found", message="Loan not found for this account.")
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                _audit(session, "record_payment_promise", {"loan_id": args.loan_id}, result, duration_ms)
                return result

        if loan.status == LoanStatus.CLOSED:
            result = ToolResult(status="not_allowed", message="This loan is already closed.")
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _audit(session, "record_payment_promise", {"loan_id": args.loan_id}, result, duration_ms)
            return result

        if args.promised_amount < settings.promise_min_amount:
            result = ToolResult(
                status="invalid_input",
                message=f"Promise amount must be at least {settings.promise_min_amount:.0f} rupees.",
            )
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _audit(session, "record_payment_promise", {"loan_id": args.loan_id}, result, duration_ms)
            return result

        promised_date = date.fromisoformat(args.promised_date)
        max_date = date.today() + timedelta(days=settings.promise_max_days_ahead)
        if promised_date < date.today():
            result = ToolResult(status="invalid_input", message="The promise date cannot be in the past.")
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _audit(session, "record_payment_promise", {"loan_id": args.loan_id}, result, duration_ms)
            return result
        if promised_date > max_date:
            result = ToolResult(
                status="invalid_input",
                message=f"The promise date must be within the next {settings.promise_max_days_ahead} days.",
            )
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _audit(session, "record_payment_promise", {"loan_id": args.loan_id}, result, duration_ms)
            return result

        promise, created = promise_repo.create(
            loan_id=loan.id,
            promised_amount=args.promised_amount,
            promised_date=promised_date,
            channel="voice",
            idempotency_key=args.idempotency_key,
        )
        result = ToolResult(
            status="success",
            message="Payment promise recorded." if created else "Payment promise already recorded.",
            data={
                "promise_id": promise.id,
                "loan_id": loan.id,
                "amount": args.promised_amount,
                "date": args.promised_date,
                "created": created,
            },
        )
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _audit(session, "record_payment_promise", {"loan_id": loan.id, "amount": args.promised_amount, "date": args.promised_date}, result, duration_ms)
        return result

    def request_due_date_change(
        self, session: SessionState, args: RequestDueDateChangeInput
    ) -> ToolResult:
        start = time.monotonic()
        guard = policy_guard.check_verified(session)
        if guard:
            return guard

        loan = loan_repo.get_by_id(args.loan_id)
        if not loan or loan.customer_id != session.customer_id:
            active_loans = loan_repo.get_active_loans(session.customer_id)
            if active_loans:
                loan = active_loans[0]
            else:
                result = ToolResult(status="not_found", message="Loan not found for this account.")
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                _audit(session, "request_due_date_change", {"loan_id": args.loan_id}, result, duration_ms)
                return result

        if loan.status == LoanStatus.CLOSED:
            result = ToolResult(status="not_allowed", message="This loan is already closed.")
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _audit(session, "request_due_date_change", {"loan_id": args.loan_id}, result, duration_ms)
            return result

        current_day = loan.emi_due_date or 1
        day_diff = abs(args.requested_day - current_day)
        if day_diff > settings.due_date_change_max_days:
            result = ToolResult(
                status="invalid_input",
                message=f"Due date can only be changed by up to {settings.due_date_change_max_days} days. Your current due date is the {current_day}th.",
            )
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _audit(session, "request_due_date_change", {"loan_id": args.loan_id, "requested_day": args.requested_day}, result, duration_ms)
            return result

        result = ToolResult(
            status="success",
            message=f"Due date change request submitted. Your EMI due date will be updated to the {args.requested_day}th of each month. This change typically takes one billing cycle to take effect.",
            data={"loan_id": loan.id, "requested_day": args.requested_day, "current_day": current_day},
        )
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _audit(session, "request_due_date_change", {"loan_id": loan.id, "requested_day": args.requested_day}, result, duration_ms)
        return result

    def log_complaint(
        self, session: SessionState, args: LogComplaintInput
    ) -> ToolResult:
        start = time.monotonic()
        cid = session.customer_id or "C-0004"
        complaint = complaint_repo.create(
            customer_id=cid,
            category=args.category,
            text=args.text,
        )
        result = ToolResult(
            status="success",
            message=f"Your complaint has been registered with reference ID {complaint.id[:8].upper()}. Our team will follow up within 5 to 7 business days.",
            data={"complaint_id": complaint.id, "category": args.category},
        )
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _audit(session, "log_complaint", {"category": args.category}, result, duration_ms)
        return result

    def escalate_to_human(
        self, session: SessionState, args: EscalateToHumanInput
    ) -> ToolResult:
        start = time.monotonic()
        priority_map = {
            "explicit_request": EscalationPriority.MEDIUM,
            "low_confidence": EscalationPriority.MEDIUM,
            "policy_trigger": EscalationPriority.HIGH,
            "repeated_failure": EscalationPriority.MEDIUM,
            "system_error": EscalationPriority.HIGH,
            "sentiment_distress": EscalationPriority.HIGH,
            "legal_threat": EscalationPriority.URGENT,
            "hardship": EscalationPriority.HIGH,
        }
        priority = priority_map.get(args.reason_code, EscalationPriority.MEDIUM)

        package = {
            "session_id": session.session_id,
            "call_id": session.call_id,
            "customer_id": session.customer_id,
            "verified": session.verified,
            "intent": session.current_intent,
            "loan_id": session.current_loan_id,
            "state_at_escalation": session.state,
            "reason_code": args.reason_code,
            "summary": args.summary,
            "turn_count": session.turn_count,
            "timestamp": datetime.utcnow().isoformat(),
        }

        import json as _json
        eq = escalation_repo.enqueue(
            call_id=session.call_id,
            reason_code=args.reason_code,
            priority=priority,
            packaged_context=_json.dumps(package),
        )
        call_record_repo.close(
            session.call_id,
            CallDisposition.ESCALATED,
            summary=args.summary,
            escalation_flag=True,
        )
        session.is_escalated = True
        result = ToolResult(
            status="success",
            message="Escalation created. Connecting you to a specialist now.",
            data={"escalation_id": eq.id, "priority": priority.value},
        )
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _audit(session, "escalate_to_human", {"reason_code": args.reason_code}, result, duration_ms)
        return result

    def end_call(
        self, session: SessionState, args: EndCallInput
    ) -> ToolResult:
        start = time.monotonic()
        disposition_map = {
            "resolved": CallDisposition.RESOLVED,
            "abandoned": CallDisposition.ABANDONED,
            "escalated": CallDisposition.ESCALATED,
        }
        disposition = disposition_map.get(args.disposition, CallDisposition.RESOLVED)
        call_record_repo.close(session.call_id, disposition)
        result = ToolResult(
            status="success",
            message="Call closed.",
            data={"disposition": disposition.value},
        )
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        _audit(session, "end_call", {"disposition": args.disposition}, result, duration_ms)
        return result


tool_executor = ToolExecutor()
