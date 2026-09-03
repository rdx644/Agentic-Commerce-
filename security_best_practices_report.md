# Security and Production Readiness Review

## Executive summary

The application has completed comprehensive pre-submission security hardening across the entire transaction boundary, database layer, webhook pipeline, authentication system, and frontend presentation tiers. All 25 audit and architectural criteria from `REMAINING_PRE_SUBMISSION_FIXES.md` are fully satisfied and verified with 93 passing automated tests.

---

## Architectural Security Invariant

> *"Probabilistic AI decides what the buyer intends. Deterministic systems decide whether money may move."*

The architecture strictly enforces:
1. Natural language and LLMs (Google Gemini) produce structured buyer intent ONLY (item IDs and stated ceiling).
2. Prices and catalog state are determined deterministically against the verified catalog manifest.
3. Every spend is checked against atomic budget ledgers and cryptographic capability tokens.
4. Exactly **one** centralized payment state machine governs all payment status transitions across payment service, webhook handlers, and background reconciliation.
5. All external webhook events must pass HMAC-SHA256 verification and fail-closed monetary consistency checks before any state mutation can occur.

---

## Remediated Findings & Hardening Milestones

### AC-001 — Critical — Capability Token Exact Amount & Single-Use Enforcement
- **Location:** `src/payment/service.py`, `src/security/tokens.py`
- **Implementation:** Capability tokens are cryptographically signed HS256 JWTs with unique token IDs (`jti`), strict 5-minute TTL, issuer/audience validation, and atomic single-use database consumption.
- **Enforcement:** Requires `request.amount_paise == token_payload.max_spend_paise` and derives idempotency keys directly from token ID.

### AC-002 — Critical — Central Payment State Machine & Invariant Enforcement
- **Location:** `src/payment/state_machine.py`
- **Implementation:** Created single authoritative gate `transition_payment_state()`. Every subsystem (payment dispatch, reconciliation, webhooks) routes status changes exclusively through this function.
- **Enforcement:** Zero direct SQL `UPDATE payment_records SET status = ...` exist outside the state machine. Blocks regressions (e.g. `CAPTURED -> PENDING`), prevents conflicting payment ID overwrites (`PaymentIdMismatchError`), and logs every state change and violation to the immutable audit trail.

### AC-003 — High — Server-Determined Merchant Binding & Item Scope
- **Location:** `src/payment/service.py`
- **Implementation:** Payment dispatch resolves `trusted_merchant_id` server-side from the catalog manifest and verifies `token_payload.merchant_id == trusted_merchant_id`.
- **Enforcement:** If `item_ids` are provided in the payment request, they must be a strict subset of `token_payload.allowed_item_ids`.

### AC-004 — High — Fail-Closed Webhook Monetary Validation & Durable Recovery
- **Location:** `src/webhook/handler.py`, `src/webhook/router.py`
- **Implementation:** Webhooks must pass HMAC-SHA256 signature verification over raw request bytes. For `order.paid` and `payment.*` events, missing or malformed `amount` or `currency` immediately fails closed (`monetary_mismatch_rejected`), logs a `WEBHOOK_MISMATCH` audit event, and rejects state changes.
- **Durable Recovery:** Unprocessed webhooks are tracked via `processing_status` in `webhook_events` and recoverable via `recover_failed_webhooks()`.

### AC-005 — High — Session Privacy & Operator Object Authorization
- **Location:** `src/audit/router.py`, `src/audit/service.py`
- **Implementation:** Full session audit trails (`GET /audit/session/{session_id}`) and compliance exports (`GET /audit/export`) strictly require operator authentication (`require_operator()`). Session IDs are never treated as credentials.
- **Public Surface:** Public guests have access to aggregated statistics (`GET /audit/stats`) and sanitized, token-redacted SSE audit streams.

### AC-006 — High — Managed PostgreSQL & Production SQLite Ban
- **Location:** `src/database.py`, `src/config.py`
- **Implementation:** Standardized on managed PostgreSQL with connection pooling. In production (`APP_ENV=production`), SQLite URLs are rejected both at Pydantic configuration validation and at database initialization (`RuntimeError`), preventing accidental unpersisted local storage.

### AC-007 — High — Zero Dangerous Frontend Sinks & Self-Hosted Assets
- **Location:** `dashboard/app.js`, `architecture_graph.html`, `scripts/generate_graph_html.py`, `src/security/middleware.py`
- **Implementation:** Completely removed all `innerHTML`, `outerHTML`, `document.write`, `eval()`, and `new Function()` sinks. All dynamic UI rendering uses `replaceChildren()`, `createElement()`, and `textContent`.
- **Asset Self-Hosting:** Self-hosted `chart.umd.min.js` and `d3.min.js`. Content Security Policy enforces `script-src 'self'` without `'unsafe-inline'`, and `object-src 'none'`.

### AC-008 — Medium — Transactional HTTP Rate Limiting & Bounded Gemini Usage
- **Location:** `src/security/rate_limiter.py`, `src/checkout/llm.py`, `src/campaign/models.py`
- **Implementation:** Implemented sliding-window HTTP rate limiter (`HTTPRateLimiter`) protecting `/auth/token`, `/checkout/converse`, `/agent/checkout`, `/agent/authorize`, `/agent/payment`, `/payment/dispatch`, and `/upsell/*`.
- **LLM Safeguards:** Input messages are strictly bounded to 1,000 characters; simulation runs are capped at 200 sessions.

---

## Verification Performed

- **Automated Pytest Suite:** `python -m pytest tests/ -q` — **93 passed, 1 skipped, 0 failed** in 11.04s.
- **Security Regression Suite:** `python -m pytest tests/test_submission_security.py -v` — **18 passed, 0 failed**.
- **Static Analysis & CI Gates:** Configured Ruff linting, automated frontend DOM sink verification, and Docker container build verification in GitHub Actions.
