from django.contrib import admin

from .models import LedgerEntry, Payout, IdempotencyKey, PayoutEvent


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("merchant", "entry_type", "category", "amount_paise", "created_at")
    list_filter = ("entry_type", "category")
    readonly_fields = [f.name for f in LedgerEntry._meta.fields]


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "merchant", "amount_paise", "status", "attempts", "created_at")
    list_filter = ("status",)


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("key", "merchant", "response_status", "created_at", "expires_at")


@admin.register(PayoutEvent)
class PayoutEventAdmin(admin.ModelAdmin):
    list_display = ("payout", "from_status", "to_status", "actor", "created_at")
