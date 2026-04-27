"""Money-moving service. Every function in here that writes a LedgerEntry
MUST first acquire the merchant row lock via select_for_update inside an
atomic block. This invariant is the foundation of the concurrency guarantee.
"""
import hashlib
import json
from datetime import timedelta

from django.db import transaction, IntegrityError
from django.db.models import Sum, Case, When, F, IntegerField, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.models import Merchant, BankAccount
from .models import LedgerEntry, Payout, IdempotencyKey, PayoutEvent
from .exceptions import (
    InsufficientBalance, IdempotencyKeyMismatch,
    IdempotencyKeyInFlight, BankAccountNotFound,
)


IDEMPOTENCY_TTL = timedelta(hours=24)


# ────────────────────────────── balance helpers ──────────────────────────────

def _balance_paise(merchant: Merchant) -> int:
    """Source-of-truth balance: SUM(credits) - SUM(debits) in paise.

    Computed entirely in Postgres via a single CASE/WHEN aggregate.
    No Python-side arithmetic on individual rows.
    Returns 0 for empty ledger (Coalesce wraps the SUM).
    """
    agg = LedgerEntry.objects.filter(merchant=merchant).aggregate(
        balance=Coalesce(
            Sum(Case(
                When(entry_type=LedgerEntry.CREDIT, then=F("amount_paise")),
                When(entry_type=LedgerEntry.DEBIT, then=-F("amount_paise")),
                output_field=IntegerField(),
            )),
            Value(0),
        )
    )
    return int(agg["balance"])


def _held_paise(merchant: Merchant) -> int:
    """Sum of amounts of payouts in pending or processing state.

    Display-only: these amounts are already debited from balance via PAYOUT_HOLD entries.
    """
    agg = Payout.objects.filter(
        merchant=merchant,
        status__in=[Payout.PENDING, Payout.PROCESSING],
    ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))
    return int(agg["total"])


def get_balance_summary(merchant: Merchant) -> dict:
    available = _balance_paise(merchant)
    held = _held_paise(merchant)
    return {
        "available_paise": available,
        "held_paise": held,
        "total_paise": available + held,
    }


# ────────────────────────────── idempotency ──────────────────────────────

def _fingerprint(body: dict) -> str:
    """SHA-256 of canonicalized request body. Catches "same key, different body"."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ────────────────────────────── KEYSTONE ──────────────────────────────

def create_payout(
    *,
    merchant_id: str,
    amount_paise: int,
    bank_account_id: str,
    idempotency_key: str,
    request_body: dict,
) -> tuple[Payout, bool]:
    """Create a payout with full concurrency + idempotency guarantees.

    Returns (payout, was_idempotent_replay).

    Concurrency: holds Postgres row-level write lock on the Merchant row
    via select_for_update(), serializing all balance-affecting writes per
    merchant. Different merchants proceed in parallel.

    Idempotency: separate transaction claims the (key, merchant) row via
    a UNIQUE INDEX, which is the database-level dedup primitive. Failure
    responses persist so retries get the same error (Stripe-style).
    """
    fp = _fingerprint(request_body)

    # ── Phase 1: claim the idempotency key in its OWN transaction ──
    # The (key, merchant) UNIQUE INDEX is the dedup primitive.
    # Two same-key requests racing? Both INSERT, exactly one wins,
    # the loser catches IntegrityError and reads the winner's row.
    try:
        with transaction.atomic():
            idem = IdempotencyKey.objects.create(
                key=idempotency_key,
                merchant_id=merchant_id,
                request_fingerprint=fp,
                expires_at=timezone.now() + IDEMPOTENCY_TTL,
            )
        is_first_request = True
    except IntegrityError:
        idem = IdempotencyKey.objects.get(
            key=idempotency_key, merchant_id=merchant_id
        )
        is_first_request = False

    if not is_first_request:
        if idem.request_fingerprint != fp:
            raise IdempotencyKeyMismatch()
        if idem.response_status is None:
            # First request still processing; client should retry shortly.
            raise IdempotencyKeyInFlight()
        # Replay: return the original payout.
        return idem.created_payout, True

    # ── Phase 2: the money-moving transaction ──
    try:
        with transaction.atomic():
            # 2a. ROW LOCK on the merchant. Postgres holds a write lock on
            #     this row until the surrounding atomic block commits or
            #     rolls back. Other transactions hitting the same row block.
            merchant = (
                Merchant.objects
                .select_for_update()        # SQL: SELECT ... FOR UPDATE
                .get(id=merchant_id)
            )

            # 2b. Validate bank account inside the lock.
            try:
                bank = BankAccount.objects.get(
                    id=bank_account_id, merchant=merchant
                )
            except BankAccount.DoesNotExist:
                raise BankAccountNotFound()

            # 2c. Compute available balance inside the lock.
            #     Because we hold the merchant row lock, no other writer
            #     can mutate this merchant's ledger between this read and
            #     the write below.
            available = _balance_paise(merchant)
            if available < amount_paise:
                raise InsufficientBalance(
                    available=available, requested=amount_paise
                )

            # 2d. Create the payout in PENDING.
            payout = Payout.objects.create(
                merchant=merchant,
                bank_account=bank,
                amount_paise=amount_paise,
                status=Payout.PENDING,
                idempotency_key=idem,
            )

            # 2e. Write the DEBIT_HOLD entry. Balance has now dropped.
            LedgerEntry.objects.create(
                merchant=merchant,
                amount_paise=amount_paise,
                entry_type=LedgerEntry.DEBIT,
                category=LedgerEntry.PAYOUT_HOLD,
                payout=payout,
                description=f"Hold for payout {payout.id}",
            )

            PayoutEvent.objects.create(
                payout=payout, from_status="", to_status=Payout.PENDING,
                actor="api", reason="payout_requested",
            )

            # 2f. Backfill the idempotency row with the success response.
            idem.response_status = 201
            idem.response_body = {
                "id": str(payout.id),
                "amount_paise": amount_paise,
                "status": Payout.PENDING,
                "bank_account_id": str(bank.id),
                "created_at": payout.created_at.isoformat(),
                "attempts": 0,
            }
            idem.save(update_fields=["response_status", "response_body"])

            # 2g. Enqueue worker AFTER commit. transaction.on_commit fires
            #     the lambda only if commit succeeds — so the worker never
            #     sees a payout that doesn't exist in the DB.
            transaction.on_commit(
                lambda: _enqueue_attempt_payout(str(payout.id))
            )

        return payout, False

    except (InsufficientBalance, BankAccountNotFound) as e:
        # Persist the error response on the idem row in its OWN transaction
        # so future retries with the same key get the same response.
        # Stripe behaves exactly this way.
        with transaction.atomic():
            idem.response_status = e.http_status
            idem.response_body = e.to_dict()
            idem.save(update_fields=["response_status", "response_body"])
        raise


def _enqueue_attempt_payout(payout_id: str):
    """Stub for D3 — does nothing yet. Wired to Celery in Task 19."""
    return
