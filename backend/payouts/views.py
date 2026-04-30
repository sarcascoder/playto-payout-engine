from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated

from .services import get_balance_summary, create_payout, create_credit_entry
from .serializers import (
    CreatePayoutRequestSerializer, CreateCreditRequestSerializer,
    PayoutSerializer, LedgerEntrySerializer,
)
from .models import Payout, LedgerEntry
from .exceptions import PayoutError


class BalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_balance_summary(request.user))


class PayoutCreateListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Payout.objects.filter(merchant=request.user).order_by("-created_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        limit = min(int(request.query_params.get("limit", 50)), 200)
        return Response(PayoutSerializer(qs[:limit], many=True).data)

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"error": "idempotency_key_required"}, status=400,
            )

        ser = CreatePayoutRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"error": "invalid_amount", "details": ser.errors},
                status=400,
            )

        try:
            payout, replayed = create_payout(
                merchant_id=str(request.user.id),
                amount_paise=ser.validated_data["amount_paise"],
                bank_account_id=str(ser.validated_data["bank_account_id"]),
                idempotency_key=idempotency_key,
                request_body=request.data,
            )
        except PayoutError as e:
            return Response(e.to_dict(), status=e.http_status)

        body = PayoutSerializer(payout).data
        body["idempotent_replay"] = replayed
        return Response(body, status=200 if replayed else 201)


class PayoutDetailView(RetrieveAPIView):
    serializer_class = PayoutSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Payout.objects.filter(merchant=self.request.user)


class LedgerListView(ListAPIView):
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = LedgerEntry.objects.filter(merchant=self.request.user).order_by("-created_at")
        limit = min(int(self.request.query_params.get("limit", 50)), 200)
        return qs[:limit]


class CreditsView(APIView):
    """Demo-only top-up. Writes one CREDIT ledger entry for the caller."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = CreateCreditRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"error": "invalid_amount", "details": ser.errors},
                status=400,
            )
        entry = create_credit_entry(
            merchant=request.user,
            amount_paise=ser.validated_data["amount_paise"],
        )
        return Response(LedgerEntrySerializer(entry).data, status=201)
