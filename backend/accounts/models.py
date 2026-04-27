import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import MerchantManager


class Merchant(AbstractBaseUser, PermissionsMixin):
    """The user model. Each Merchant has a balance derived from their LedgerEntries."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = MerchantManager()

    class Meta:
        db_table = "merchants"

    def __str__(self):
        return f"{self.name} <{self.email}>"


class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name="bank_accounts"
    )
    account_holder_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=40)
    ifsc_code = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "bank_accounts"
        indexes = [models.Index(fields=["merchant", "is_default"])]

    def __str__(self):
        last4 = self.account_number[-4:] if len(self.account_number) >= 4 else self.account_number
        return f"{self.account_holder_name} — {self.ifsc_code}/****{last4}"
