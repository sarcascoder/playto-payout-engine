# EXPLAINER

The five questions, answered as I'd say them to the CTO.

---

## 1. The Ledger

**Balance query** (`backend/payouts/services.py`):

```python
def _balance_paise(merchant: Merchant) -> int:
    agg = LedgerEntry.objects.filter(merchant=merchant).aggregate(
        balance=Coalesce(
            Sum(Case(
                When(entry_type=LedgerEntry.CREDIT, then=F("amount_paise")),
                When(entry_type=LedgerEntry.DEBIT, then=-F("amount_paise")),
                output_field=IntegerField(),
            )),
            Value(0),
        )
    )
    return int(agg["balance"])
```

This computes `SUM(credits) − SUM(debits)` entirely in Postgres via a single `CASE/WHEN` aggregate. `Coalesce(..., 0)` handles the empty-ledger case so we never compare `None < amount` in Python — that's a real bug class AI tools love to hand you.

**Why this model:**

I made three deliberate choices that all flow from "the ledger is the single source of truth":

1. **`amount_paise: BigIntegerField`, always positive, with a CHECK constraint `amount_paise > 0`.** Sign comes from `entry_type`. A negative `amount_paise` on a CREDIT becomes a stealth debit; eliminating that bug class with a CHECK is cheap. **BigInt** because float can't represent `0.10` exactly, and `Decimal` is 3-5× slower in Postgres than int. **Paise** because converting to rupees only at the display boundary keeps every arithmetic operation exact.

2. **Three categories** (`CUSTOMER_PAYMENT`, `PAYOUT_HOLD`, `PAYOUT_REVERSAL`) so reporting and debugging are one query: "how much was credited from customers vs reversed from failed payouts" is immediate. The `entry_type` is direction; the `category` is intent.

3. **Append-only.** No UPDATE, no DELETE on `LedgerEntry`. A failed payout writes a `PAYOUT_REVERSAL` CREDIT, not a modification of the original DEBIT. This makes audits, replication, and time-travel queries (`balance_at(t)` is `SUM ... WHERE created_at <= t`) trivially correct.

**I chose not to cache the balance on the Merchant row.** Cached balance is the single most common bug class in fintech: two writers update the cache, one wins, ledger and cache drift, you can't tell which is right. Postgres can `SUM` a million indexed rows in milliseconds. For higher volumes you'd add a periodic checkpoint table (snapshot + delta-since-snapshot); for this challenge scope the SUM is sub-millisecond.

---

## 2. The Lock

**The exact code** (`backend/payouts/services.py`, inside `create_payout`):

```python
# ── Phase 2: the money-moving transaction ──
with transaction.atomic():
    # 2a. ROW LOCK on the merchant.
    merchant = (
        Merchant.objects
        .select_for_update()        # SQL: SELECT ... FOR UPDATE
        .get(id=merchant_id)
    )

    # 2b. Validate bank account inside the lock.
    bank = BankAccount.objects.get(id=bank_account_id, merchant=merchant)

    # 2c. Compute available balance inside the lock.
    available = _balance_paise(merchant)
    if available < amount_paise:
        raise InsufficientBalance(available=available, requested=amount_paise)

    # 2d. Create the payout in PENDING.
    payout = Payout.objects.create(...)

    # 2e. Write the DEBIT_HOLD entry. Balance has now dropped.
    LedgerEntry.objects.create(
        merchant=merchant, amount_paise=amount_paise,
        entry_type=LedgerEntry.DEBIT, category=LedgerEntry.PAYOUT_HOLD,
        payout=payout,
    )
```

**The database primitive** is Postgres **row-level write locks**, acquired via `SELECT ... FOR UPDATE`. Held until the surrounding `transaction.atomic` block commits or rolls back. Other transactions that try to lock the same row block; plain reads (MVCC) are not blocked.

**Why this prevents overdraw:** when two requests arrive simultaneously to overdraw a merchant, exactly one connection's `SELECT FOR UPDATE` wins. It reads the balance, writes the DEBIT_HOLD, commits. The lock releases. The losing connection unblocks, re-reads the balance (now lower because of the new debit), sees `insufficient`, raises 422. **At no point can the merchant's balance go negative.** This is verified by `tests/test_concurrency.py` using two threads, a `threading.Barrier`, and `pytest --reuse-db` against real Postgres (not SQLite).

**Why lock the Merchant row** (and not the LedgerEntry rows or table-level)?
- Different merchants don't contend (full parallelism across merchants).
- A single merchant's payouts are inherently serial — there's one balance.
- Always locking exactly one row in a known order means **zero deadlock risk**.

**The system-wide invariant:** every code path that INSERTs into `LedgerEntry` first does `Merchant.objects.select_for_update().get(id=...)` inside the same `transaction.atomic` block. Four call sites: `create_payout`, `mark_payout_failed`, `reap_stuck_payouts` (when failing after max retries), and the seed script. Documented + code-reviewed; the codebase is small enough that all four are visible.

---

## 3. The Idempotency

**How the system knows it has seen a key before:** a `UNIQUE (key, merchant_id)` constraint on the `IdempotencyKey` table. Every request tries to INSERT its key:

```python
try:
    with transaction.atomic():
        idem = IdempotencyKey.objects.create(
            key=idempotency_key,
            merchant_id=merchant_id,
            request_fingerprint=fp,
            expires_at=timezone.now() + IDEMPOTENCY_TTL,
        )
    is_first_request = True
except IntegrityError:
    idem = IdempotencyKey.objects.get(
        key=idempotency_key, merchant_id=merchant_id
    )
    is_first_request = False
```

The unique index *is* the dedup primitive — there is no "check then create" race because the database itself adjudicates atomically.

**What happens if the first request is in flight when the second arrives:**

1. Request 1 commits the idem row with `response_status = NULL`.
2. Request 1 starts the money-moving transaction.
3. Request 2 arrives, `INSERT` fails with `IntegrityError`, reads the existing row.
4. Request 2 sees `response_status IS NULL` → returns `409 idempotency_key_in_progress`.
5. Client retries after a beat. By then, request 1 has either committed (replay returns the saved response) or hit a business-rule failure and persisted the error (replay returns the same error).

**Why the idempotency row commits in its OWN transaction** before the money-moving one: failure responses must persist. If both lived in one transaction, a `422 insufficient_balance` would roll back the idem row, and the retry would think it's a new request — potentially succeeding because conditions changed in between. Stripe behaves exactly this way. Verified by `test_failed_request_idempotency_persists_error`.

**Plus** the `request_fingerprint` (sha256 of canonicalized body) catches the bug where a client reuses a key but changes the body — we return `409 idempotency_key_mismatch` rather than silently replaying the wrong response.

**Keys are scoped per merchant** via the `(key, merchant_id)` composite unique index. Two different merchants can independently use the same UUID with no collision. **Keys expire after 24 hours** via a Celery beat task (`purge_expired_idempotency`).

---

## 4. The State Machine

**Where `failed → completed` is blocked** (`backend/payouts/models.py`):

```python
LEGAL_TRANSITIONS = {
    PENDING:    {PROCESSING},
    PROCESSING: {COMPLETED, FAILED},
    COMPLETED:  set(),    # terminal
    FAILED:     set(),    # terminal
}

def transition_to(self, new_status, *, actor, reason=""):
    legal = self.LEGAL_TRANSITIONS.get(self.status, set())
    if new_status not in legal:
        raise IllegalStateTransition(self.status, new_status, legal)
    old_status = self.status
    self.status = new_status
    self.save(update_fields=["status", "updated_at"])
    PayoutEvent.objects.create(
        payout=self, from_status=old_status, to_status=new_status,
        actor=actor, reason=reason,
    )
```

`FAILED` maps to `set()` — terminal. Any call to `transition_to(COMPLETED)` on a failed payout raises `IllegalStateTransition` (which the view layer turns into `409 illegal_state_transition`). **All status changes flow through this single method** — there is no other code path that mutates `status`.

**Defense in depth:** the `payouts` table has a `CHECK constraint` enforcing `status IN ('pending', 'processing', 'completed', 'failed')`. Even raw SQL bypassing the Django model can't insert garbage.

**The retry-without-going-backwards trick:** the spec says "anything backwards is illegal" — including `processing → pending`. The watchdog never moves a payout backwards. Instead, `attempt_payout` accepts BOTH `PENDING` (first call) and `PROCESSING` (retry) as valid entry states; the payout stays in `PROCESSING` across all retry attempts. Only `attempts` and `processing_started_at` change between attempts. This satisfies "no backwards transition" while still enabling retry. Verified by `test_processing_to_pending_illegal` (legality check) and `test_watchdog_retries_under_max_attempts` (retry behaviour).

Every legal transition writes a `PayoutEvent` audit row, so the timeline of any payout is queryable: when it was created, when each retry happened, when it terminated, and which actor (`api`, `worker`, `watchdog`) caused each move. That's a future-debugging insurance policy.

---

## 5. The AI Audit

The two most instructive moments from the build (full running notes in `docs/ai-audit-notes.md`).

### Incident 1: CORS allowed-headers default doesn't include `Idempotency-Key`

**Context:** First end-to-end test of the React dashboard against the live Django API. Form submits, backend never sees the request, frontend shows "Request failed".

**What AI suggested when scaffolding `settings.py`:**

```python
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173"
).split(",")
# (no CORS_ALLOW_HEADERS set — relies on django-cors-headers default)
```

**What was wrong:** the `django-cors-headers` default `CORS_ALLOW_HEADERS` is the standard six: `accept, authorization, content-type, user-agent, x-csrftoken, x-requested-with`. Custom headers like `Idempotency-Key` are NOT included. When the browser does a preflight OPTIONS, the server responds "I don't allow that header"; the browser blocks the actual POST; axios surfaces a CORS network error with no `err.response`; the frontend's specific error handlers (which key off `err.response.data.error`) all miss, falling through to a generic "Request failed" with no useful diagnostic.

**The bug is invisible during backend testing.** `curl` doesn't do CORS preflight. It only shows up the moment a real browser hits the API. AI-generated CORS configs almost always assume "default headers are enough" and never proactively add custom ones.

**What I replaced it with:**

```python
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers) + ["idempotency-key"]
```

**Lesson:** whenever you add a custom request header to your API contract, you must also add it to `CORS_ALLOW_HEADERS`. The bug doesn't surface in pytest, doesn't surface in curl — only in a real browser. Always test the full stack end-to-end before declaring a feature done.

### Incident 2: `transaction.on_commit` enqueue silently lost when callback was a stub

**Context:** I built `create_payout` on Day 2 with a stub `_enqueue_attempt_payout` (returned `None`) wired via `transaction.on_commit`. On Day 3 I replaced the stub with the real `attempt_payout.delay()` call. Discovered later that one Day-2 payout was permanently stuck in `PENDING` — it had been enqueued through the stub, which did nothing, so the worker never got the message. The watchdog only sweeps `PROCESSING` payouts (stuck > 30s); `PENDING` orphans live forever.

**What AI naturally suggests:**

```python
# Inside create_payout:
attempt_payout.delay(str(payout.id))
```

**What's wrong with this overall pattern:** enqueueing inside the transaction (without `on_commit`) means the worker can fire BEFORE the DB commits — worker fetches the payout by ID, sees it doesn't exist, fails. Using `transaction.on_commit` fixes that race. **But there's a second failure mode:** the `on_commit` callback itself can throw, or be a no-op, and the Payout row exists in the DB with no corresponding queue message. **There is no built-in retry from "row exists, queue message lost."** The orphaned-PENDING payout is the symptom.

**What I replaced it with:** in this challenge, the manual one-time re-enqueue via shell. In production, the right fix is a **transactional outbox** pattern — write the queue message to a DB table inside the same transaction, and have a separate poller drain the outbox into Celery. That guarantees "if the row exists, the message will eventually be delivered." Out of scope for this 5-day challenge; called out explicitly here as a known gap.

**Lesson:** enqueueing background work from a transaction is fundamentally a distributed-systems problem. `on_commit` solves the "fire too early" half but not the "message never sent" half. Any real money system needs a transactional outbox or equivalent for durability — and a watchdog that watches `PENDING` (not just `PROCESSING`) so orphans get caught instead of living forever.
