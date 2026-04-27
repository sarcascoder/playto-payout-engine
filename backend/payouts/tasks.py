"""Celery tasks for the payout worker.

attempt_payout       — drives a payout through the bank simulator
mark_payout_failed   — (in services.py) atomically fails + reverses
reap_stuck_payouts   — watchdog: retries or finalizes payouts stuck in PROCESSING > 30s
purge_expired_idempotency — TTL cleanup, runs hourly
"""
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from accounts.models import Merchant
from .models import Payout, IdempotencyKey, LedgerEntry
from .services import mark_payout_failed
from .simulator import simulate_bank


WATCHDOG_TIMEOUT = timedelta(seconds=30)
MAX_ATTEMPTS = 3


@shared_task(bind=True, max_retries=0)
def attempt_payout(self, payout_id: str):
    """Attempt to settle a payout via the simulated bank.

    Accepts both PENDING (first attempt, enqueued by create_payout) and
    PROCESSING (retry, enqueued by reap_stuck_payouts). Bumps attempts
    and resets processing_started_at on each call. State machine stays
    strict — retries do NOT move state backwards.
    """
    with transaction.atomic():
        try:
            p = Payout.objects.select_for_update().get(id=payout_id)
        except Payout.DoesNotExist:
            return
        if p.status not in (Payout.PENDING, Payout.PROCESSING):
            return  # terminal already; safe no-op
        if p.status == Payout.PENDING:
            p.transition_to(Payout.PROCESSING, actor="worker")
        p.attempts += 1
        p.processing_started_at = timezone.now()
        p.save(update_fields=["attempts", "processing_started_at"])

    # Bank call OUTSIDE the transaction — no locks held during slow I/O.
    outcome = simulate_bank()

    if outcome == "success":
        with transaction.atomic():
            p = Payout.objects.select_for_update().get(id=payout_id)
            if p.status == Payout.PROCESSING:
                p.transition_to(Payout.COMPLETED, actor="worker", reason="bank_settled")
    elif outcome == "fail":
        mark_payout_failed(payout_id, reason="bank_rejected")
    # "hang" → return without transition; watchdog will re-enqueue


@shared_task
def reap_stuck_payouts():
    """Find payouts stuck in PROCESSING > 30s and either retry or fail.

    Retry strategy: payout STAYS in PROCESSING (no backwards transition).
    Watchdog re-enqueues attempt_payout with exponential backoff. After
    MAX_ATTEMPTS, the payout is failed and funds are returned atomically.
    """
    cutoff = timezone.now() - WATCHDOG_TIMEOUT
    stuck_ids = list(Payout.objects.filter(
        status=Payout.PROCESSING,
        processing_started_at__lt=cutoff,
    ).values_list("id", flat=True))

    for pid in stuck_ids:
        with transaction.atomic():
            p = Payout.objects.select_for_update().get(id=pid)
            if p.status != Payout.PROCESSING:
                continue
            if p.attempts >= MAX_ATTEMPTS:
                # Max retries — fail and reverse atomically.
                merchant = Merchant.objects.select_for_update().get(id=p.merchant_id)
                p.transition_to(
                    Payout.FAILED, actor="watchdog",
                    reason="max_retries_exceeded",
                )
                p.last_error = "max_retries_exceeded"
                p.save(update_fields=["last_error"])
                LedgerEntry.objects.create(
                    merchant=merchant, amount_paise=p.amount_paise,
                    entry_type=LedgerEntry.CREDIT,
                    category=LedgerEntry.PAYOUT_REVERSAL,
                    payout=p, description="Reversal: max retries exceeded",
                )
            else:
                # Re-enqueue retry. Payout stays in PROCESSING — no
                # backwards transition. attempt_payout accepts PROCESSING
                # as a valid entry state.
                attempts = p.attempts
                transaction.on_commit(
                    lambda pid=str(pid), a=attempts: attempt_payout.apply_async(
                        args=[pid], countdown=2 ** a,
                    )
                )


@shared_task
def purge_expired_idempotency():
    """Delete idempotency rows past their TTL. Runs hourly."""
    deleted, _ = IdempotencyKey.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()
    return deleted
