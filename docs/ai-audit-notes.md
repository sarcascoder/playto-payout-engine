# AI Audit Running Notes

Real moments where AI suggested subtly wrong code. Captured as they happen.
Format: section per incident — what AI said, what was wrong, what we replaced it with.

---

## Incident 0: Template

```
### Incident N: <one-line summary>

**Context:** what we were building when this came up

**What AI suggested:**
\`\`\`python
# the wrong code, verbatim
\`\`\`

**What was wrong:** technical explanation of the bug class

**What I replaced it with:**
\`\`\`python
# the corrected code
\`\`\`

**Lesson:** what to remember next time you see a similar AI suggestion
```

---
<!-- new incidents below this line -->

### Incident 1: CORS allowed-headers default doesn't include custom headers

**Context:** First end-to-end test of the React dashboard against the live Django API. Form submits, backend never sees the request, frontend shows "Request failed".

**What AI suggested (when scaffolding `settings.py`):**
```python
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173"
).split(",")
# (no CORS_ALLOW_HEADERS set — relies on django-cors-headers default)
```

**What was wrong:** The `django-cors-headers` default `CORS_ALLOW_HEADERS` is the standard 6: `accept, authorization, content-type, user-agent, x-csrftoken, x-requested-with`. **Custom headers like `Idempotency-Key` are NOT included.** When the browser does a preflight OPTIONS, the server says "I don't allow that header", browser blocks the actual POST, axios surfaces a CORS network error with no `err.response`. The frontend's specific error handlers (which key off `err.response.data.error`) all miss, falling through to the generic "Request failed".

The bug is invisible during backend testing — `curl` doesn't do CORS preflight. It only shows up the moment a real browser hits the API. AI-generated CORS configs almost always assume "default headers are enough" and never proactively add custom ones.

**What I replaced it with:**
```python
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers) + ["idempotency-key"]
```

**Lesson:** Whenever you add a custom request header to your API contract, you must also add it to `CORS_ALLOW_HEADERS`. The bug doesn't surface in pytest, doesn't surface in curl — only in a real browser. Always test the full stack end-to-end before declaring a feature done.

---

### Incident 2: `transaction.on_commit` enqueue silently lost when callback was a stub

**Context:** I built `create_payout` on Day 2 with a stub `_enqueue_attempt_payout` (returned None) and wired `transaction.on_commit(lambda: _enqueue_attempt_payout(...))`. On Day 3 I replaced the stub with the real Celery `attempt_payout.delay()` call. Discovered later that one Day-2 payout (`b3c1e84f`) was permanently stuck in PENDING — it had been enqueued through the stub, which did nothing, so the worker never got the message.

**What AI would naturally suggest:**
```python
# create_payout — fire and forget
attempt_payout.delay(str(payout.id))
```

**What's wrong with this pattern overall:** Enqueueing inside the transaction (without `on_commit`) means the worker can fire BEFORE the DB commits — worker fetches the payout by ID, sees it doesn't exist, fails. Using `transaction.on_commit` fixes that race. But there's a SECOND failure mode: the `on_commit` callback itself can throw, or be a no-op, and the Payout row exists in the DB with no corresponding queue entry. **There is no built-in retry from "row exists, queue message lost."**

The orphaned-PENDING payout is the symptom. The watchdog only sweeps PROCESSING (stuck > 30s); it doesn't watch PENDING. So orphans live forever.

**What I added:** A note in the README + the EXPLAINER about this gap. The production fix would be a "transactional outbox" pattern — write the queue message to a DB table inside the same transaction, and have a separate poller that drains the outbox into Celery. That guarantees "if the row exists, the message will eventually be delivered." Out of scope for this 5-day challenge, but called out explicitly.

For the orphaned `b3c1e84f` row, I cleaned it up manually via shell.

**Lesson:** Enqueueing background work from a transaction is fundamentally a distributed-systems problem. `on_commit` solves the "fire too early" half but not the "message never sent" half. Any real money system needs a transactional outbox or equivalent for durability.
