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
