from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

urlpatterns = [
    path("auth/login", TokenObtainPairView.as_view(), name="login"),
    path("auth/refresh", TokenRefreshView.as_view(), name="refresh"),
    path("me", views.MeView.as_view(), name="me"),
    path("bank-accounts", views.BankAccountListCreateView.as_view(), name="bank-accounts"),
    path("bank-accounts/<uuid:pk>", views.BankAccountDeleteView.as_view(), name="bank-account-detail"),
]
