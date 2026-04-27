import pytest

from payouts.models import Payout, PayoutEvent
from payouts.exceptions import IllegalStateTransition


@pytest.fixture
def payout(merchant, bank_account):
    return Payout.objects.create(
        merchant=merchant, bank_account=bank_account,
        amount_paise=10000, status=Payout.PENDING,
    )


@pytest.mark.django_db
def test_pending_to_processing_legal(payout):
    payout.transition_to(Payout.PROCESSING, actor="worker")
    assert payout.status == Payout.PROCESSING
    assert PayoutEvent.objects.filter(
        payout=payout, to_status=Payout.PROCESSING
    ).exists()


@pytest.mark.django_db
def test_processing_to_completed_legal(payout):
    payout.transition_to(Payout.PROCESSING, actor="worker")
    payout.transition_to(Payout.COMPLETED, actor="worker")
    assert payout.status == Payout.COMPLETED


@pytest.mark.django_db
def test_processing_to_failed_legal(payout):
    payout.transition_to(Payout.PROCESSING, actor="worker")
    payout.transition_to(Payout.FAILED, actor="worker")
    assert payout.status == Payout.FAILED


@pytest.mark.django_db
def test_pending_to_completed_illegal(payout):
    with pytest.raises(IllegalStateTransition):
        payout.transition_to(Payout.COMPLETED, actor="worker")


@pytest.mark.django_db
def test_completed_to_pending_illegal(payout):
    payout.transition_to(Payout.PROCESSING, actor="worker")
    payout.transition_to(Payout.COMPLETED, actor="worker")
    with pytest.raises(IllegalStateTransition):
        payout.transition_to(Payout.PENDING, actor="worker")


@pytest.mark.django_db
def test_failed_to_completed_illegal(payout):
    payout.transition_to(Payout.PROCESSING, actor="worker")
    payout.transition_to(Payout.FAILED, actor="worker")
    with pytest.raises(IllegalStateTransition):
        payout.transition_to(Payout.COMPLETED, actor="worker")


@pytest.mark.django_db
def test_processing_to_pending_illegal(payout):
    """The spec says 'anything backwards' is illegal — including PROCESSING -> PENDING."""
    payout.transition_to(Payout.PROCESSING, actor="worker")
    with pytest.raises(IllegalStateTransition):
        payout.transition_to(Payout.PENDING, actor="worker")


@pytest.mark.django_db
def test_each_transition_writes_event(payout):
    payout.transition_to(Payout.PROCESSING, actor="worker", reason="started")
    event = PayoutEvent.objects.filter(payout=payout).latest("created_at")
    assert event.from_status == Payout.PENDING
    assert event.to_status == Payout.PROCESSING
    assert event.actor == "worker"
    assert event.reason == "started"
