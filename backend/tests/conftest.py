import pytest

from accounts.models import Merchant, BankAccount


@pytest.fixture
def merchant(db):
    return Merchant.objects.create_user(
        email="alice@example.com", password="dev-pass", name="Alice's Studio",
    )


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant,
        account_holder_name="Alice's Studio Pvt Ltd",
        account_number="123456789012",
        ifsc_code="HDFC0001234",
        is_default=True,
    )
