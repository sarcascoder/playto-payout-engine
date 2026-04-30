# Add Credits ("Top-Up") Feature — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow an authenticated merchant to credit their own balance from the dashboard so the demo loop (drain → refill → demo again) works end-to-end on the deployed app.

**Architecture:** Add a `POST /api/v1/credits` endpoint backed by a service function `create_credit_entry()` that writes one CREDIT `LedgerEntry` (category `CUSTOMER_PAYMENT`) under a per-merchant row lock — preserving the existing "every ledger write holds the merchant lock" invariant. On the frontend, a small `TopUpForm` lives inside `BalanceCard`; on success it invalidates `['balance']` and `['ledger']` so every dependent panel refreshes.

**Tech Stack:** Django + DRF + simplejwt (backend), pytest + pytest-django (tests), React + TanStack Query + axios (frontend), Vite + Tailwind.

---

## File Map

**Created:**
- `backend/tests/test_credits.py` — pytest module covering service + view.
- `frontend/src/components/TopUpForm.tsx` — small form component.

**Modified:**
- `backend/payouts/services.py` — add `create_credit_entry()` near the top of the file, beneath the balance helpers.
- `backend/payouts/serializers.py` — add `CreateCreditRequestSerializer`.
- `backend/payouts/views.py` — add `CreditsView`.
- `backend/payouts/urls.py` — register `path("credits", ...)`.
- `frontend/src/hooks/useBalance.ts` — add `useTopUp` mutation hook.
- `frontend/src/components/BalanceCard.tsx` — restructure into 2-col grid; embed `<TopUpForm />`.

---

## Task 1: Backend service `create_credit_entry()` + service-level tests

Add the smallest possible service function that writes one CREDIT row under the merchant lock. Mirrors the lock-then-write pattern of `create_payout` so the codebase invariant ("every LedgerEntry write holds the merchant row lock") stays intact.

**Files:**
- Modify: `backend/payouts/services.py` — append after `get_balance_summary()` (~line 67)
- Create: `backend/tests/test_credits.py`

- [ ] **Step 1: Write the failing service tests**

Create `backend/tests/test_credits.py`:

```python
"""Tests for the demo top-up service that credits a merchant's balance."""
import pytest

from payouts.models import LedgerEntry
from payouts.services import (
    _balance_paise, create_credit_entry, MIN_CREDIT_PAISE, MAX_CREDIT_PAISE,
)


@pytest.mark.django_db
def test_create_credit_writes_one_ledger_row(merchant):
    entry = create_credit_entry(merchant=merchant, amount_paise=5000_00)
    assert entry.entry_type == LedgerEntry.CREDIT
    assert entry.category == LedgerEntry.CUSTOMER_PAYMENT
    assert entry.amount_paise == 5000_00
    assert entry.merchant_id == merchant.id
    assert "Demo top-up" in entry.description
    assert LedgerEntry.objects.filter(merchant=merchant).count() == 1


@pytest.mark.django_db
def test_create_credit_increases_balance(merchant):
    assert _balance_paise(merchant) == 0
    create_credit_entry(merchant=merchant, amount_paise=2500_00)
    assert _balance_paise(merchant) == 2500_00
    create_credit_entry(merchant=merchant, amount_paise=1000_00)
    assert _balance_paise(merchant) == 3500_00


@pytest.mark.django_db
def test_create_credit_below_minimum_rejected(merchant):
    with pytest.raises(ValueError, match="amount_paise"):
        create_credit_entry(merchant=merchant, amount_paise=MIN_CREDIT_PAISE - 1)
    assert LedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test_create_credit_above_maximum_rejected(merchant):
    with pytest.raises(ValueError, match="amount_paise"):
        create_credit_entry(merchant=merchant, amount_paise=MAX_CREDIT_PAISE + 1)
    assert LedgerEntry.objects.count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_credits.py -v`
Expected: ImportError — `create_credit_entry`, `MIN_CREDIT_PAISE`, `MAX_CREDIT_PAISE` don't exist yet.

- [ ] **Step 3: Implement the service**

In `backend/payouts/services.py`, append after the `get_balance_summary` function (around line 67, before the `# ── idempotency ──` divider):

```python
# ────────────────────────────── credits ──────────────────────────────

# Demo top-up bounds. Tight upper bound keeps the abuse surface small if
# this endpoint is ever left enabled outside the take-home demo.
MIN_CREDIT_PAISE = 100              # ₹1
MAX_CREDIT_PAISE = 100_00_000       # ₹1,00,000 (1 lakh) per call


def create_credit_entry(*, merchant: Merchant, amount_paise: int) -> LedgerEntry:
    """Write one CREDIT LedgerEntry for a merchant. Demo top-up only.

    Holds the merchant row lock for symmetry with create_payout — every
    ledger write in this codebase must take the lock so balance reads
    inside the lock see a stable, ordered view.
    """
    if not (MIN_CREDIT_PAISE <= amount_paise <= MAX_CREDIT_PAISE):
        raise ValueError(
            f"amount_paise {amount_paise} outside "
            f"[{MIN_CREDIT_PAISE}, {MAX_CREDIT_PAISE}]"
        )
    with transaction.atomic():
        # Re-fetch under lock to maintain the codebase invariant.
        locked = Merchant.objects.select_for_update().get(id=merchant.id)
        return LedgerEntry.objects.create(
            merchant=locked,
            amount_paise=amount_paise,
            entry_type=LedgerEntry.CREDIT,
            category=LedgerEntry.CUSTOMER_PAYMENT,
            description=f"Demo top-up: ₹{amount_paise / 100:.2f}",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_credits.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/payouts/services.py backend/tests/test_credits.py
git commit -m "feat(credits): add create_credit_entry service for demo top-ups"
```

---

## Task 2: Backend request serializer

A thin DRF serializer that mirrors the bounds in the service so invalid input gets a clean 400 before reaching the service.

**Files:**
- Modify: `backend/payouts/serializers.py:14` — append a new serializer class after `CreatePayoutRequestSerializer`

- [ ] **Step 1: Add the serializer**

Insert after line 11 (after `CreatePayoutRequestSerializer`) in `backend/payouts/serializers.py`:

```python
class CreateCreditRequestSerializer(serializers.Serializer):
    # Bounds match payouts.services.MIN/MAX_CREDIT_PAISE exactly.
    # Repeated here (not imported) because serializers stay declarative.
    amount_paise = serializers.IntegerField(min_value=100, max_value=100_00_000)
```

- [ ] **Step 2: Verify import compiles**

Run: `cd backend && uv run python -c "from payouts.serializers import CreateCreditRequestSerializer; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/payouts/serializers.py
git commit -m "feat(credits): add CreateCreditRequestSerializer"
```

---

## Task 3: Backend view + URL + view-level test

The view validates with the serializer, calls the service, returns the new entry serialized.

**Files:**
- Modify: `backend/payouts/views.py` — add `CreditsView` at end of file
- Modify: `backend/payouts/urls.py` — register the route
- Modify: `backend/tests/test_credits.py` — append API-level tests

- [ ] **Step 1: Write the failing API tests**

Append to `backend/tests/test_credits.py`:

```python
# ──────────── view layer ────────────
from rest_framework.test import APIClient


@pytest.fixture
def authed_client(merchant):
    client = APIClient()
    client.force_authenticate(user=merchant)
    return client


@pytest.mark.django_db
def test_post_credits_creates_entry_and_returns_201(authed_client, merchant):
    resp = authed_client.post("/api/v1/credits", {"amount_paise": 5000_00}, format="json")
    assert resp.status_code == 201
    assert resp.data["amount_paise"] == 5000_00
    assert resp.data["entry_type"] == LedgerEntry.CREDIT
    assert resp.data["category"] == LedgerEntry.CUSTOMER_PAYMENT
    assert _balance_paise(merchant) == 5000_00


@pytest.mark.django_db
def test_post_credits_rejects_below_min(authed_client):
    resp = authed_client.post("/api/v1/credits", {"amount_paise": 50}, format="json")
    assert resp.status_code == 400
    assert resp.data["error"] == "invalid_amount"


@pytest.mark.django_db
def test_post_credits_rejects_above_max(authed_client):
    resp = authed_client.post(
        "/api/v1/credits", {"amount_paise": MAX_CREDIT_PAISE + 1}, format="json",
    )
    assert resp.status_code == 400
    assert resp.data["error"] == "invalid_amount"


@pytest.mark.django_db
def test_post_credits_requires_auth(db):
    anon = APIClient()
    resp = anon.post("/api/v1/credits", {"amount_paise": 5000_00}, format="json")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_credits.py -v`
Expected: 4 new tests fail with 404 (URL not registered) on the POST tests.

- [ ] **Step 3: Implement the view**

Append to `backend/payouts/views.py`:

```python
class CreditsView(APIView):
    """Demo-only top-up. Writes one CREDIT ledger entry for the caller."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .serializers import CreateCreditRequestSerializer
        from .services import create_credit_entry
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
```

- [ ] **Step 4: Register the URL**

In `backend/payouts/urls.py`, add to `urlpatterns`:

```python
    path("credits", views.CreditsView.as_view(), name="credits"),
```

The full file should look like:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("balance", views.BalanceView.as_view(), name="balance"),
    path("payouts", views.PayoutCreateListView.as_view(), name="payouts"),
    path("payouts/<uuid:pk>", views.PayoutDetailView.as_view(), name="payout-detail"),
    path("ledger", views.LedgerListView.as_view(), name="ledger"),
    path("credits", views.CreditsView.as_view(), name="credits"),
]
```

- [ ] **Step 5: Run all tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_credits.py -v`
Expected: 8 passed.

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `cd backend && uv run pytest`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/payouts/views.py backend/payouts/urls.py backend/tests/test_credits.py
git commit -m "feat(credits): POST /api/v1/credits endpoint"
```

---

## Task 4: Frontend `useTopUp` hook

A small mutation hook colocated with `useBalance`. Invalidates `['balance']` and `['ledger']` on success — this is the "wire it everywhere" cascade.

**Files:**
- Modify: `frontend/src/hooks/useBalance.ts`

- [ ] **Step 1: Update the hooks file**

Replace the contents of `frontend/src/hooks/useBalance.ts` with:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BalanceSummary, LedgerEntry } from "../api/types";

export function useBalance() {
  return useQuery<BalanceSummary>({
    queryKey: ["balance"],
    queryFn: async () => (await api.get("/balance")).data,
    refetchInterval: 5000,
  });
}

export function useTopUp() {
  const qc = useQueryClient();
  return useMutation<LedgerEntry, unknown, { amount_paise: number }>({
    mutationFn: async ({ amount_paise }) =>
      (await api.post("/credits", { amount_paise })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["balance"] });
      qc.invalidateQueries({ queryKey: ["ledger"] });
    },
  });
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useBalance.ts
git commit -m "feat(credits): useTopUp hook with balance+ledger invalidation"
```

---

## Task 5: `TopUpForm` component

Small form. Rupee input + three preset chips + submit button. Error message in the same red-pill style used in `LoginPage` and `PayoutForm`.

**Files:**
- Create: `frontend/src/components/TopUpForm.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/TopUpForm.tsx`:

```tsx
import { useState } from "react";
import { useTopUp } from "../hooks/useBalance";

const PRESETS_RUPEES = [1000, 5000, 10000];

export function TopUpForm() {
  const topUp = useTopUp();
  const [rupees, setRupees] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const paise = Math.round(parseFloat(rupees) * 100);
    if (!paise || paise < 100) {
      setError("Enter at least ₹1");
      return;
    }
    if (paise > 100_00_000) {
      setError("Maximum ₹1,00,000 per top-up");
      return;
    }
    try {
      await topUp.mutateAsync({ amount_paise: paise });
      setRupees("");
    } catch (err: any) {
      const data = err?.response?.data;
      if (data?.error === "invalid_amount") {
        setError("Amount out of range");
      } else if (err?.message?.includes("Network")) {
        setError("Network error");
      } else {
        setError(`Request failed (${err?.response?.status ?? "no response"})`);
      }
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="eyebrow">Top up</div>
      <label className="relative flex items-center">
        <span className="absolute left-3 text-[var(--color-ink-muted)] num pointer-events-none">₹</span>
        <input
          type="number"
          step="1"
          min="1"
          className="input num pl-7 w-full"
          placeholder="Amount"
          value={rupees}
          onChange={(e) => setRupees(e.target.value)}
        />
      </label>
      <div className="flex gap-1.5">
        {PRESETS_RUPEES.map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => setRupees(String(r))}
            className="text-[12px] px-2 py-1 border border-[var(--color-line-soft)] rounded hover:bg-[#f0eee8] text-[var(--color-ink-muted)]"
          >
            ₹{r.toLocaleString("en-IN")}
          </button>
        ))}
      </div>
      <button
        className="btn btn-primary w-full"
        disabled={topUp.isPending}
      >
        {topUp.isPending ? "Adding…" : "Add"}
      </button>
      {error && (
        <p className="text-[12px] text-[var(--color-danger)] flex items-center gap-1.5">
          <span className="h-1 w-1 rounded-full bg-[var(--color-danger)]" />
          {error}
        </p>
      )}
    </form>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. (The component isn't imported anywhere yet — that's fine.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TopUpForm.tsx
git commit -m "feat(credits): TopUpForm component"
```

---

## Task 6: Embed `TopUpForm` inside `BalanceCard`

Restructure the BalanceCard into a two-column grid on `md+` (numbers left, top-up right). On mobile it stacks.

**Files:**
- Modify: `frontend/src/components/BalanceCard.tsx`

- [ ] **Step 1: Update BalanceCard**

Replace the contents of `frontend/src/components/BalanceCard.tsx` with:

```tsx
import { useBalance } from "../hooks/useBalance";
import { formatPaiseBare, formatPaise } from "../lib/format";
import { TopUpForm } from "./TopUpForm";

export function BalanceCard() {
  const { data, isLoading } = useBalance();

  if (isLoading || !data) {
    return <div className="card p-8 h-44 animate-pulse" />;
  }

  return (
    <section className="card p-8 rise-in rise-in-delay-1">
      <div className="grid grid-cols-1 md:grid-cols-[1fr_240px] gap-8 md:gap-12">
        {/* Left: numbers */}
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <span className="eyebrow">Available balance</span>
            <span className="text-xs text-[var(--color-ink-muted)] num">
              updated {new Date().toLocaleTimeString()}
            </span>
          </div>

          <div className="flex items-baseline gap-3">
            <span className="display-num text-[var(--color-ink)]">
              ₹{formatPaiseBare(data.available_paise)}
            </span>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-x-12 gap-y-3 max-w-md">
            <SubMetric
              label="In flight"
              value={formatPaise(data.held_paise)}
              accent="text-[var(--color-warning)]"
              hint="held in pending or processing payouts"
            />
            <SubMetric
              label="Total"
              value={formatPaise(data.total_paise)}
              accent="text-[var(--color-ink)]"
              hint="available + in flight"
            />
          </div>
        </div>

        {/* Right: top-up */}
        <div className="md:border-l md:border-[var(--color-line-soft)] md:pl-8">
          <TopUpForm />
        </div>
      </div>
    </section>
  );
}

function SubMetric({
  label, value, accent, hint,
}: {
  label: string;
  value: string;
  accent: string;
  hint?: string;
}) {
  return (
    <div>
      <div className="eyebrow mb-0.5">{label}</div>
      <div className={`text-lg font-medium num ${accent}`}>{value}</div>
      {hint && (
        <div className="text-[11px] text-[var(--color-ink-faint)] mt-0.5">{hint}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BalanceCard.tsx
git commit -m "feat(credits): embed TopUpForm in BalanceCard"
```

---

## Task 7: Manual end-to-end check on local dev

Run frontend + backend locally and walk the demo loop.

- [ ] **Step 1: Start backend**

Run in one terminal: `cd backend && uv run python manage.py runserver 8001`
Expected: server boots, no errors.

- [ ] **Step 2: Start frontend**

Run in another terminal: `cd frontend && npm run dev`
Expected: Vite dev server on port 5173.

- [ ] **Step 3: Walk the demo loop**

Open `http://localhost:5173/login`, sign in as `alice@playto.dev` / `alice-pass-1`.

Verify:
1. **Initial balance** shows ₹2,500.
2. **Drain** the balance — fire the "Concurrency" demo button (drains via 3 successful payouts).
3. **Balance hits low** — the Concurrency button on DemoPanel becomes disabled (its gate is `available > 0`).
4. **Top up ₹5,000** — type `5000` in the new form (or click the chip), hit Add.
   - Balance updates without a page refresh.
   - Ledger Activity shows a new "Demo top-up" CREDIT row at the top.
   - DemoPanel's Concurrency button re-enables.
   - PayoutForm's "available" reflects the new amount.
5. **Re-run a payout** to confirm the round-trip.
6. **Validation:** try `0`, negative, very large (`200000`) — appropriate error messages appear inline.

- [ ] **Step 4: Commit any tweaks (skip if none needed)**

If the manual walkthrough reveals any rough edges, fix them and commit before redeploying.

---

## Task 8: Redeploy to Vercel

Push to git so the deployed app reflects the new feature.

- [ ] **Step 1: Push to origin**

```bash
git push
```

- [ ] **Step 2: Trigger production deploy**

```bash
vercel --prod --yes
```

Expected output: `Production: https://payto-...vercel.app` and `Aliased: https://paytopay-one.vercel.app` with status `READY`.

- [ ] **Step 3: Verify on the live URL**

Open `https://paytopay-one.vercel.app/login`, sign in, top up, drain, top up again. Confirm the loop works end-to-end against Railway.

---

## Cross-cutting verification

After all tasks are done:

- [ ] **Backend tests green:** `cd backend && uv run pytest` → 0 failures.
- [ ] **Frontend typechecks:** `cd frontend && npx tsc --noEmit` → 0 errors.
- [ ] **Frontend builds:** `cd frontend && npm run build` → succeeds.
- [ ] **No `LedgerEntry` invariant violation:** quick grep for new ledger writes outside `services.py` — there should be none introduced by this feature.

```bash
grep -rn "LedgerEntry.objects.create" backend/ --include="*.py"
```

Expected: only the locations we already had (`services.py` × 3, `scripts/seed.py` × 1) plus our new one inside `create_credit_entry`. Total 5 sites, all in `services.py`/`seed.py`.
