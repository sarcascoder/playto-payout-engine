from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import BankAccount
from .serializers import MerchantSerializer, BankAccountSerializer


class MeView(generics.RetrieveAPIView):
    serializer_class = MerchantSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class BankAccountListView(generics.ListAPIView):
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            BankAccount.objects
            .filter(merchant=self.request.user)
            .order_by("-is_default", "created_at")
        )
