import uuid

from django.db import models
from django.utils import timezone


class LedgerEntry(models.Model):
    """Append-only ledger. Source of truth for merchant balance.

    Balance = SUM(amount_paise WHERE entry_type=CREDIT)
            - SUM(amount_paise WHERE entry_type=DEBIT)

    Three categories track WHY each entry exists:
      - CUSTOMER_PAYMENT  (CREDIT) - simulated incoming payment
      - PAYOUT_HOLD       (DEBIT)  - written when a payout is requested
      - PAYOUT_REVERSAL   (CREDIT) - written when a payout fails
    """
    CREDIT = "credit"
    DEBIT = "debit"
    ENTRY_TYPES = [(CREDIT, "Credit"), (DEBIT, "Debit")]

    CUSTOMER_PAYMENT = "customer_payment"
    PAYOUT_HOLD = "payout_hold"
    PAYOUT_REVERSAL = "payout_reversal"
    CATEGORIES = [
        (CUSTOMER_PAYMENT, "Customer payment"),
        (PAYOUT_HOLD, "Payout hold"),
        (PAYOUT_REVERSAL, "Payout reversal"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        "accounts.Merchant", on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    amount_paise = models.BigIntegerField()  # always > 0; sign comes from entry_type
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES)
    category = models.CharField(max_length=30, choices=CATEGORIES)
    payout = models.ForeignKey(
        "payouts.Payout", on_delete=models.PROTECT,
        related_name="ledger_entries", null=True, blank=True,
    )
    description = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ledger_entries"
        indexes = [models.Index(fields=["merchant", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_paise__gt=0),
                name="ledger_amount_positive",
            ),
        ]

    def __str__(self):
        sign = "+" if self.entry_type == self.CREDIT else "-"
        return f"{sign}{self.amount_paise}p [{self.category}]"


class Payout(models.Model):
    """A merchant's withdrawal request. Strict state machine."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    STATUSES = [
        (PENDING, "Pending"),
        (PROCESSING, "Processing"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
    ]

    LEGAL_TRANSITIONS = {
        PENDING:    {PROCESSING},
        PROCESSING: {COMPLETED, FAILED},
        COMPLETED:  set(),    # terminal
        FAILED:     set(),    # terminal
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        "accounts.Merchant", on_delete=models.PROTECT, related_name="payouts",
    )
    bank_account = models.ForeignKey(
        "accounts.BankAccount", on_delete=models.PROTECT, related_name="payouts",
    )
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING)
    idempotency_key = models.OneToOneField(
        "payouts.IdempotencyKey", on_delete=models.PROTECT,
        related_name="created_payout", null=True, blank=True,
    )
    attempts = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payouts"
        indexes = [
            models.Index(fields=["merchant", "-created_at"]),
            models.Index(fields=["status", "processing_started_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_paise__gt=0),
                name="payout_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "processing", "completed", "failed"]),
                name="payout_status_valid",
            ),
        ]

    def transition_to(self, new_status: str, *, actor: str, reason: str = ""):
        """Mutate status if the transition is legal; else raise.

        Caller MUST hold the row lock (select_for_update on this Payout
        and on the related Merchant when ledger entries are also written).
        """
        from .exceptions import IllegalStateTransition  # local import to avoid cycle
        legal = self.LEGAL_TRANSITIONS.get(self.status, set())
        if new_status not in legal:
            raise IllegalStateTransition(self.status, new_status, legal)
        old_status = self.status
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        PayoutEvent.objects.create(
            payout=self, from_status=old_status, to_status=new_status,
            actor=actor, reason=reason,
        )


class IdempotencyKey(models.Model):
    """Per-merchant request deduplication. The (key, merchant) UNIQUE INDEX
    is the database-level dedup primitive."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.UUIDField()
    merchant = models.ForeignKey(
        "accounts.Merchant", on_delete=models.PROTECT,
        related_name="idempotency_keys",
    )
    request_fingerprint = models.CharField(max_length=64)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    # Note: idem -> payout navigation uses Payout.idempotency_key reverse accessor
    # (`idem.created_payout`). No explicit FK to avoid circular reference.
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "idempotency_keys"
        constraints = [
            models.UniqueConstraint(
                fields=["key", "merchant"],
                name="idempotency_key_per_merchant",
            ),
        ]
        indexes = [models.Index(fields=["expires_at"])]


class PayoutEvent(models.Model):
    """Audit log of every state transition. Cheap to query, very useful in support."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payout = models.ForeignKey(
        Payout, on_delete=models.CASCADE, related_name="events",
    )
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.CharField(max_length=50)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "payout_events"
        indexes = [models.Index(fields=["payout", "created_at"])]
