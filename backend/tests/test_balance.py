import pytest

from payouts.models import LedgerEntry
from payouts.services import _balance_paise


@pytest.mark.django_db
def test_empty_ledger_returns_zero(merchant):
    assert _balance_paise(merchant) == 0


@pytest.mark.django_db
def test_single_credit_returns_amount(merchant):
    LedgerEntry.objects.create(
        merchant=merchant, amount_paise=10000,
        entry_type=LedgerEntry.CREDIT, category=LedgerEntry.CUSTOMER_PAYMENT,
    )
    assert _balance_paise(merchant) == 10000


@pytest.mark.django_db
def test_credits_minus_debits(merchant):
    LedgerEntry.objects.create(
        merchant=merchant, amount_paise=10000,
        entry_type=LedgerEntry.CREDIT, category=LedgerEntry.CUSTOMER_PAYMENT,
    )
    LedgerEntry.objects.create(
        merchant=merchant, amount_paise=3000,
        entry_type=LedgerEntry.DEBIT, category=LedgerEntry.PAYOUT_HOLD,
    )
    LedgerEntry.objects.create(
        merchant=merchant, amount_paise=500,
        entry_type=LedgerEntry.CREDIT, category=LedgerEntry.PAYOUT_REVERSAL,
    )
    # 10000 + 500 - 3000 = 7500
    assert _balance_paise(merchant) == 7500


@pytest.mark.django_db
def test_balance_is_integer_type(merchant):
    LedgerEntry.objects.create(
        merchant=merchant, amount_paise=42,
        entry_type=LedgerEntry.CREDIT, category=LedgerEntry.CUSTOMER_PAYMENT,
    )
    assert isinstance(_balance_paise(merchant), int)
