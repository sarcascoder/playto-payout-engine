"""Tests for the demo top-up service that credits a merchant's balance."""
import pytest

from payouts.models import LedgerEntry
from payouts.services import (
    _balance_paise, create_credit_entry, MIN_CREDIT_PAISE, MAX_CREDIT_PAISE,
)


@pytest.mark.django_db
def test_create_credit_writes_one_ledger_row(merchant):
    entry = create_credit_entry(merchant=merchant, amount_paise=5000_00)
    assert entry.entry_type == LedgerEntry.CREDIT
    assert entry.category == LedgerEntry.CUSTOMER_PAYMENT
    assert entry.amount_paise == 5000_00
    assert entry.merchant_id == merchant.id
    assert "Demo top-up" in entry.description
    assert LedgerEntry.objects.filter(merchant=merchant).count() == 1


@pytest.mark.django_db
def test_create_credit_increases_balance(merchant):
    assert _balance_paise(merchant) == 0
    create_credit_entry(merchant=merchant, amount_paise=2500_00)
    assert _balance_paise(merchant) == 2500_00
    create_credit_entry(merchant=merchant, amount_paise=1000_00)
    assert _balance_paise(merchant) == 3500_00


@pytest.mark.django_db
def test_create_credit_below_minimum_rejected(merchant):
    with pytest.raises(ValueError, match="amount_paise"):
        create_credit_entry(merchant=merchant, amount_paise=MIN_CREDIT_PAISE - 1)
    assert LedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test_create_credit_above_maximum_rejected(merchant):
    with pytest.raises(ValueError, match="amount_paise"):
        create_credit_entry(merchant=merchant, amount_paise=MAX_CREDIT_PAISE + 1)
    assert LedgerEntry.objects.count() == 0


# ──────────── view layer ────────────
from rest_framework.test import APIClient


@pytest.fixture
def authed_client(merchant):
    client = APIClient()
    client.force_authenticate(user=merchant)
    return client


@pytest.mark.django_db
def test_post_credits_creates_entry_and_returns_201(authed_client, merchant):
    resp = authed_client.post("/api/v1/credits", {"amount_paise": 5000_00}, format="json")
    assert resp.status_code == 201
    assert resp.data["amount_paise"] == 5000_00
    assert resp.data["entry_type"] == LedgerEntry.CREDIT
    assert resp.data["category"] == LedgerEntry.CUSTOMER_PAYMENT
    assert _balance_paise(merchant) == 5000_00


@pytest.mark.django_db
def test_post_credits_rejects_below_min(authed_client):
    resp = authed_client.post("/api/v1/credits", {"amount_paise": 50}, format="json")
    assert resp.status_code == 400
    assert resp.data["error"] == "invalid_amount"


@pytest.mark.django_db
def test_post_credits_rejects_above_max(authed_client):
    resp = authed_client.post(
        "/api/v1/credits", {"amount_paise": MAX_CREDIT_PAISE + 1}, format="json",
    )
    assert resp.status_code == 400
    assert resp.data["error"] == "invalid_amount"


@pytest.mark.django_db
def test_post_credits_requires_auth(db):
    anon = APIClient()
    resp = anon.post("/api/v1/credits", {"amount_paise": 5000_00}, format="json")
    assert resp.status_code == 401
