from django.db import transaction

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import BankAccount
from .serializers import MerchantSerializer, BankAccountSerializer


class MeView(generics.RetrieveAPIView):
    serializer_class = MerchantSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class BankAccountListCreateView(generics.ListCreateAPIView):
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            BankAccount.objects
            .filter(merchant=self.request.user)
            .order_by("-is_default", "created_at")
        )

    def perform_create(self, serializer):
        # If the new account is_default=True, demote any existing defaults
        # for this merchant atomically. is_default isn't required, defaults to False.
        with transaction.atomic():
            new_is_default = serializer.validated_data.get("is_default", False)
            if new_is_default:
                BankAccount.objects.filter(
                    merchant=self.request.user, is_default=True,
                ).update(is_default=False)
            serializer.save(merchant=self.request.user)


class BankAccountDeleteView(generics.DestroyAPIView):
    """Delete a bank account. Refuses if the bank still has live payouts."""
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BankAccount.objects.filter(merchant=self.request.user)
