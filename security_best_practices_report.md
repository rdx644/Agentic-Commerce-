# Security and Production Readiness Review

## Executive summary

The application now has a safer deployment baseline, a strict CSP-compatible dashboard, capability-bound payments, and authorised upsell flows. Automated and live black-box checks pass. It is suitable for a **single-instance, controlled deployment** after production secrets and hostnames are configured.

It is not appropriate to expose as a multi-tenant public administration service until the remaining data-platform finding below is addressed.

## Remediated findings

### AC-001 — Critical — Capability token could be used for arbitrary partial charges

**Location:** `src/payment/service.py:132`

**Evidence:** The dispatch path now requires `request.amount_paise != token_payload.max_spend_paise` to reject, and derives its idempotency receipt from the token ID.

**Impact before fix:** A valid token could have been replayed with multiple different amounts beneath its limit, allowing total orders to exceed the authorised spend.

**Fix applied:** Dispatch now accepts only the exact authorised amount and idempotency is tied to the specific capability token.

### AC-002 — High — Upsell endpoints accepted unauthorised requests

**Location:** `src/upsell/service.py:36`, `src/upsell/service.py:136`

**Evidence:** Both offer generation and acceptance call `verify_capability_token` and check the session binding.

**Impact before fix:** A caller who knew a session ID could generate or accept an upsell against that session’s remaining budget.

**Fix applied:** Both actions require a valid original checkout authority; the campaign simulation now propagates that token.

### AC-003 — High — Stored DOM XSS in the audit dashboard

**Location:** `dashboard/app.js:27`, `dashboard/app.js:128`, `dashboard/app.js:326`, `dashboard/app.js:443`

**Evidence:** API-supplied audit/session data is now rendered through `textContent`, DOM nodes, and `replaceChildren`, with no `innerHTML` sinks remaining.

**Impact before fix:** Attacker-controlled audit strings could execute script in an operator’s browser.

**Fix applied:** Removed unsafe DOM sinks and inline UI handlers. The CSP at `src/security/middleware.py:50` no longer permits `unsafe-inline`.

### AC-004 — Medium — Unsafe development configuration could be deployed

**Location:** `src/config.py:63`, `src/main.py:165`, `src/main.py:182`

**Evidence:** Production configuration validates JWT/Razorpay secrets and debug logging; API docs are disabled in production; trusted hosts and CORS are explicit environment configuration.

**Fix applied:** Added fail-closed settings, deployment documentation, a non-root Docker image, health check, and a persistent `/data` volume convention.

## Remaining findings requiring product/infrastructure decisions

### AC-005 — High — No user/operator authentication or object-level authorisation

**Location:** `src/audit/router.py:20`, `src/audit/router.py:44`, `src/campaign/router.py:15`, `src/payment/router.py:25`

**Evidence:** Resolved with `src/security/auth.py`; the dashboard plus privileged routers now share an HTTP Basic dependency and production requires a 16+ character operator secret. Production black-box checks returned 401 without credentials and 200 with valid credentials.

**Impact:** A public deployment could expose transaction/audit data and allow callers to run costly campaigns or reconciliation actions.

**Fix applied:** Administrative endpoints are protected in production. Before supporting multiple merchants or staff roles, replace the single operator boundary with tenant-aware OIDC/SSO and per-object authorisation.

### AC-006 — Medium — SQLite constrains availability and horizontal scale

**Location:** `src/database.py`, `Dockerfile:27`, `README.md:31`

**Evidence:** The release image deliberately runs one worker and stores SQLite data on a persistent volume.

**Impact:** This avoids multi-writer ambiguity for a single instance but is not resilient to host loss and cannot safely scale across replicas.

**Required decision:** Move ledgers and idempotency records to a managed transactional database before multi-replica deployment; add backups, migrations, and restore drills.

## Verification performed

- `python -m pytest -q -p no:cacheprovider` — 40 passed.
- Live service: healthy response, catalog read, stale-catalog guardrail rejection, invalid-token payment rejection, and 4-session campaign run all passed.
- Browser inspection: dashboard loaded with no console errors; live status, accessible buttons, labelled filters, and audit-table structure were present.
- Production-mode black-box check: dashboard and audit endpoints reject anonymous callers (401), accept the configured operator (200), keep `/docs` disabled (404), and leave `/health` public (200).
