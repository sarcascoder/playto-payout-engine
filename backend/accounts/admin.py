from django.contrib import admin

from .models import Merchant, BankAccount


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "is_active", "created_at")
    search_fields = ("email", "name")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("merchant", "account_holder_name", "ifsc_code", "is_default")
    list_filter = ("is_default",)
