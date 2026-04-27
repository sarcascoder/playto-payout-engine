class PayoutError(Exception):
    """Base for all payout-domain errors. http_status + to_dict() for serialization."""
    http_status = 500
    error_code = "payout_error"

    def to_dict(self) -> dict:
        return {"error": self.error_code}


class InsufficientBalance(PayoutError):
    http_status = 422
    error_code = "insufficient_balance"

    def __init__(self, available: int, requested: int):
        super().__init__(f"available {available} < requested {requested}")
        self.available = available
        self.requested = requested

    def to_dict(self):
        return {
            "error": self.error_code,
            "available_paise": self.available,
            "requested_paise": self.requested,
        }


class BankAccountNotFound(PayoutError):
    http_status = 404
    error_code = "bank_account_not_found"


class IdempotencyKeyMismatch(PayoutError):
    http_status = 409
    error_code = "idempotency_key_mismatch"


class IdempotencyKeyInFlight(PayoutError):
    http_status = 409
    error_code = "idempotency_key_in_progress"


class IllegalStateTransition(PayoutError):
    http_status = 409
    error_code = "illegal_state_transition"

    def __init__(self, from_status: str, to_status: str, legal: set):
        super().__init__(
            f"{from_status} → {to_status} not allowed; "
            f"legal: {sorted(legal) or 'terminal'}"
        )
        self.from_status = from_status
        self.to_status = to_status

    def to_dict(self):
        return {
            "error": self.error_code,
            "from_status": self.from_status,
            "to_status": self.to_status,
        }
