# Playto Payout Engine

A merchant payout engine for Indian businesses collecting international payments. Built for the **Playto Pay Founding Engineer take-home challenge (2026)**.

🌐 **Live demo:** https://frontend-lake-mu-20.vercel.app
🔌 **Backend API:** https://playto-payout-engine-production-8dda.up.railway.app/api/v1
📦 **Repo:** https://github.com/sarcascoder/playto-payout-engine

---

## Demo accounts

| Email | Password | Initial balance |
|---|---|---|
| `alice@playto.dev` | `alice-pass-1` | ₹2,500 |
| `bob@playto.dev`   | `bob-pass-1`   | ₹8,000 |
| `carol@playto.dev` | `carol-pass-1` | ₹800   |

Try logging in, requesting a payout, watching it transition from `pending → processing → completed`/`failed` within 1-2 seconds. The bank simulator returns 70% success / 20% fail / 10% hang per the spec; the watchdog reaps stuck payouts every 10s.

---

## Stack

| Layer | Choice |
|---|---|
| Backend framework | Django 5.2 + DRF + djangorestframework-simplejwt |
| Database | PostgreSQL 16 (row-level locks via `SELECT FOR UPDATE`) |
| Background jobs | Celery 5 + Redis 7 (worker + beat) |
| Frontend | React 19 + Vite 8 + TypeScript + TailwindCSS v4 + TanStack Query |
| Local dev | Docker Compose (Postgres + Redis) + uv (Python) |
| Backend deploy | Railway (web + worker + beat + Postgres + Redis, all in one project) |
| Frontend deploy | Vercel |

---

## Local setup

```bash
# 1. Clone
git clone https://github.com/sarcascoder/playto-payout-engine
cd playto-payout-engine

# 2. Start Postgres + Redis
cp .env.example .env
docker compose up -d

# 3. Backend
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py shell < scripts/seed.py

# 4. Run backend (3 terminals)
uv run python manage.py runserver 0.0.0.0:8001
uv run celery -A config worker -l info --pool=solo
uv run celery -A config beat -l info

# 5. Frontend
cd ../frontend
npm install
cp .env.example .env
npm run dev
```

Visit http://localhost:5173 and log in as Alice.

---

## Tests

```bash
cd backend
uv run pytest
```

**25 tests pass**, including the two rubric-mandated ones:
- `tests/test_concurrency.py` — two simultaneous payouts can't overdraw a balance
- `tests/test_idempotency.py` — same key returns the same response, scoped per merchant; failure responses persist

Plus state-machine, balance-derivation, end-to-end worker flow, and watchdog tests.

## How to demo each rubric criterion (live)

Open the [live dashboard](https://frontend-lake-mu-20.vercel.app), sign in as `bob@playto.dev / bob-pass-1` (₹8,000 balance — gives more room to play), and use the **"Demo: rubric-graded edge cases"** panel near the top. Three buttons:

| Button | Demonstrates | What you'll see |
|---|---|---|
| 🏎️ **Concurrency: 8 parallel payouts** | The `SELECT FOR UPDATE` lock | 8 requests fired at once, each demanding ⅓ of available balance → exactly ~3 succeed, ~5 get clean 422s. Balance never goes negative. |
| 🔁 **Idempotency: same key twice** | The unique-index dedup | Two POSTs with identical `Idempotency-Key` → same payout id, second returns `idempotent_replay: true`. |
| 💸 **Overdraw: 422 insufficient** | Balance enforcement | Asks for `available + ₹100` → returns `422 insufficient_balance` with structured body. |

Then watch the **payout history** and **recent activity** tables update live (poll every 3s). For failed payouts you'll see the matching `payout_reversal` credit entry — that's the atomic state-transition + reversal in action.

### Or via curl from your terminal

```bash
BASE=https://playto-payout-engine-production-8dda.up.railway.app/api/v1
ACCESS=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"bob@playto.dev","password":"bob-pass-1"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access'])")
BANK=$(curl -s $BASE/bank-accounts -H "Authorization: Bearer $ACCESS" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")

# Concurrency: fire 8 parallel ₹3000 payouts (Bob has ₹8000 → ~2 should succeed)
for i in $(seq 1 8); do
  ( curl -s -X POST $BASE/payouts \
      -H "Authorization: Bearer $ACCESS" \
      -H "Idempotency-Key: $(uuidgen | tr 'A-Z' 'a-z')" \
      -H "Content-Type: application/json" \
      -d "{\"amount_paise\": 300000, \"bank_account_id\": \"$BANK\"}" \
      -w "\n[$i] HTTP %{http_code}\n" ) &
done
wait

# Idempotency: same key twice
KEY=$(uuidgen | tr 'A-Z' 'a-z')
for i in 1 2; do
  curl -s -X POST $BASE/payouts \
    -H "Authorization: Bearer $ACCESS" \
    -H "Idempotency-Key: $KEY" \
    -H "Content-Type: application/json" \
    -d "{\"amount_paise\": 1000, \"bank_account_id\": \"$BANK\"}" \
    -w "\n[$i] HTTP %{http_code}\n"
done
```

---

## Architecture (high level)

The full design is in `docs/superpowers/specs/2026-04-27-playto-payout-engine-design.md` (with a 50-question CTO-prep bank in §15). The five things you need to know:

1. **Append-only ledger is the source of truth for balance.** No cached balance anywhere. Balance = `SUM(credits) − SUM(debits)`, computed in Postgres via a single `CASE/WHEN` aggregate. Three categories: `CUSTOMER_PAYMENT` (credit), `PAYOUT_HOLD` (debit, written when payout requested), `PAYOUT_REVERSAL` (credit, written when payout fails).

2. **Money is BigInteger paise.** Never float, never Decimal. Sign comes from `entry_type`, `amount_paise > 0` enforced by Postgres CHECK constraint.

3. **Concurrency** is enforced by `SELECT ... FOR UPDATE` on the Merchant row inside a `transaction.atomic` block. **Every code path that writes to the ledger holds this lock first.** Different merchants run in parallel; same merchant's writes serialize through the lock. Zero deadlock surface area.

4. **Idempotency** uses a `UNIQUE(key, merchant_id)` constraint on a separate table — the index itself is the database-level dedup primitive (no "check then create" race). The idempotency row is committed in its own transaction *before* the money-moving one, so failure responses (e.g. `422 insufficient_balance`) persist and are replayed on retry. Stripe-style.

5. **State machine** is strict: `pending → processing → {completed | failed}`. Backwards transitions are blocked. Retries do NOT move state backwards — the payout stays in `PROCESSING` across all retry attempts; only `attempts` and `processing_started_at` change.

See `EXPLAINER.md` for the deep dive on each.

---

## What I deliberately didn't build

- Customer payment ingestion — spec says skip
- Real bank API — simulator returns 70/20/10 success/fail/hang per spec
- Webhook delivery (bonus, skipped)
- Event sourcing (bonus, skipped)
- Pixel-perfect UI — rubric explicitly de-prioritizes

---

## Why not Warden?

I've shipped my own auth library — [Warden](https://github.com/sarcascoder/warden) (Java/Spring Boot, JWT + 2FA + OTP). I deliberately used `djangorestframework-simplejwt` here instead. Running a JVM auth service alongside Django would have added a deploy target, a network hop per request, and complexity that isn't on the rubric. The right tool for a Django payments engine is Django-native auth.

---

## License

[VIEW-ONLY](LICENSE) — code is public for employer evaluation only. No use, fork, or derivative works permitted without written permission.
