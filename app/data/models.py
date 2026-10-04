import enum
import random
from datetime import date, datetime, timedelta

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String, primary_key=True)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    preferred_language = Column(String, default="en")
    last_four_account = Column(String(4), nullable=False)
    security_pin = Column(String(6), nullable=False)
    consent_to_call = Column(Boolean, default=True)
    do_not_call = Column(Boolean, default=False)
    is_vulnerable = Column(Boolean, default=False)

    loans = relationship("Loan", back_populates="customer")
    call_records = relationship("CallRecord", back_populates="customer")
    complaints = relationship("Complaint", back_populates="customer")


class LoanStatus(str, enum.Enum):
    CURRENT = "current"
    OVERDUE = "overdue"
    CLOSED = "closed"


class LoanProduct(str, enum.Enum):
    PERSONAL = "personal"
    AUTO = "auto"
    HOME = "home"


class Loan(Base):
    __tablename__ = "loans"

    id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    product_type = Column(Enum(LoanProduct), nullable=False)
    principal = Column(Float, nullable=False)
    outstanding_balance = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    emi_amount = Column(Float, nullable=False)
    emi_due_date = Column(Integer, nullable=True)
    status = Column(Enum(LoanStatus), nullable=False, default=LoanStatus.CURRENT)
    days_past_due = Column(Integer, default=0)

    customer = relationship("Customer", back_populates="loans")
    payments = relationship("Payment", back_populates="loan")
    promises = relationship("PromiseToPay", back_populates="loan")


class PaymentStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True)
    loan_id = Column(String, ForeignKey("loans.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_date = Column(Date, nullable=False)
    mode = Column(String, nullable=False)
    status = Column(Enum(PaymentStatus), nullable=False)

    loan = relationship("Loan", back_populates="payments")


class PromiseStatus(str, enum.Enum):
    PENDING = "pending"
    KEPT = "kept"
    BROKEN = "broken"


class PromiseToPay(Base):
    __tablename__ = "promises_to_pay"

    id = Column(String, primary_key=True)
    loan_id = Column(String, ForeignKey("loans.id"), nullable=False)
    promised_amount = Column(Float, nullable=False)
    promised_date = Column(Date, nullable=False)
    channel = Column(String, default="voice")
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(PromiseStatus), default=PromiseStatus.PENDING)
    idempotency_key = Column(String, unique=True, nullable=False)

    loan = relationship("Loan", back_populates="promises")


class CallDisposition(str, enum.Enum):
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"
    IN_PROGRESS = "in_progress"


class CallRecord(Base):
    __tablename__ = "call_records"

    id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    disposition = Column(Enum(CallDisposition), default=CallDisposition.IN_PROGRESS)
    escalation_flag = Column(Boolean, default=False)
    summary = Column(Text, nullable=True)

    customer = relationship("Customer", back_populates="call_records")
    escalations = relationship("EscalationQueue", back_populates="call_record")


class ComplaintStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    category = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    status = Column(Enum(ComplaintStatus), default=ComplaintStatus.OPEN)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="complaints")


class EscalationPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class EscalationStatus(str, enum.Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"


class EscalationQueue(Base):
    __tablename__ = "escalation_queue"

    id = Column(String, primary_key=True)
    call_id = Column(String, ForeignKey("call_records.id"), nullable=False)
    reason_code = Column(String, nullable=False)
    priority = Column(Enum(EscalationPriority), default=EscalationPriority.MEDIUM)
    packaged_context = Column(Text, nullable=False)
    status = Column(Enum(EscalationStatus), default=EscalationStatus.QUEUED)
    created_at = Column(DateTime, default=datetime.utcnow)

    call_record = relationship("CallRecord", back_populates="escalations")


def create_tables(engine):
    Base.metadata.create_all(engine)


def _rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def seed_database(engine):
    rng = _rng(42)
    with Session(engine) as session:
        if session.query(Customer).count() > 0:
            return

        first_names = [
            "Arjun", "Priya", "Rahul", "Sneha", "Vikram", "Ananya", "Deepak", "Kavya",
            "Suresh", "Meera", "Rohit", "Pooja", "Amit", "Divya", "Kiran", "Lakshmi",
            "Manish", "Nisha", "Sanjay", "Ritu", "Ajay", "Sunita", "Rajesh", "Geeta",
            "Vivek", "Sonal", "Manoj", "Rekha", "Pankaj", "Smita",
        ]
        last_names = [
            "Sharma", "Verma", "Patel", "Singh", "Kumar", "Gupta", "Nair", "Reddy",
            "Iyer", "Mehta", "Joshi", "Agarwal", "Pillai", "Bose", "Chatterjee",
        ]
        products = list(LoanProduct)
        modes = ["NEFT", "UPI", "NACH", "Cheque", "Cash"]

        customers = []
        for i in range(1, 101):
            cid = f"C-{i:04d}"
            fn = rng.choice(first_names)
            ln = rng.choice(last_names)
            dob = date(rng.randint(1960, 2000), rng.randint(1, 12), rng.randint(1, 28))

            if i == 1:
                last_four = "4512"
                pin = "849201"
            elif i == 2:
                last_four = "3194"
                pin = "512849"
            elif i == 3:
                last_four = "7712"
                pin = "129845"
            elif i == 4:
                last_four = "8821"
                pin = "664321"
            elif i == 5:
                last_four = "5555"
                pin = "555555"
            elif i == 9:
                last_four = "9999"
                pin = "999999"
            else:
                last_four = "1234" if i < 55 else f"{rng.randint(1000, 9999)}"
                pin = "123456" if i < 55 else f"{rng.randint(100000, 999999)}"

            dnc = (i == 5)
            vulnerable = i in (7, 13)
            c = Customer(
                id=cid,
                full_name=f"{fn} {ln}",
                phone=f"+91{rng.randint(7000000000, 9999999999)}",
                date_of_birth=dob,
                last_four_account=last_four,
                security_pin=pin,
                consent_to_call=not dnc,
                do_not_call=dnc,
                is_vulnerable=vulnerable,
            )
            customers.append(c)
            session.add(c)

        session.flush()

        loans = []
        for i, cust in enumerate(customers):
            num_loans = 2 if i in (0, 10, 20, 30) else 1
            for j in range(num_loans):
                lid = f"L-{i:04d}-{j}"
                product = rng.choice(products)
                principal = rng.choice([100000, 200000, 500000, 1000000, 2500000])
                rate = rng.uniform(8.5, 18.0)
                tenure_months = rng.choice([12, 24, 36, 60, 120, 240])
                monthly_rate = rate / 12 / 100
                emi = principal * monthly_rate / (1 - (1 + monthly_rate) ** -tenure_months)
                paid_months = rng.randint(0, tenure_months - 1)
                outstanding = principal * (1 + monthly_rate) ** paid_months - emi * (
                    (1 + monthly_rate) ** paid_months - 1
                ) / monthly_rate
                outstanding = max(0.0, outstanding)

                if i == 15:
                    status = LoanStatus.CLOSED
                    outstanding = 0.0
                    dpd = 0
                    due_day = None
                elif i in (8, 9, 11):
                    status = LoanStatus.OVERDUE
                    dpd = rng.randint(91, 180)
                    due_day = rng.randint(1, 28)
                elif i in (3, 4, 6):
                    status = LoanStatus.OVERDUE
                    dpd = rng.randint(1, 60)
                    due_day = rng.randint(1, 28)
                elif i == 25:
                    status = LoanStatus.CURRENT
                    dpd = 0
                    due_day = None
                else:
                    status = LoanStatus.CURRENT
                    dpd = 0
                    due_day = rng.randint(1, 28)

                loan = Loan(
                    id=lid,
                    customer_id=cust.id,
                    product_type=product,
                    principal=round(principal, 2),
                    outstanding_balance=round(outstanding, 2),
                    interest_rate=round(rate, 2),
                    emi_amount=round(emi, 2),
                    emi_due_date=due_day,
                    status=status,
                    days_past_due=dpd,
                )
                loans.append(loan)
                session.add(loan)

                for k in range(rng.randint(0, 5)):
                    pay_date = date.today() - timedelta(days=30 * (k + 1))
                    payment = Payment(
                        id=f"P-{i:04d}-{j}-{k}",
                        loan_id=lid,
                        amount=round(emi, 2),
                        payment_date=pay_date,
                        mode=rng.choice(modes),
                        status=PaymentStatus.SUCCESS,
                    )
                    session.add(payment)

        session.commit()
