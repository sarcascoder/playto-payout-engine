from rest_framework import serializers

from .models import Payout, LedgerEntry


class CreatePayoutRequestSerializer(serializers.Serializer):
    # Cap well below Postgres BigInt max (9.2e18) — protects the LedgerEntry
    # write from OverflowError if a balance somehow accumulates that high.
    # 10^15 paise = ₹10 trillion, more than any legitimate payout will ever be.
    amount_paise = serializers.IntegerField(min_value=1, max_value=10**15)
    bank_account_id = serializers.UUIDField()


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = (
            "id", "amount_paise", "status", "bank_account_id",
            "attempts", "last_error", "created_at", "updated_at",
        )


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = (
            "id", "amount_paise", "entry_type", "category",
            "payout_id", "description", "created_at",
        )
