from django.db.models import Sum, Case, When, F, IntegerField, Value
from django.db.models.functions import Coalesce

from accounts.models import Merchant
from .models import LedgerEntry, Payout


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
