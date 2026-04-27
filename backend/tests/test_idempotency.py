"""The rubric-mandated idempotency test.

Same idempotency key used twice → exactly one Payout, second returns the same response.
"""
import uuid

import pytest

from accounts.models import Merchant, BankAccount
from payouts.models import LedgerEntry, Payout, IdempotencyKey
from payouts.services import create_payout
from payouts.exceptions import IdempotencyKeyMismatch, InsufficientBalance


@pytest.fixture
def funded_merchant(db):
    m = Merchant.objects.create_user(email="i@example.com", password="x", name="Idem Test")
    BankAccount.objects.create(
        merchant=m, account_holder_name="I",
        account_number="1", ifsc_code="HDFC0001234", is_default=True,
    )
    LedgerEntry.objects.create(
        merchant=m, amount_paise=10000,
        entry_type=LedgerEntry.CREDIT, category=LedgerEntry.CUSTOMER_PAYMENT,
    )
    return m


@pytest.mark.django_db
def test_same_key_returns_same_payout(funded_merchant):
    bank = funded_merchant.bank_accounts.first()
    key = str(uuid.uuid4())
    body = {"amount_paise": 5000, "bank_account_id": str(bank.id)}

    p1, replay1 = create_payout(
        merchant_id=str(funded_merchant.id), amount_paise=5000,
        bank_account_id=str(bank.id), idempotency_key=key, request_body=body,
    )
    p2, replay2 = create_payout(
        merchant_id=str(funded_merchant.id), amount_paise=5000,
        bank_account_id=str(bank.id), idempotency_key=key, request_body=body,
    )

    assert p1.id == p2.id
    assert replay1 is False
    assert replay2 is True
    assert Payout.objects.filter(merchant=funded_merchant).count() == 1


@pytest.mark.django_db
def test_same_key_different_body_raises_mismatch(funded_merchant):
    bank = funded_merchant.bank_accounts.first()
    key = str(uuid.uuid4())

    create_payout(
        merchant_id=str(funded_merchant.id), amount_paise=5000,
        bank_account_id=str(bank.id), idempotency_key=key,
        request_body={"amount_paise": 5000, "bank_account_id": str(bank.id)},
    )
    with pytest.raises(IdempotencyKeyMismatch):
        create_payout(
            merchant_id=str(funded_merchant.id), amount_paise=3000,
            bank_account_id=str(bank.id), idempotency_key=key,
            request_body={"amount_paise": 3000, "bank_account_id": str(bank.id)},
        )


@pytest.mark.django_db
def test_failed_request_idempotency_persists_error(funded_merchant):
    """If first request hits InsufficientBalance, the idem row persists the 422.
    Stripe-style behavior: errors are part of the idempotent response too."""
    bank = funded_merchant.bank_accounts.first()
    key = str(uuid.uuid4())
    body = {"amount_paise": 99999, "bank_account_id": str(bank.id)}

    with pytest.raises(InsufficientBalance):
        create_payout(
            merchant_id=str(funded_merchant.id), amount_paise=99999,
            bank_account_id=str(bank.id), idempotency_key=key, request_body=body,
        )

    # The idem row now exists with the persisted error response
    idem = IdempotencyKey.objects.get(key=key, merchant=funded_merchant)
    assert idem.response_status == 422
    assert idem.response_body["error"] == "insufficient_balance"


@pytest.mark.django_db
def test_different_merchants_can_share_key(db):
    """Idempotency keys are scoped per merchant via UNIQUE(key, merchant_id)."""
    m1 = Merchant.objects.create_user(email="a@x.com", password="x", name="A")
    m2 = Merchant.objects.create_user(email="b@x.com", password="x", name="B")
    for m in (m1, m2):
        BankAccount.objects.create(
            merchant=m, account_holder_name=m.name,
            account_number="1", ifsc_code="HDFC0001234", is_default=True,
        )
        LedgerEntry.objects.create(
            merchant=m, amount_paise=10000,
            entry_type=LedgerEntry.CREDIT, category=LedgerEntry.CUSTOMER_PAYMENT,
        )

    shared_key = str(uuid.uuid4())
    bank1 = m1.bank_accounts.first()
    bank2 = m2.bank_accounts.first()

    p1, _ = create_payout(
        merchant_id=str(m1.id), amount_paise=1000,
        bank_account_id=str(bank1.id), idempotency_key=shared_key,
        request_body={"amount_paise": 1000, "bank_account_id": str(bank1.id)},
    )
    p2, _ = create_payout(
        merchant_id=str(m2.id), amount_paise=1000,
        bank_account_id=str(bank2.id), idempotency_key=shared_key,
        request_body={"amount_paise": 1000, "bank_account_id": str(bank2.id)},
    )
    assert p1.id != p2.id
    assert p1.merchant_id == m1.id
    assert p2.merchant_id == m2.id
