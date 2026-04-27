from rest_framework import serializers

from .models import Payout, LedgerEntry


class CreatePayoutRequestSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=1)
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
