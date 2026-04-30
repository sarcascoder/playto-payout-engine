from django.urls import path

from . import views

urlpatterns = [
    path("balance", views.BalanceView.as_view(), name="balance"),
    path("payouts", views.PayoutCreateListView.as_view(), name="payouts"),
    path("payouts/<uuid:pk>", views.PayoutDetailView.as_view(), name="payout-detail"),
    path("ledger", views.LedgerListView.as_view(), name="ledger"),
    path("credits", views.CreditsView.as_view(), name="credits"),
]
