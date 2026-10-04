TOOL_DEFINITIONS = [
    {
        "name": "verify_identity",
        "description": "Verify the caller's identity by checking their customer ID, last four digits of their account number, and six-digit security PIN against our records. Must be called before accessing any account information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "The customer ID provided by the caller (e.g. C-0001)"},
                "last_four_account": {"type": "string", "description": "Last four digits of the account number", "pattern": "^\\d{4}$"},
                "security_pin": {"type": "string", "description": "Six-digit security PIN", "pattern": "^\\d{6}$"},
            },
            "required": ["customer_id", "last_four_account", "security_pin"],
        },
    },
    {
        "name": "get_loan_summary",
        "description": "Retrieve the outstanding balance, EMI amount, due date, and status for the verified customer's active loan(s). Requires identity verification first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "string", "description": "Optional specific loan ID. If omitted, returns all active loans."},
            },
            "required": [],
        },
    },
    {
        "name": "get_payment_history",
        "description": "Retrieve the last N payments for a specific loan. Requires identity verification first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "string", "description": "The loan ID to retrieve payments for"},
                "limit": {"type": "integer", "description": "Number of payments to return (1-20)", "default": 5},
            },
            "required": ["loan_id"],
        },
    },
    {
        "name": "record_payment_promise",
        "description": "Record a promise to pay a specified amount by a specified date. Requires verification. Always read back the amount and date for explicit confirmation before calling this tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "string", "description": "The loan ID for which the promise is being made"},
                "promised_amount": {"type": "number", "description": "The promised payment amount in Indian Rupees"},
                "promised_date": {"type": "string", "description": "Date by which payment will be made, in YYYY-MM-DD format"},
                "idempotency_key": {"type": "string", "description": "Unique key to prevent duplicate promises. Generate a UUID."},
            },
            "required": ["loan_id", "promised_amount", "promised_date", "idempotency_key"],
        },
    },
    {
        "name": "request_due_date_change",
        "description": "Submit a request to change the EMI due date for a loan. The change can be by up to the configured maximum number of days. Requires verification and explicit confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_id": {"type": "string", "description": "The loan ID for the due date change"},
                "requested_day": {"type": "integer", "description": "The new day of the month for EMI (1-28)", "minimum": 1, "maximum": 28},
            },
            "required": ["loan_id", "requested_day"],
        },
    },
    {
        "name": "log_complaint",
        "description": "Log a formal complaint from the caller with a category and description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Complaint category (e.g. billing_error, harassment, incorrect_charge, service_quality)"},
                "text": {"type": "string", "description": "Detailed description of the complaint as stated by the caller"},
            },
            "required": ["category", "text"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Transfer the call to a human specialist. Use when the caller asks for a human, when policy requires it, when repeated failures occur, or when you cannot resolve the issue. Always explain to the caller what is happening.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason_code": {
                    "type": "string",
                    "description": "Reason for escalation",
                    "enum": ["explicit_request", "low_confidence", "policy_trigger", "repeated_failure", "system_error", "sentiment_distress", "legal_threat", "hardship"],
                },
                "summary": {"type": "string", "description": "Brief summary of what was discussed and what the caller needs, for the human specialist"},
            },
            "required": ["reason_code", "summary"],
        },
    },
    {
        "name": "end_call",
        "description": "Close the call session with a disposition. Use after the caller has confirmed they have no more questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "disposition": {
                    "type": "string",
                    "enum": ["resolved", "abandoned", "escalated"],
                    "default": "resolved",
                },
            },
            "required": [],
        },
    },
]

STATE_ALLOWED_TOOLS: dict[str, list[str]] = {
    "GREETING": [],
    "IDENTIFY": ["verify_identity", "escalate_to_human"],
    "VERIFY": ["verify_identity", "escalate_to_human"],
    "INTENT": [
        "get_loan_summary",
        "get_payment_history",
        "record_payment_promise",
        "request_due_date_change",
        "log_complaint",
        "escalate_to_human",
        "end_call",
    ],
    "SERVICE": [
        "get_loan_summary",
        "get_payment_history",
        "record_payment_promise",
        "request_due_date_change",
        "log_complaint",
        "escalate_to_human",
        "end_call",
    ],
    "CONFIRM": ["record_payment_promise", "request_due_date_change", "escalate_to_human", "end_call"],
    "WRAP_UP": ["end_call", "escalate_to_human"],
    "ESCALATE": ["escalate_to_human"],
    "CLOSED": [],
}


def get_tools_for_state(state: str) -> list[dict]:
    allowed = STATE_ALLOWED_TOOLS.get(state, [])
    return [t for t in TOOL_DEFINITIONS if t["name"] in allowed]
