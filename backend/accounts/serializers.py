import re

from rest_framework import serializers

from .models import Merchant, BankAccount


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ("id", "email", "name", "created_at")


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = (
            "id", "account_holder_name", "account_number",
            "ifsc_code", "is_default", "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate_ifsc_code(self, value: str) -> str:
        # Indian IFSC format: 4 letters + 0 + 6 alphanumeric.
        upper = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", upper):
            raise serializers.ValidationError(
                "IFSC must be 4 letters + '0' + 6 alphanumeric (e.g. HDFC0001234)."
            )
        return upper

    def validate_account_number(self, value: str) -> str:
        cleaned = value.strip().replace(" ", "")
        if not cleaned.isdigit() or not (6 <= len(cleaned) <= 20):
            raise serializers.ValidationError(
                "Account number must be 6-20 digits."
            )
        return cleaned

    def validate_account_holder_name(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Holder name too short.")
        return cleaned
