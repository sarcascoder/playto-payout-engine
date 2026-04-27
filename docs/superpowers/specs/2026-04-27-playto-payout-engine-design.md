# Playto Payout Engine — Design Spec

**Author:** Anupam Tripathi (with Claude as pair)
**Date:** 2026-04-27
**Context:** Founding Engineer take-home challenge for Playto Pay
**Deadline:** 5 days from email receipt (received 2026-04-25)
**Source spec:** Playto Founding Engineer Challenge 2026 (verbatim copy in `docs/challenge.md`)

---

## 1. Goal

Build a minimal version of Playto Pay's **payout engine**: the service that lets Indian merchants withdraw their accumulated USD-collected balance to their Indian bank account. The challenge does not require building the customer-payment-collection side — only the merchant-balance + payout-request + payout-processing pipeline.

## 2. Non-goals (deliberately out of scope)

The challenge rubric is explicit: "We are NOT grading on pixel-perfect UI, perfect test coverage, fancy patterns, feature completeness beyond what is listed." We optimize for the rubric.

| Out of scope | Why |
|---|---|
| Customer payment ingestion flow | Spec says "You do not need to build the customer payment flow." |
| Real bank API integration | Simulated 70% success / 20% fail / 10% hang in worker |
| Webhook delivery | Optional bonus — skip in favor of audit log |
| Event sourcing | Optional bonus — skip; ledger-as-source-of-truth is enough |
| Multi-currency / FX | Single currency (INR paise) per the spec |
| KYC / KYB onboarding | Out of challenge scope |
| Pixel-perfect UI | Rubric explicitly de-prioritizes |
| Test coverage > ~3-4 sharp tests | Rubric explicitly de-prioritizes |
| Sophisticated frontend state management | Polling every 3s is fine |

## 3. Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend framework | Django 5.x + Django REST Framework | Spec requirement |
| Database | PostgreSQL 16 | Spec strongly preferred; we **need** row-level locks |
| Background jobs | Celery 5.x + Redis 7 | Industry standard, matches what CTO will probe |
| Auth | `djangorestframework-simplejwt` (JWT access + refresh) | Django-native, ~30 min setup, no fancy patterns |
| Frontend framework | React 19 + Vite 6 + TypeScript | Anupam knows Vite cold; no SSR needed |
| Frontend styling | TailwindCSS | Spec requirement |
| Frontend state | TanStack Query (React Query) for server state | Built-in polling, caching, retry — perfect for "live status updates" |
| Local dev | docker-compose (postgres + redis + django + celery worker) | Bonus point in rubric; matches Anupam's existing experience |
| Frontend deploy | Vercel | Per Anupam's preference; frontend is static + API calls |
| Backend deploy | Railway | Single project hosts Django web + Celery worker + Postgres + Redis |
| Repo | Public GitHub, conventional commits, linear history | "Clean commit history" in rubric |

### Auth scope decision
Auth is implemented (per Anupam's preference) using `djangorestframework-simplejwt`. The README explicitly notes that Anupam has shipped his own auth library (Warden, Java/Spring Boot) but did not integrate it here because running a JVM service alongside Django would add deploy complexity that is not on the rubric. This frames the choice as a senior judgment call rather than an absence.

## 4. Data Model

```
Merchant ──┬── BankAccount        (where to send money)
           │
           ├── LedgerEntry         (source-of-truth for balance — append-only)
           │
           ├── Payout              (a withdrawal request + its status)
           │     └── LedgerEntry   (debit/reversal entries link back here)
           │     └── PayoutEvent   (audit log of every state transition)
           │
           └── IdempotencyKey      (per-merchant request dedup, 24h TTL)
```

### 4.1 `Merchant` (extends `AbstractBaseUser`)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `email` | unique str | login identifier |
| `name` | str | display name |
| `password` | hashed str | Django-managed |
| `is_active` | bool | |
| `created_at` | timestamp | |

`AUTH_USER_MODEL = 'accounts.Merchant'` in settings.

### 4.2 `BankAccount`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant` | FK → Merchant | |
| `account_holder_name` | str | |
| `account_number` | str | stored plain for spec scope; gap noted in EXPLAINER |
| `ifsc_code` | str | |
| `is_default` | bool | |
| `created_at` | timestamp | |

### 4.3 `LedgerEntry` — heart of the system

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant` | FK → Merchant, indexed | |
| `amount_paise` | **BigIntegerField, CHECK > 0** | sign comes from `entry_type` |
| `entry_type` | enum: `CREDIT` \| `DEBIT` | |
| `category` | enum: `CUSTOMER_PAYMENT` \| `PAYOUT_HOLD` \| `PAYOUT_REVERSAL` | |
| `payout` | FK → Payout, nullable | links debit/reversal to its payout |
| `description` | str | human-readable |
| `created_at` | timestamp, indexed | |

Index on `(merchant_id, created_at)` for fast balance and history queries.

**Append-only.** No UPDATE, no DELETE. Reversals are new CREDIT entries, not modifications.

**Three-category lifecycle:**
- Customer pays → `CREDIT [CUSTOMER_PAYMENT]` → balance ↑
- Merchant withdraws → `DEBIT [PAYOUT_HOLD]` → balance ↓ immediately
- Payout SUCCEEDS → no entry (the hold becomes permanent)
- Payout FAILS → `CREDIT [PAYOUT_REVERSAL]` → balance ↑ back

**Balance formula (always derivable, no cache):**
```
balance_paise = SUM(amount_paise WHERE entry_type=CREDIT)
              − SUM(amount_paise WHERE entry_type=DEBIT)
```

### 4.4 `Payout`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `merchant` | FK | |
| `bank_account` | FK | |
| `amount_paise` | BigInt > 0 | denormalized from ledger |
| `status` | enum: `PENDING` \| `PROCESSING` \| `COMPLETED` \| `FAILED` | with CHECK constraint |
| `idempotency_key` | FK → IdempotencyKey, nullable | one-to-one in practice |
| `attempts` | int, default 0 | retry counter |
| `last_error` | text, nullable | most recent attempt's error |
| `processing_started_at` | timestamp, nullable | watchdog uses this |
| `created_at` / `updated_at` | timestamps | |

### 4.5 `IdempotencyKey`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `key` | UUID, indexed | client-supplied |
| `merchant` | FK | scoping per spec |
| `request_fingerprint` | sha256 hex of request body | catches "same key, different body" |
| `response_status` | int, nullable | filled when request completes (or fails) |
| `response_body` | JSONField, nullable | filled when request completes (or fails) |
| `payout` | FK → Payout, nullable | the payout this request created |
| `created_at` | timestamp | |
| `expires_at` | timestamp | created_at + 24h |

`unique_together = ('key', 'merchant')` — this unique index is the database-level dedup primitive.

A periodic Celery beat task purges rows where `expires_at < now()`.

### 4.6 `PayoutEvent` (audit log)

| Field | Type |
|---|---|
| `id` | UUID PK |
| `payout` | FK → Payout |
| `from_status` | str (empty for creation) |
| `to_status` | str |
| `actor` | str (e.g., `api`, `worker:process_payout`, `watchdog`) |
| `reason` | str |
| `created_at` | timestamp |

Every legal state transition writes a row here.

## 5. API Surface

All routes prefixed `/api/v1`. JWT required on everything except `/auth/*`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login` | email + password → access + refresh JWT |
| POST | `/auth/refresh` | refresh token → new access token |
| GET | `/me` | current merchant info |
| GET | `/balance` | `{ available_paise, held_paise, total_paise }` (see semantics below) |
| GET | `/ledger?limit=50&cursor=` | paginated ledger entries |
| GET | `/bank-accounts` | merchant's bank accounts |
| POST | `/payouts` | create payout (Idempotency-Key header required) |
| GET | `/payouts?status=&limit=` | list payouts |
| GET | `/payouts/<id>` | single payout (frontend polls this) |

### `GET /api/v1/balance` — balance semantics

```json
{
  "available_paise": 4000,   // ledger sum: SUM(CREDIT) - SUM(DEBIT)
  "held_paise": 6000,         // SUM(payout.amount_paise) WHERE status IN (pending, processing)
  "total_paise": 10000        // available + held (informational only)
}
```

Because we DEBIT the ledger when a payout is requested (the `PAYOUT_HOLD` entry), `available_paise` already reflects the post-hold balance. `held_paise` is a separate display-only count of in-flight payouts. They sum to the user's "I haven't lost this money yet" total.

### `POST /api/v1/payouts` — full contract

**Headers**
```
Authorization: Bearer <access_token>
Idempotency-Key: <uuid>
Content-Type: application/json
```

**Body**
```json
{ "amount_paise": 6000, "bank_account_id": "<uuid>" }
```

**Success (first time) — 201 Created**
```json
{
  "id": "<payout-uuid>",
  "amount_paise": 6000,
  "status": "pending",
  "bank_account_id": "<uuid>",
  "attempts": 0,
  "created_at": "2026-04-27T10:00:00Z",
  "idempotent_replay": false
}
```

**Idempotent replay — 200 OK**
Same body as above with `"idempotent_replay": true`.

**Errors**

| HTTP | When | Body |
|---|---|---|
| 400 | missing `Idempotency-Key` header | `{"error": "idempotency_key_required"}` |
| 400 | `amount_paise <= 0` | `{"error": "invalid_amount"}` |
| 401 | bad/missing JWT | DRF default |
| 404 | `bank_account_id` not owned | `{"error": "bank_account_not_found"}` |
| 409 | same key, **different body** | `{"error": "idempotency_key_mismatch"}` |
| 409 | same key, **request still in flight** | `{"error": "idempotency_key_in_progress"}` |
| 422 | insufficient balance | `{"error": "insufficient_balance", "available_paise": 4000, "requested_paise": 6000}` |

`422` (not `400`) for insufficient balance — the request was valid but business-rule rejected. Stripe convention.

## 6. The Concurrency Keystone

This is the most rubric-relevant piece. Quoted in full because the EXPLAINER will paste it verbatim.

```python
# payouts/services.py
from django.db import transaction, IntegrityError
from django.db.models import Sum, Case, When, F, IntegerField, Value
from django.db.models.functions import Coalesce

from accounts.models import Merchant, BankAccount
from .models import Payout, LedgerEntry, IdempotencyKey, PayoutEvent
from .exceptions import (
    InsufficientBalance, IdempotencyKeyMismatch,
    IdempotencyKeyInFlight, BankAccountNotFound,
)
import hashlib, json


def _fingerprint(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _balance_paise(merchant: Merchant) -> int:
    """Source-of-truth balance: SUM(credits) - SUM(debits) in paise.
    Computed entirely in the database — no Python-side arithmetic on rows."""
    agg = LedgerEntry.objects.filter(merchant=merchant).aggregate(
        balance=Coalesce(
            Sum(Case(
                When(entry_type=LedgerEntry.CREDIT, then=F("amount_paise")),
                When(entry_type=LedgerEntry.DEBIT,  then=-F("amount_paise")),
                output_field=IntegerField(),
            )),
            Value(0),
        )
    )
    return int(agg["balance"])


def create_payout(*, merchant_id, amount_paise, bank_account_id,
                  idempotency_key, request_body) -> tuple[Payout, bool]:
    """Returns (payout, was_idempotent_replay)."""
    fp = _fingerprint(request_body)

    # ── Phase 1: claim the idempotency key (its own short transaction) ──
    try:
        with transaction.atomic():
            idem = IdempotencyKey.objects.create(
                key=idempotency_key,
                merchant_id=merchant_id,
                request_fingerprint=fp,
            )
        is_first_request = True
    except IntegrityError:
        idem = IdempotencyKey.objects.get(
            key=idempotency_key, merchant_id=merchant_id
        )
        is_first_request = False

    if not is_first_request:
        if idem.request_fingerprint != fp:
            raise IdempotencyKeyMismatch()
        if idem.response_status is None:
            raise IdempotencyKeyInFlight()
        return idem.payout, True

    # ── Phase 2: the money-moving transaction ──
    try:
        with transaction.atomic():
            # 2a. ROW LOCK on the merchant. Every operation that reads
            #     balance and writes to the ledger MUST hold this lock first.
            merchant = (
                Merchant.objects
                .select_for_update()        # SQL: SELECT ... FOR UPDATE
                .get(id=merchant_id)
            )

            # 2b. Validate inputs INSIDE the lock (TOCTOU-safe).
            try:
                bank = BankAccount.objects.get(
                    id=bank_account_id, merchant=merchant
                )
            except BankAccount.DoesNotExist:
                raise BankAccountNotFound()

            # 2c. Compute available balance INSIDE the lock.
            available = _balance_paise(merchant)
            if available < amount_paise:
                raise InsufficientBalance(
                    available=available, requested=amount_paise
                )

            # 2d. Create the payout in PENDING.
            payout = Payout.objects.create(
                merchant=merchant,
                bank_account=bank,
                amount_paise=amount_paise,
                status=Payout.PENDING,
                idempotency_key=idem,
            )

            # 2e. Write the DEBIT_HOLD entry. Balance has now dropped.
            LedgerEntry.objects.create(
                merchant=merchant,
                amount_paise=amount_paise,
                entry_type=LedgerEntry.DEBIT,
                category=LedgerEntry.PAYOUT_HOLD,
                payout=payout,
                description=f"Hold for payout {payout.id}",
            )

            PayoutEvent.objects.create(
                payout=payout, from_status="", to_status=Payout.PENDING,
                actor="api", reason="payout_requested",
            )

            # 2f. Backfill the idempotency row with the success response.
            idem.payout = payout
            idem.response_status = 201
            idem.response_body = {
                "id": str(payout.id),
                "amount_paise": amount_paise,
                "status": Payout.PENDING,
                "bank_account_id": str(bank.id),
                "created_at": payout.created_at.isoformat(),
            }
            idem.save(update_fields=["payout", "response_status", "response_body"])

            # 2g. Enqueue the worker AFTER the transaction commits.
            #     transaction.on_commit fires the lambda only if commit succeeds —
            #     so the worker never sees a payout that doesn't exist in the DB.
            transaction.on_commit(
                lambda: attempt_payout.delay(str(payout.id))
            )

        return payout, False

    except (InsufficientBalance, BankAccountNotFound) as e:
        # Persist the error response on the idem row IN ITS OWN transaction
        # so future retries with the same key get the same 422/404.
        with transaction.atomic():
            idem.response_status = e.http_status
            idem.response_body = e.to_dict()
            idem.save(update_fields=["response_status", "response_body"])
        raise
```

### 6.1 Why each primitive is needed

**`select_for_update()`** compiles to `SELECT ... FOR UPDATE`. Postgres holds a row-level write lock until the transaction commits or rolls back. Other transactions hitting the same row block; plain reads (MVCC) are not blocked. Released atomically with the transaction.

**Must be inside `transaction.atomic()`** — outside a transaction Django autocommits, the lock is released the instant SELECT returns. Newer Django raises `TransactionManagementError`; we don't rely on that and always use the atomic block explicitly.

**Lock granularity = Merchant row** because:
- Different merchants don't contend (full parallelism across merchants).
- A single merchant's payouts are inherently serial (one balance, one writer at a time).
- Always locking exactly one row in a known order = zero deadlock risk.

### 6.2 The invariant

> **Every code path that INSERTs into `LedgerEntry` MUST first do `Merchant.objects.select_for_update().get(id=...)` inside the same `transaction.atomic` block.**

This applies to: `create_payout`, the worker's reversal write on failure (`mark_payout_failed`), the watchdog's reversal write on max-retries (`reap_stuck_payouts`), the seed script, and any future ledger writer.

We document and code-review-enforce this invariant rather than building runtime assertions — the cost of accidentally bypassing it is loud (the concurrency test fails immediately) and the codebase is small enough that all four call sites are visible.

### 6.3 Two-phase idempotency rationale

Idempotency is in its **own transaction** before the money-moving transaction because:

1. The unique index on `(key, merchant_id)` is the dedup primitive. Two same-key requests racing? Both INSERT, exactly one wins, the loser catches `IntegrityError` and reads the winner's row. No "check then create" TOCTOU.
2. Failure responses must persist. If the first request gets `insufficient_balance` (422), the retry must get the same 422 — not a fresh attempt. So the idem row commits even when business logic fails. Stripe behaves this way.
3. In-flight detection — second request arriving mid-first sees `response_status IS NULL` and returns 409.

## 7. State Machine

The challenge spec is strict: legal transitions are exactly `pending → processing → completed` OR `pending → processing → failed`. **"Anything backwards" is illegal**, including `processing → pending`. Our retry design must respect this.

```python
# payouts/models.py
class Payout(models.Model):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    STATUSES = [PENDING, PROCESSING, COMPLETED, FAILED]

    LEGAL_TRANSITIONS = {
        PENDING:    {PROCESSING},
        PROCESSING: {COMPLETED, FAILED},
        COMPLETED:  set(),    # terminal
        FAILED:     set(),    # terminal
    }

    def transition_to(self, new_status, *, actor, reason=""):
        """The ONLY way to change Payout.status. Caller must hold the row lock."""
        legal = self.LEGAL_TRANSITIONS.get(self.status, set())
        if new_status not in legal:
            raise IllegalStateTransition(
                f"{self.status} → {new_status} is not allowed "
                f"(legal: {sorted(legal) or 'none — terminal state'})"
            )
        old_status = self.status
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        PayoutEvent.objects.create(
            payout=self, from_status=old_status, to_status=new_status,
            actor=actor, reason=reason,
        )
```

Plus a Postgres CHECK constraint that `status IN ('pending','processing','completed','failed')` via `models.CheckConstraint` so even raw SQL can't insert garbage.

**Retry strategy without breaking the state machine:** retries do NOT transition the payout back to `PENDING`. The payout stays `PROCESSING` across all retry attempts. The worker task accepts both `PENDING` (first attempt) and `PROCESSING` (retry) as valid entry states, transitioning to `PROCESSING` only on the first call. See §8 for the worker code.

## 8. Worker / Retry / Watchdog

### 8.1 `attempt_payout(payout_id)` — the main worker task

Accepts both `PENDING` (first attempt, enqueued by `create_payout`) and `PROCESSING` (retry, enqueued by `reap_stuck_payouts`). On first call it transitions to `PROCESSING`; on retries it stays in `PROCESSING`. Either way it bumps `attempts` and resets `processing_started_at`.

```python
@shared_task(bind=True)
def attempt_payout(self, payout_id):
    with transaction.atomic():
        p = Payout.objects.select_for_update().get(id=payout_id)
        if p.status not in (Payout.PENDING, Payout.PROCESSING):
            return  # already terminal; safe no-op
        if p.status == Payout.PENDING:
            p.transition_to(Payout.PROCESSING, actor="worker")
        p.attempts += 1
        p.processing_started_at = timezone.now()
        p.save(update_fields=["attempts", "processing_started_at"])

    # Simulate bank call OUTSIDE the transaction (no locks held during sleep)
    outcome = simulate_bank()  # returns "success" / "fail" / "hang"

    if outcome == "success":
        with transaction.atomic():
            p = Payout.objects.select_for_update().get(id=payout_id)
            if p.status == Payout.PROCESSING:
                p.transition_to(Payout.COMPLETED, actor="worker", reason="bank_settled")
    elif outcome == "fail":
        mark_payout_failed(payout_id, reason="bank_rejected")
    else:  # "hang" — return without transitioning; watchdog will retry
        return
```

### 8.2 `mark_payout_failed` — atomic state + reversal

```python
def mark_payout_failed(payout_id, reason):
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        merchant = Merchant.objects.select_for_update().get(id=payout.merchant_id)
        payout.transition_to(Payout.FAILED, actor="worker", reason=reason)
        LedgerEntry.objects.create(
            merchant=merchant,
            amount_paise=payout.amount_paise,
            entry_type=LedgerEntry.CREDIT,
            category=LedgerEntry.PAYOUT_REVERSAL,
            payout=payout,
            description=f"Reversal for failed payout {payout.id}",
        )
```

State transition and reversal commit together — there is never a window where the payout is FAILED but the funds have not returned.

### 8.3 `reap_stuck_payouts` — Celery beat task, every 10s

```python
@shared_task
def reap_stuck_payouts():
    cutoff = timezone.now() - timedelta(seconds=30)
    stuck_ids = list(Payout.objects.filter(
        status=Payout.PROCESSING,
        processing_started_at__lt=cutoff,
    ).values_list("id", flat=True))

    for pid in stuck_ids:
        with transaction.atomic():
            p = Payout.objects.select_for_update().get(id=pid)
            if p.status != Payout.PROCESSING:
                continue
            if p.attempts >= 3:
                # Max retries — fail and reverse atomically (no state rollback)
                merchant = Merchant.objects.select_for_update().get(id=p.merchant_id)
                p.transition_to(Payout.FAILED, actor="watchdog", reason="max_retries_exceeded")
                LedgerEntry.objects.create(
                    merchant=merchant, amount_paise=p.amount_paise,
                    entry_type=LedgerEntry.CREDIT,
                    category=LedgerEntry.PAYOUT_REVERSAL,
                    payout=p, description="Reversal: max retries exceeded",
                )
            else:
                # Re-enqueue retry. Payout STAYS in PROCESSING — no backwards
                # transition. attempt_payout accepts PROCESSING as a valid entry.
                # processing_started_at gets reset by attempt_payout on each call.
                transaction.on_commit(
                    lambda pid=pid, attempts=p.attempts: attempt_payout.apply_async(
                        args=[pid], countdown=2 ** attempts,
                    )
                )
```

The retry never violates the strict state machine — `PROCESSING → PENDING` is not legal and not used. The payout simply stays in `PROCESSING` across retry attempts; only the bookkeeping (`attempts`, `processing_started_at`) changes.

## 9. Frontend

Single-page React + Vite + Tailwind. Three sections on one screen:

1. **Balance card** — shows available paise (formatted as ₹) + held paise. Polled every 5s.
2. **Request payout form** — amount input, bank account dropdown, submit button. Generates a UUID for the `Idempotency-Key` header on submit. Shows inline error on 4xx.
3. **Payout history table** — list of payouts with status badge. Polled every 3s. Status badge color-codes (gray=pending, blue=processing, green=completed, red=failed).

State managed via TanStack Query with `refetchInterval`. JWT stored in localStorage (acceptable for the demo; gap noted in EXPLAINER).

## 10. Testing

Per rubric: "at least 2 meaningful tests, one for concurrency and one for idempotency." We will write both as integration tests using `pytest-django` + Postgres test DB.

### 10.1 Concurrency test

Spin up two threads (or two `transaction.atomic` blocks) attempting payouts that would together overdraw a merchant. Assert exactly one succeeds (`Payout` exists in PENDING) and one raises `InsufficientBalance`. Use `threading.Barrier` to maximize the race window.

### 10.2 Idempotency test

Make the same `POST /api/v1/payouts` call twice with the same `Idempotency-Key`. Assert:
- Both responses have the same payout ID and body.
- Only one `Payout` row in the database.
- Second response has `idempotent_replay: true`.

### 10.3 Bonus tests (if time permits)

- Illegal state transition raises (`completed → pending`, etc.).
- Watchdog reverses funds after max retries.
- Balance invariant: `SUM(credits) − SUM(debits) == derived balance` after a sequence of operations.

## 11. Project layout

```
payto-payout-engine/
├── README.md
├── EXPLAINER.md
├── docker-compose.yml
├── railway.toml             # backend deploy config (Railway)
├── vercel.json              # frontend deploy config (Vercel)
├── backend/
│   ├── manage.py
│   ├── pyproject.toml
│   ├── config/
│   │   ├── settings.py
│   │   ├── celery.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── accounts/
│   │   ├── models.py        # Merchant, BankAccount
│   │   ├── serializers.py
│   │   ├── views.py         # /me, /balance, /bank-accounts, auth
│   │   └── urls.py
│   ├── payouts/
│   │   ├── models.py        # LedgerEntry, Payout, IdempotencyKey, PayoutEvent
│   │   ├── services.py      # create_payout, mark_payout_failed
│   │   ├── tasks.py         # attempt_payout, reap_stuck_payouts, purge_expired_idempotency
│   │   ├── serializers.py
│   │   ├── views.py         # /payouts, /ledger
│   │   ├── exceptions.py
│   │   ├── simulator.py     # simulate_bank()
│   │   └── urls.py
│   ├── tests/
│   │   ├── test_concurrency.py
│   │   ├── test_idempotency.py
│   │   └── test_state_machine.py
│   └── scripts/
│       └── seed.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── api/client.ts
    │   ├── components/
    │   │   ├── BalanceCard.tsx
    │   │   ├── PayoutForm.tsx
    │   │   └── PayoutHistory.tsx
    │   └── pages/
    │       ├── LoginPage.tsx
    │       └── DashboardPage.tsx
    └── index.html
```

## 12. Five-day execution shape

| Day | Theme | Outputs |
|---|---|---|
| **D1** | Setup + Ledger keystone | Repo, docker-compose, Django+DRF+Postgres+Redis bootstrapped. Migrations for Merchant, BankAccount, LedgerEntry. Seed script (2-3 merchants, credit history). Balance query verified. |
| **D2** | Lock + Payout API | Payout + IdempotencyKey models. `create_payout` service with full keystone code. `POST /payouts` view. Concurrency test green. Idempotency test green. |
| **D3** | Worker + Retry | Celery + Redis wired. `process_payout`, `mark_payout_failed`, `reap_stuck_payouts`. Bank simulator. State machine with audit log. State-machine test green. |
| **D4** | Dashboard + Deploy | React+Vite+Tailwind frontend (3 components). JWT login flow. Deploy backend to Railway, frontend to Vercel. Smoke-test end-to-end on prod. |
| **D5** | EXPLAINER + polish + buffer | Write EXPLAINER.md (most drafted from build notes). Honest AI audit (real moments captured). README polish. Submit. |

Day 5 is buffer. If the deploy or worker setup blows up on D3/D4, we eat into D5. If everything goes smooth, D5 covers polish + the audit log bonus.

## 13. EXPLAINER.md outline

| Section | Source |
|---|---|
| 1. The Ledger | `_balance_paise()` query + the three-category lifecycle from §4.3 |
| 2. The Lock | `create_payout()` lines 2a-2c + §6.1 explanation of `SELECT ... FOR UPDATE` |
| 3. The Idempotency | Two-phase pattern from §6.3 + the `(key, merchant)` unique index |
| 4. The State Machine | `LEGAL_TRANSITIONS` map + `transition_to()` from §7 |
| 5. The AI Audit | Real moments captured during build (running notes in `docs/ai-audit-notes.md`) |

The AI audit will be authentic, not fabricated. As we build, we'll save real moments where Claude/Cursor/Copilot suggested subtly wrong code and Anupam caught it. Common candidates:
- `F('balance') - amount` for atomic deduct without first acquiring lock → can go negative
- `update_or_create` for idempotency → race between get and create
- `select_for_update` outside `transaction.atomic` → silent no-op
- `Sum` over filtered queryset without `Coalesce(..., 0)` → returns None on empty result, breaks downstream comparison
- Suggesting Decimal for money instead of paise-as-int

## 14. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Railway free tier insufficient for Django+Celery+Postgres+Redis | Medium | Render or Fly.io as fallback; we test deploy on D4 morning |
| Celery + Redis configuration eats half a day | Medium | Use a known-good `celery.py` template; test locally on D3 morning |
| `select_for_update` deadlocks under test | Low | Always lock Merchant first, single row, known order — no deadlock surface |
| Postgres test DB setup friction | Low | Use `pytest-django` with `--reuse-db` and a docker-compose Postgres service |
| Frontend takes longer than budgeted | Medium | Keep UI to one screen, three components, no fancy animations |

## 15. CTO Interview Question Bank

The CTO call is **45 minutes** and follows the EXPLAINER. Every question below derives from a decision in this spec. **Likelihood markers:** 🔴 = very likely, 🟡 = likely, ⚪ = possible-but-deeper.

Practice these out loud. The goal is not memorization — it's that every answer feels obvious because you understand the *why*.

---

### 15.1 Concurrency & The Lock (the most-probed area)

**🔴 Q1. What database primitive does your lock rely on?**
Postgres row-level write locks via `SELECT ... FOR UPDATE`, scoped to the Merchant row. Held until the surrounding `transaction.atomic` block commits or rolls back.

**🔴 Q2. Walk me through what happens when two `POST /payouts` requests arrive simultaneously for the same merchant with a 100-rupee balance, both asking for 60.**
Both requests hit the keystone. Phase 1: each tries to INSERT its own (different) idempotency key — no contention there. Phase 2: both call `Merchant.objects.select_for_update().get(id=...)`. Postgres grants the row lock to whichever request's transaction reaches the SQL first; the other connection blocks. The winner reads balance = 100, writes a DEBIT_HOLD of 60, commits. Lock releases. Loser's connection unblocks, reads balance = 40 (the new value, because we re-read inside the lock), 40 < 60, raises `InsufficientBalance` → 422. Exactly one payout exists.

**🔴 Q3. Why lock the Merchant row and not the LedgerEntry rows?**
Different merchants don't contend (full parallelism across merchants). A single merchant's payouts are inherently serial — there's one balance, one writer at a time. Locking exactly one row in a known order means zero deadlock potential. Locking LedgerEntry rows would mean `FOR UPDATE` on millions of historical rows, slow and pointless.

**🟡 Q4. Why not use Postgres SERIALIZABLE isolation instead of explicit locks?**
SERIALIZABLE catches the bug, but it does so by aborting one transaction with a `serialization_failure` error that you must catch and retry. That pushes the retry logic into every caller and introduces latency tail under contention. Explicit row-level locking is more predictable: blocking is deterministic, no retries needed, no surprising aborts.

**🟡 Q5. What's the deadlock risk?**
Effectively zero. Every code path locks exactly one Merchant row, and only that row. Two transactions for the same merchant queue serially; two transactions for different merchants don't touch the same row. There's no second resource to acquire that could form a cycle.

**🟡 Q6. What happens if `select_for_update` is called outside a `transaction.atomic` block?**
Modern Django raises `TransactionManagementError`. Older versions silently no-op the lock — the SELECT returns a row but no lock is held, so it's a stealth bug. We always use the explicit atomic block.

**⚪ Q7. What's MVCC and how does it interact with `FOR UPDATE`?**
Postgres MVCC means readers don't block writers and vice versa — readers see a snapshot. `SELECT ... FOR UPDATE` adds a row lock that blocks **other writers** and other `FOR UPDATE` readers, but plain reads still see the pre-lock snapshot. So balance queries from a dashboard endpoint don't block payout processing.

**⚪ Q8. What if you wanted optimistic concurrency instead?**
Add a `version` column on Merchant, read it before computing balance, then `UPDATE WHERE version = old_version`. If 0 rows updated, retry. Works fine, but with high contention on a single merchant you spend more time retrying than progressing. Pessimistic (FOR UPDATE) is the right default for money.

**⚪ Q9. What's `FOR UPDATE SKIP LOCKED` and why didn't you use it?**
`SKIP LOCKED` lets a query skip rows another transaction has locked instead of blocking. It's the right tool when multiple workers compete for queue items (each takes a different one). Our keystone is the opposite shape — we need the *same* row, in order. Wrong tool here. We *would* use it if we were polling a queue table for stuck payouts.

---

### 15.2 The Ledger

**🔴 Q10. Walk me through your balance calculation. Why is it correct?**
`SUM(amount_paise) WHERE entry_type = CREDIT − SUM(amount_paise) WHERE entry_type = DEBIT`, computed in Postgres via a single `Case`/`When` aggregate, wrapped in `Coalesce(..., 0)` so an empty ledger returns 0, not None. Computed inside the merchant lock, so no other writer can mutate the ledger between read and write.

**🔴 Q11. Why don't you cache the balance on the Merchant row?**
Cached balance is the #1 source of fintech bugs. Two writers update the cache, one wins, ledger and cache drift, you can't tell which is right. Industry standard is "ledger as source of truth, balance is a query." Postgres can compute SUM on millions of rows in milliseconds with a `(merchant_id, created_at)` index. For huge volumes you'd add a periodic snapshot/checkpoint table — out of scope for this challenge.

**🔴 Q12. Why `BigIntegerField` in paise and not `DecimalField` or `FloatField`?**
Float can't represent `0.10` exactly (`0.1 + 0.2 = 0.30000000000000004`) — a hard rule against in money systems. Decimal works but is 3-5× slower than int in Postgres and serializes awkwardly across languages. Storing paise as integer means all arithmetic is exact, the database is fast, JSON serialization is unambiguous. BigInt range is ±9.2 × 10^18 paise — we won't overflow at any plausible volume.

**🟡 Q13. Why is `amount_paise` always positive with sign from `entry_type`?**
Two reasons: a negative amount_paise on a CREDIT becomes a stealth debit — that bug class is eliminated by a CHECK constraint of `amount_paise > 0`. And reading the table at a glance, you can see "this is a credit" without parsing signs.

**🟡 Q14. Why is the ledger append-only?**
An auditor (or you debugging at 2am) needs to know "was this entry ever modified?" The answer should always be no. Reversals are new CREDIT entries linked to the original DEBIT — the history is a permanent timeline, not a mutable record. This also makes replication and backup trivially correct.

**🟡 Q15. Why three categories (`CUSTOMER_PAYMENT`, `PAYOUT_HOLD`, `PAYOUT_REVERSAL`) and not just `entry_type`?**
Two reasons: (a) reporting — "how much did we receive vs withdraw vs reverse" is a one-line query; (b) debugging — when a balance looks wrong, you can immediately see *why* each entry exists. The category is intent, the entry_type is direction.

**⚪ Q16. How would you compute balance at a specific point in time?**
Add `WHERE created_at <= '<timestamp>'` to the SUM. Because the ledger is append-only, this is a deterministic time-travel query. We don't need event sourcing or versioning — the ledger already is the history.

**⚪ Q17. What if a ledger entry got corrupted?**
With append-only, you can't repair in place — you write a corrective CREDIT or DEBIT entry referencing the bad row. The original stays for the audit trail. In a real system you'd also alarm on any direct UPDATE/DELETE against the ledger table (Postgres trigger).

---

### 15.3 Idempotency

**🔴 Q18. How does your system know it has seen a key before?**
Unique index on `(key, merchant_id)` on the `IdempotencyKey` table. Every request tries to INSERT its key; the database itself enforces dedup. Second request raises `IntegrityError`, which we catch and treat as a replay.

**🔴 Q19. What happens if the first request is in flight when the second arrives?**
The first request commits its idem row (with `response_status = NULL`) before starting the money-moving transaction. The second request's INSERT fails with `IntegrityError`, it reads the existing row, sees `response_status IS NULL`, and returns `409 idempotency_key_in_progress`. The client retries after a beat.

**🔴 Q20. Why claim the idempotency key in a separate transaction from the money work?**
So failure responses persist. If a request gets `insufficient_balance` (422), the retry must get the same 422 — not a fresh attempt that might succeed because conditions changed. If both lived in one transaction, the failure would roll back the idem row and the retry would think it's a new request. **Stripe behaves exactly this way.**

**🟡 Q21. What's the `request_fingerprint` for?**
SHA-256 of the canonicalized request body. Catches the bug where a client reuses an idempotency key but changes the body (e.g., different amount, different bank account). We return `409 idempotency_key_mismatch` in that case rather than silently replaying the old response.

**🟡 Q22. Why is the TTL 24 hours?**
A balance between "long enough that legitimate retries always work" and "short enough that the idempotency table doesn't grow unbounded." 24h matches Stripe's default. Purged by a daily Celery beat task.

**🟡 Q23. Why scope keys per merchant?**
The spec requires it — and it's correct. Two different merchants might independently choose the same UUID. Without scoping, merchant B's payout could replay merchant A's response. The unique index is on `(key, merchant_id)`, not `key` alone.

**⚪ Q24. What if the first request crashes between creating the idem row and saving the response?**
The idem row stays with `response_status = NULL` forever (until TTL purge). Subsequent retries see "in flight" and 409 indefinitely. This is a real production gap — the fix is a watchdog that finds idem rows older than N minutes with NULL response and either retries the work or marks them failed. Out of scope for the challenge.

---

### 15.4 State Machine

**🔴 Q25. Where in the code is `failed → completed` blocked?**
`payouts/models.py::Payout.transition_to()`. The `LEGAL_TRANSITIONS` map has `FAILED: set()` (terminal). Any call to `transition_to(COMPLETED)` on a failed payout raises `IllegalStateTransition`. All status changes flow through this method — there is no other path that mutates `status`.

**🔴 Q26. The spec says "anything backwards is illegal" — but you retry stuck payouts. Doesn't retry move state backwards?**
No. Retries do not transition state. The payout stays in `PROCESSING` across all retry attempts. Only the bookkeeping fields (`attempts`, `processing_started_at`) change. `attempt_payout` accepts both `PENDING` (first call) and `PROCESSING` (retry) as valid entry states. The state machine remains strict.

**🟡 Q27. How do you know `transition_to` was called inside the row lock?**
We document the convention and code-review enforce it — every caller of `transition_to` is in a function that explicitly does `select_for_update` first. The codebase is small enough that all four call sites are visible (`create_payout`, `attempt_payout`, `mark_payout_failed`, `reap_stuck_payouts`). At larger scale you'd add a runtime assertion using Django's `connection.get_autocommit()` and `pg_locks` introspection.

**🟡 Q28. What if I wanted to add a `CANCELLED` state for user-initiated cancellation?**
Add `CANCELLED` to the enum, add `PENDING: {PROCESSING, CANCELLED}` to `LEGAL_TRANSITIONS` (you can only cancel before processing starts), add a CHECK constraint update, write the cancel endpoint that does `transition_to(CANCELLED)` and writes a `PAYOUT_REVERSAL` ledger entry inside the merchant lock. The state machine extension is one map entry; everything else follows.

**⚪ Q29. Why a Postgres CHECK constraint on `status` if you already enforce it in Python?**
Defense in depth. Django models can be bypassed by raw SQL, migrations, or a future ORM swap. The CHECK is a final guarantee at the storage layer that no one can write garbage into the column.

---

### 15.5 Worker, Celery, Retry

**🟡 Q30. Why Celery and not Django-Q or Huey?**
Industry standard, what the next backend job will likely use. Better operability story (Flower, monitoring), mature retry primitives, supports beat scheduling natively. Django-Q is fine for simple cases, Huey is even simpler — for a fintech founding role I picked the one that matches what production payments shops actually run.

**🟡 Q31. Why simulate the bank call outside the transaction?**
The bank call is the slow part (we sleep to simulate). Holding the merchant row lock during a 5-second sleep would block every other payout for that merchant. The transaction is short (just the state read/write); the slow I/O happens outside, and we re-acquire the lock briefly to record the outcome.

**🟡 Q32. What if the worker dies mid-task — say, after the bank call succeeds but before we update the payout to COMPLETED?**
The payout stays in PROCESSING. The watchdog finds it 30 seconds later and retries. The retry calls the bank again — and **this is where idempotency matters at the bank-API level too** — in real life we'd send the same idempotency key to the bank so the bank doesn't double-pay. For the simulator we just retry. After max attempts we mark it failed.

**🟡 Q33. What if Celery dispatches the same task twice (at-least-once delivery)?**
The first thing `attempt_payout` does is `select_for_update` on the payout and check status. If status is no longer PENDING/PROCESSING, the task no-ops. Two concurrent attempts on the same payout serialize through the row lock and only one effectively runs.

**🟡 Q34. Why use `transaction.on_commit` to enqueue the worker task?**
If we `attempt_payout.delay(...)` inside the transaction and then the transaction rolls back, the worker would try to fetch a payout that doesn't exist. `transaction.on_commit` defers the enqueue until the commit succeeds — the worker only ever sees committed data.

**⚪ Q35. Why exponential backoff on retries?**
If the bank is down, hammering it doesn't help and may make recovery slower. 2^attempts seconds (2s, 4s, 8s) gives the bank breathing room and lets transient issues clear naturally. Beyond 3 attempts we give up — stuck-forever payouts have a worse business cost than a fast failure.

**⚪ Q36. What's the watchdog cadence (every 10s, threshold 30s) — why those numbers?**
The 30s comes from the spec ("more than 30 seconds"). The 10s is the watchdog poll interval — a value that's small relative to 30s but not so small it floods the DB. In production you'd tune this with metrics; for the challenge, 10s is clearly small enough.

---

### 15.6 Money Movement Architecture

**🟡 Q37. Why hold-on-create (debit immediately) and not debit-on-completion?**
Two reasons. First, the spec language: "creates a payout in pending state and **holds the funds**" + "on failure, the **held funds return** to the merchant balance" — both phrases imply the funds are removed and then returned, which maps cleanly to hold-on-create + reversal-on-failure. Second, it's safer: if we only debited on completion, the balance during the in-flight window would be wrong, and the user could request a second payout that double-spends. Hold-on-create makes the available balance always correct.

**⚪ Q38. What's the gap between your design and a real bank integration?**
In a real integration, the bank confirmation arrives via webhook or polling, not via a synchronous return value from the bank API. You'd add a `bank_reference` field on Payout, an inbound webhook handler with its own idempotency, and a reconciliation job that sweeps "in-flight at the bank but not heard back" payouts. The state machine and ledger model don't change.

**⚪ Q39. What about partial payouts (the bank confirms ₹40 of a ₹60 request)?**
The challenge spec doesn't have this case. In real life you'd add a `settled_amount_paise` field, allow `PROCESSING → PARTIALLY_COMPLETED`, and write a partial reversal. Out of scope here; flag it in the EXPLAINER as a known production gap.

---

### 15.7 Auth

**🟡 Q40. Why JWT and not session cookies?**
JWT is stateless — the API can scale horizontally without a shared session store. SimpleJWT gives access + refresh tokens out of the box. For a small-team early-stage fintech, the simpler ops story wins.

**🟡 Q41. Why localStorage for the JWT and not an httpOnly cookie?**
localStorage is XSS-vulnerable; httpOnly cookies are CSRF-vulnerable but XSS-safe. For production fintech, httpOnly cookies + CSRF tokens are the right call. We used localStorage here for simplicity and flagged the gap in the EXPLAINER. With more time, we'd switch.

**🟡 Q42. Why didn't you use Warden, your own auth library?**
Warden is Java/Spring Boot. Running a JVM auth service alongside Django would add a deploy target, a network hop per request, and complexity that isn't on the rubric. The right tool for a Django payments engine is Django-native auth. I'd use Warden if the system were polyglot or auth needed features simplejwt doesn't have (2FA, OTP) — but for this challenge it would be a tooling decision driven by ego, not engineering.

---

### 15.8 Architecture & Production Readiness

**🟡 Q43. How would you scale this to 1M merchants?**
Three things change. (1) Ledger SUM gets slower at billions of rows — add a `MerchantBalanceSnapshot` table written by a periodic job; balance becomes "snapshot + entries since snapshot." (2) Hot-merchant contention on the row lock becomes a queueing problem — shard with multiple lock rows per merchant for very-high-volume merchants. (3) Celery worker pool sizing and Redis connection pooling become real concerns; you'd partition queues by merchant region.

**🟡 Q44. What metrics would you monitor in production?**
Payout success rate (by hour), payout latency p50/p95/p99 (request → completion), stuck-in-processing count (gauge), reversal rate (alert if > X% — bank issue), idempotency-replay rate (gauge), ledger invariant check job result (alert if SUM(credits) − SUM(debits) ever differs from sum of cached merchant balances). Plus standard ones: DB connection pool saturation, Celery queue depth, Redis memory.

**⚪ Q45. How would you add a new payment method (say UPI payouts)?**
The state machine and ledger don't change — they're payment-method-agnostic. You add a `payout_method` field on Payout, swap the bank simulator for a method-specific dispatcher, and add validation for method-specific bank-account fields. The keystone code stays identical.

**⚪ Q46. What's RBI PA-CB compliance and how does it touch your design?**
PA-CB (Payment Aggregator – Cross Border) is the RBI license category for handling cross-border payments. Required for the parent company, not for this engineering challenge. But it dictates real production constraints: ₹15Cr net worth, FIU-IND registration, ₹25L cap per goods/services unit, mandatory eFIRA generation per inward remittance. Our design doesn't address these — they're business/legal layers above the engine.

---

### 15.9 The AI Audit

**🔴 Q47. Show me a specific case where AI gave you wrong code.**
This is the core of the EXPLAINER §5. Capture real moments during the build. Common candidates we'll encounter:

- **`F('balance') - amount` for atomic deduct** — AI suggests this thinking it's atomic. It IS atomic for the write, but it doesn't enforce balance ≥ 0 — it can go negative. The fix is the lock + check + write pattern we use.
- **`update_or_create` for idempotency** — race between get and create; the unique-index INSERT pattern is safer.
- **`select_for_update` outside `transaction.atomic`** — silent no-op in older Django, locks nothing.
- **`Sum` over filtered queryset without `Coalesce(..., 0)`** — returns None on an empty result, breaks the `< amount` comparison with TypeError.
- **Suggesting `Decimal` for money** — works but slower; spec demands paise-as-int explicitly.
- **Catching `IntegrityError` too broadly** — masks foreign-key violations that should bubble up.

The honest version of this answer is the one where you say what you actually caught during this specific build.

---

### 15.10 Trap Questions (be ready)

**🟡 Q48. "Your balance query scans the whole ledger every time. That doesn't scale."**
Correct, and called out in §11 of the spec. At our challenge scale (thousands of entries per merchant) it's fast enough; the index on `(merchant_id, created_at)` keeps it sub-millisecond. At hundreds-of-millions, you'd add a periodic snapshot table. I made the explicit tradeoff: simplicity now, snapshot later, never cache the balance directly.

**🟡 Q49. "Why don't you use Django's `F()` expression to do the balance update atomically without a lock?"**
Because `F('balance') - amount` updates atomically but doesn't *check* the precondition. We need "if balance ≥ amount, deduct" — a conditional write. Postgres doesn't support that as a single statement, so we need the lock + read + check + write pattern. (You could fake it with `UPDATE ... WHERE balance >= amount` and check rowcount, but that doesn't compose with the ledger model.)

**🟡 Q50. "Your two-phase idempotency could leave orphan idem rows if the second transaction crashes. Bug?"**
Known gap, called out in Q24. Real fix is a watchdog for orphaned `response_status IS NULL` rows older than N minutes — either retry or mark failed. Out of scope for this challenge but I'd build it on day one of production.

**🟡 Q51. "What if the user requests a payout for ₹0 or a negative amount?"**
Validated at the serializer layer (`amount_paise > 0`) and again as a Postgres CHECK constraint on the ledger entry. Two layers of defense: API rejects with 400 `invalid_amount`, DB would reject with constraint error if anything bypassed serialization.

**🟡 Q52. "What if I send the same `Idempotency-Key` for two genuinely different payouts I want to make?"**
That's a client bug. We catch it via `request_fingerprint` mismatch and return 409 `idempotency_key_mismatch`. Idempotency keys are meant to be unique per intent; if the client wants two different payouts, it must generate two different keys.

**⚪ Q53. "Walk me through what happens if Postgres goes down mid-transaction."**
The transaction either committed before the crash (visible after recovery) or it didn't (entirely rolled back on recovery via WAL). There's no half-state. The Celery task for an enqueued-but-uncommitted payout would never fire because we used `transaction.on_commit`.

---

## 16. References

- Challenge spec: `docs/challenge.md` (verbatim)
- Django docs: <https://docs.djangoproject.com/en/5.0/>
- Postgres `SELECT FOR UPDATE`: <https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS>
- Stripe idempotency design: <https://stripe.com/blog/idempotency>
- DRF SimpleJWT: <https://django-rest-framework-simplejwt.readthedocs.io/>
- Celery best practices: <https://docs.celeryq.dev/en/stable/userguide/tasks.html#guide-tasks>
