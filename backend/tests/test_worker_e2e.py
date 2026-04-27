"""End-to-end worker flow with Celery in eager (synchronous) mode.

Verifies that create_payout → enqueue → attempt_payout → state transition
all chain correctly, and that failure paths atomically reverse the funds.
"""
import uuid

import pytest
from unittest.mock import patch

from accounts.models import Merchant, BankAccount
from payouts.models import LedgerEntry, Payout
from payouts.services import create_payout, _balance_paise


@pytest.fixture
def funded_merchant(db):
    m = Merchant.objects.create_user(email="e@example.com", password="x", name="E")
    BankAccount.objects.create(
        merchant=m, account_holder_name="E",
        account_number="1", ifsc_code="HDFC0001234", is_default=True,
    )
    LedgerEntry.objects.create(
        merchant=m, amount_paise=10000,
        entry_type=LedgerEntry.CREDIT, category=LedgerEntry.CUSTOMER_PAYMENT,
    )
    return m


@pytest.mark.django_db(transaction=True)
def test_payout_succeeds_end_to_end(funded_merchant, settings):
    """When the bank returns success, payout becomes COMPLETED and the
    held funds stay debited (the hold becomes permanent)."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    bank = funded_merchant.bank_accounts.first()

    with patch("payouts.tasks.simulate_bank", return_value="success"):
        payout, _ = create_payout(
            merchant_id=str(funded_merchant.id), amount_paise=3000,
            bank_account_id=str(bank.id), idempotency_key=str(uuid.uuid4()),
            request_body={"amount_paise": 3000, "bank_account_id": str(bank.id)},
        )
        payout.refresh_from_db()

    assert payout.status == Payout.COMPLETED
    # 10000 - 3000 (hold, never reversed) = 7000
    assert _balance_paise(funded_merchant) == 7000


@pytest.mark.django_db(transaction=True)
def test_payout_fails_and_funds_return(funded_merchant, settings):
    """When the bank returns fail, payout becomes FAILED and the held funds
    are atomically returned via a PAYOUT_REVERSAL credit entry."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    bank = funded_merchant.bank_accounts.first()

    with patch("payouts.tasks.simulate_bank", return_value="fail"):
        payout, _ = create_payout(
            merchant_id=str(funded_merchant.id), amount_paise=3000,
            bank_account_id=str(bank.id), idempotency_key=str(uuid.uuid4()),
            request_body={"amount_paise": 3000, "bank_account_id": str(bank.id)},
        )
        payout.refresh_from_db()

    assert payout.status == Payout.FAILED
    # 10000 - 3000 (hold) + 3000 (reversal) = 10000
    assert _balance_paise(funded_merchant) == 10000

    # The reversal entry exists and is linked to the payout
    reversal = LedgerEntry.objects.get(
        payout=payout, category=LedgerEntry.PAYOUT_REVERSAL,
    )
    assert reversal.entry_type == LedgerEntry.CREDIT
    assert reversal.amount_paise == 3000


@pytest.mark.django_db(transaction=True)
def test_payout_hangs_stays_in_processing(funded_merchant, settings):
    """When the bank 'hangs' (returns no transition), payout stays in PROCESSING.
    The watchdog (separate test) is what eventually retries or fails it."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    bank = funded_merchant.bank_accounts.first()

    with patch("payouts.tasks.simulate_bank", return_value="hang"):
        payout, _ = create_payout(
            merchant_id=str(funded_merchant.id), amount_paise=3000,
            bank_account_id=str(bank.id), idempotency_key=str(uuid.uuid4()),
            request_body={"amount_paise": 3000, "bank_account_id": str(bank.id)},
        )
        payout.refresh_from_db()

    assert payout.status == Payout.PROCESSING
    assert payout.attempts == 1
    assert payout.processing_started_at is not None
    # Held funds still debited
    assert _balance_paise(funded_merchant) == 7000
