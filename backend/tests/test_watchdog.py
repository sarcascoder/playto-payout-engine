"""Watchdog (reap_stuck_payouts) tests.

Verifies that payouts stuck in PROCESSING > 30s are either retried (with
exponential backoff) or, after MAX_ATTEMPTS, marked FAILED with funds returned.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from accounts.models import Merchant, BankAccount
from payouts.models import LedgerEntry, Payout
from payouts.services import _balance_paise
from payouts.tasks import reap_stuck_payouts


@pytest.fixture
def stuck_payout(db):
    m = Merchant.objects.create_user(email="w@example.com", password="x", name="W")
    bank = BankAccount.objects.create(
        merchant=m, account_holder_name="W",
        account_number="1", ifsc_code="HDFC0001234", is_default=True,
    )
    LedgerEntry.objects.create(
        merchant=m, amount_paise=10000,
        entry_type=LedgerEntry.CREDIT, category=LedgerEntry.CUSTOMER_PAYMENT,
    )
    # Hand-craft a payout in PROCESSING with a stale processing_started_at
    payout = Payout.objects.create(
        merchant=m, bank_account=bank,
        amount_paise=3000, status=Payout.PROCESSING,
        attempts=1,
        processing_started_at=timezone.now() - timedelta(seconds=60),
    )
    LedgerEntry.objects.create(
        merchant=m, amount_paise=3000,
        entry_type=LedgerEntry.DEBIT, category=LedgerEntry.PAYOUT_HOLD,
        payout=payout,
    )
    return payout


@pytest.mark.django_db(transaction=True)
def test_watchdog_retries_under_max_attempts(stuck_payout, settings):
    """attempts < MAX_ATTEMPTS → re-enqueue, payout stays in PROCESSING."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    # Stub the retry to skip actually running the bank call
    with patch("payouts.tasks.attempt_payout.apply_async") as mock_apply:
        reap_stuck_payouts()
    stuck_payout.refresh_from_db()
    assert stuck_payout.status == Payout.PROCESSING
    # Watchdog enqueued a retry with exponential backoff
    mock_apply.assert_called_once()
    args, kwargs = mock_apply.call_args
    assert kwargs["countdown"] == 2 ** 1  # attempts was 1 when watchdog ran


@pytest.mark.django_db(transaction=True)
def test_watchdog_fails_after_max_attempts(stuck_payout):
    """attempts >= MAX_ATTEMPTS → transition to FAILED + reversal."""
    stuck_payout.attempts = 3
    stuck_payout.save(update_fields=["attempts"])

    reap_stuck_payouts()

    stuck_payout.refresh_from_db()
    assert stuck_payout.status == Payout.FAILED
    assert _balance_paise(stuck_payout.merchant) == 10000  # 10000 - 3000 + 3000 reversal
    assert LedgerEntry.objects.filter(
        payout=stuck_payout, category=LedgerEntry.PAYOUT_REVERSAL,
    ).exists()
