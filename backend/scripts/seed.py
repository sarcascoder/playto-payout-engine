"""Seed 3 merchants with bank accounts and credit history.

Run via:  uv run python manage.py shell < scripts/seed.py
"""
from accounts.models import Merchant, BankAccount
from payouts.models import LedgerEntry


def reset():
    LedgerEntry.objects.all().delete()
    BankAccount.objects.all().delete()
    Merchant.objects.filter(is_superuser=False).delete()


def make_merchant(email, name, password, credits_paise, extra_banks=()):
    m = Merchant.objects.create_user(email=email, password=password, name=name)
    BankAccount.objects.create(
        merchant=m,
        account_holder_name=name,
        account_number=f"99{abs(hash(email)) % 10**10:010d}",
        ifsc_code="HDFC0001234",
        is_default=True,
    )
    for ba in extra_banks:
        BankAccount.objects.create(merchant=m, is_default=False, **ba)
    for amount in credits_paise:
        LedgerEntry.objects.create(
            merchant=m, amount_paise=amount,
            entry_type=LedgerEntry.CREDIT,
            category=LedgerEntry.CUSTOMER_PAYMENT,
            description=f"Simulated customer payment ₹{amount/100:.2f}",
        )
    return m


def run():
    # Idempotent: skip if seed already ran. This lets us safely run on every
    # container start in production.
    if Merchant.objects.filter(is_superuser=False).exists():
        print("Merchants already exist; skipping seed.")
        return
    alice = make_merchant(
        "alice@playto.dev", "Alice's Design Studio", "alice-pass-1",
        credits_paise=[500_00, 1200_00, 800_00],   # ₹2500
    )
    bob = make_merchant(
        "bob@playto.dev", "Bob's Dev Agency", "bob-pass-1",
        credits_paise=[5000_00, 3000_00],           # ₹8000
        # Bob has 2 bank accounts to demo the dropdown
        extra_banks=[
            {
                "account_holder_name": "Bob's Dev Agency",
                "account_number": "551122334455",
                "ifsc_code": "ICIC0005678",
            },
        ],
    )
    carol = make_merchant(
        "carol@playto.dev", "Carol's Marketing Co", "carol-pass-1",
        credits_paise=[200_00, 150_00, 350_00, 100_00],  # ₹800
    )
    print(f"Seeded:")
    print(f"  alice@playto.dev / alice-pass-1  -> id={alice.id}")
    print(f"  bob@playto.dev   / bob-pass-1    -> id={bob.id}")
    print(f"  carol@playto.dev / carol-pass-1  -> id={carol.id}")


# Auto-run when exec'd through manage.py shell
run()
