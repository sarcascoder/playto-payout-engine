"""The rubric-mandated concurrency test.

Two threads each attempt to create a 60-paise payout against a merchant
with 100-paise balance. Exactly one must succeed; the other must raise
InsufficientBalance. No overdraw under any race ordering.
"""
import threading
import uuid

import pytest
from django.db import close_old_connections

from accounts.models import Merchant, BankAccount
from payouts.models import LedgerEntry, Payout
from payouts.services import create_payout, _balance_paise
from payouts.exceptions import InsufficientBalance


@pytest.fixture
def funded_merchant(db):
    m = Merchant.objects.create_user(
        email="race@example.com", password="x", name="Race Subject",
    )
    BankAccount.objects.create(
        merchant=m, account_holder_name="Race",
        account_number="1", ifsc_code="HDFC0001234", is_default=True,
    )
    LedgerEntry.objects.create(
        merchant=m, amount_paise=100,
        entry_type=LedgerEntry.CREDIT,
        category=LedgerEntry.CUSTOMER_PAYMENT,
    )
    return m


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_payouts_only_one_succeeds(funded_merchant):
    """Two simultaneous 60-paise payouts on a 100-paise balance.
    Exactly one succeeds, exactly one is rejected, balance never goes negative."""
    bank = funded_merchant.bank_accounts.first()
    barrier = threading.Barrier(2)
    results = {"success": [], "rejected": []}
    lock = threading.Lock()

    def attempt():
        try:
            barrier.wait()  # both threads start at the same instant
            payout, _ = create_payout(
                merchant_id=str(funded_merchant.id),
                amount_paise=60,
                bank_account_id=str(bank.id),
                idempotency_key=str(uuid.uuid4()),
                request_body={"amount_paise": 60, "bank_account_id": str(bank.id)},
            )
            with lock:
                results["success"].append(payout.id)
        except InsufficientBalance:
            with lock:
                results["rejected"].append("insufficient")
        finally:
            close_old_connections()

    t1 = threading.Thread(target=attempt)
    t2 = threading.Thread(target=attempt)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert len(results["success"]) == 1, f"expected exactly 1 success, got {results}"
    assert len(results["rejected"]) == 1, f"expected exactly 1 rejection, got {results}"
    assert _balance_paise(funded_merchant) == 40  # 100 - 60 = 40, never -20
    assert Payout.objects.filter(merchant=funded_merchant).count() == 1


@pytest.mark.django_db(transaction=True)
def test_sequential_two_payouts_both_succeed_if_balance_allows(funded_merchant):
    """Sanity check: the lock doesn't break the happy path."""
    bank = funded_merchant.bank_accounts.first()
    p1, _ = create_payout(
        merchant_id=str(funded_merchant.id), amount_paise=30,
        bank_account_id=str(bank.id), idempotency_key=str(uuid.uuid4()),
        request_body={"amount_paise": 30, "bank_account_id": str(bank.id)},
    )
    p2, _ = create_payout(
        merchant_id=str(funded_merchant.id), amount_paise=40,
        bank_account_id=str(bank.id), idempotency_key=str(uuid.uuid4()),
        request_body={"amount_paise": 40, "bank_account_id": str(bank.id)},
    )
    assert p1.status == Payout.PENDING
    assert p2.status == Payout.PENDING
    assert _balance_paise(funded_merchant) == 30  # 100 - 30 - 40
