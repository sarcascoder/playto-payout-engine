# Add Credits ("Top-Up") Feature — Design

**Date:** 2026-04-30
**Author:** Anupam (with Claude)
**Status:** Approved, ready for implementation plan

## Why

The dashboard demo flow currently has a one-way drain: seeded balance → payouts → balance hits zero → demo is over. To verify the end-to-end pipeline (concurrency lock, idempotency, overdraw rejection, payout state machine, watchdog) on the deployed app, the reviewer or owner needs to refill a merchant's balance without a database reset. This feature adds a small "Top up" form near the balance card so the dashboard can be demoed in a loop: drain → refill → drain again.

## Scope

In-scope:
- New backend endpoint that appends a CREDIT ledger entry for the authenticated merchant.
- Small frontend form embedded inside the existing `BalanceCard`.
- React-Query invalidation so every dependent panel refreshes after a top-up.
- One backend test file covering validation and balance effect.

Out-of-scope:
- Idempotency-key handling on credits (demo-only feature; keeping it simple).
- Frontend test runner setup (no JS test framework exists in this repo yet).
- Admin UI changes.
- New ledger category — we reuse the existing `CUSTOMER_PAYMENT` category, which already represents "simulated incoming payment" and matches what `seed.py` does.

## UX

A small form sits inside the existing `BalanceCard` on the right (numbers stay on the left). On `md+` screens the card becomes a two-column grid; on mobile the form stacks beneath the balance.

```
┌─ Available balance ─────────────── updated 14:32 ─┐
│  ₹2,500                              ┌─ Top up ─┐ │
│                                      │ ₹  5000  │ │
│  In flight       Total               │ [Add]    │ │
│  ₹0              ₹2,500              │ 1k 5k 10k│ │
└─────────────────────────────────────────────────────┘
```

- Input: rupee amount (integer rupees, internally converted to paise).
- Below the input: three preset chips — `₹1,000`, `₹5,000`, `₹10,000` — that fill the input on click. Pure speed-up for repeated demo runs.
- Button: `Add`. Becomes `Adding…` and disables itself during the request.
- Error: a red dot + message below the button (same pattern as `LoginPage`'s "Invalid credentials" footer).
- After success: form clears, balance card and ledger activity refresh automatically.

## Backend

### Endpoint
```
POST /api/v1/credits
Headers: Authorization: Bearer <jwt>
Body:    { "amount_paise": int }
```

### Validation
- `amount_paise` is required, integer, `100 ≤ amount_paise ≤ 100_00_000` (₹1 to ₹1,00,000 per call).
- On invalid: `400` with `{ "error": "invalid_amount", "details": {...} }` (mirrors `PayoutCreateListView` error shape).

### Effect
Creates one `LedgerEntry`:
- `merchant = request.user`
- `amount_paise = <validated>`
- `entry_type = LedgerEntry.CREDIT`
- `category = LedgerEntry.CUSTOMER_PAYMENT` (reused — fits the simulated-payment framing already in `seed.py`)
- `description = f"Demo top-up: ₹{amount_paise/100:.2f}"`

Wrapped in a single `transaction.atomic()` block — though the operation is one INSERT, keeping the pattern matches the rest of the codebase.

### Response
`201` with the new entry serialized via the existing `LedgerEntrySerializer`. No new serializer needed for the response.

### Files
- `backend/payouts/views.py` — add `CreditsView(APIView)` next to the existing payout views.
- `backend/payouts/serializers.py` — add `CreateCreditRequestSerializer` (mirrors `CreatePayoutRequestSerializer`'s shape).
- `backend/payouts/urls.py` — register `path("credits", views.CreditsView.as_view(), name="credits")`.

### Tests
- New file `backend/tests/test_credits.py`:
  - `test_credit_below_minimum_rejected` — 50 paise → 400.
  - `test_credit_above_maximum_rejected` — 100_00_001 paise → 400.
  - `test_credit_valid_creates_ledger_and_increases_balance` — POST 5000_00, assert ledger row exists, assert `get_balance_summary()` reflects the new available.
  - `test_credit_requires_auth` — anonymous → 401.

## Frontend

### Hook
`frontend/src/hooks/useBalance.ts` — add a `useTopUp` mutation:
- POST `/credits` with `{ amount_paise }`.
- On success, invalidates `['balance']` and `['ledger']` query keys.

### Component
`frontend/src/components/TopUpForm.tsx` (new):
- Controlled input (rupee amount, integer).
- Three preset chip buttons.
- Submit button with loading + error states.
- Calls `useTopUp().mutate({ amount_paise: rupees * 100 })`.

### Wiring
- `BalanceCard.tsx` — restructure into a 2-column grid on `md+` (existing content left, `<TopUpForm />` right). Mobile collapses to stacked.
- No other component edits needed: query-key invalidation handles the cascade.

### Cascading refresh ("wire it everywhere")
On a successful top-up, react-query invalidates `['balance']` and `['ledger']`. Effects:
- `BalanceCard` — refetches and shows new available + total.
- `LedgerActivity` — refetches and shows the new CREDIT row at the top.
- `PayoutForm` — its "available" hint refreshes via `useBalance`.
- `DemoPanel` — its `available <= 0` gate on the Concurrency button releases.

No manual prop drilling; every consumer of these query keys will pick up the change.

## Error handling

| Case | Behaviour |
|------|-----------|
| Empty / non-numeric input | Submit button disabled; no request fired |
| Below ₹1 or above ₹1,00,000 | Backend returns 400; component shows the error message |
| Network failure | Component shows generic "Could not add credit. Try again." |
| Expired JWT (401) | Existing `client.ts` interceptor redirects to `/login` |

## Risk

- **Endpoint left enabled in production:** Acceptable. This project is a demo/take-home; the value-add of being able to refill mid-demo outweighs the abuse surface. If this becomes a real product, gate the endpoint behind a feature flag or a `DEBUG`/staging-only check.
- **No idempotency key:** A duplicate POST credits twice. For a demo-only refill this is a no-op concern; for a real "deposit" endpoint we would mirror the payouts idempotency pattern.

## Build sequence

1. Backend serializer + view + URL.
2. Backend tests.
3. Frontend hook.
4. Frontend `TopUpForm` component.
5. `BalanceCard` layout update embedding `TopUpForm`.
6. Manual end-to-end check on local + redeploy.
