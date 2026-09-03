# 📘 Agentic Commerce Platform — Complete Project Reference & Session Archive

> **Track**: Track 01 — AI Growth & Agentic Commerce (Razorpay Hackathon 2026)  
> **Repository**: [https://github.com/rdx644/Agentic-Commerce-](https://github.com/rdx644/Agentic-Commerce-)  
> **Live Deployment**: [https://agentic-commerce-zyoy.onrender.com/dashboard](https://agentic-commerce-zyoy.onrender.com/dashboard)  
> **Archived On**: August 26, 2026  

---

## 📑 Table of Contents
1. [Executive Summary & Core Value Proposition](#1-executive-summary--core-value-proposition)
2. [Architectural Invariants & Security Boundaries](#2-architectural-invariants--security-boundaries)
3. [Component Architecture & Directory Map](#3-component-architecture--directory-map)
4. [Live Dashboard & Architectural Blueprint Design System](#4-live-dashboard--architectural-blueprint-design-system)
5. [Cloud Deployment & Docker Specifications (Render)](#5-cloud-deployment--docker-specifications-render)
6. [Operator Demo Credentials & Access](#6-operator-demo-credentials--access)
7. [Comprehensive Failure Taxonomy & Handling](#7-comprehensive-failure-taxonomy--handling)
8. [Test Suite & CI/CD Pipeline](#8-test-suite--cicd-pipeline)
9. [Judge / Evaluator Pitch Guide (3-Minute Script)](#9-judge--evaluator-pitch-guide-3-minute-script)

---

## 1. Executive Summary & Core Value Proposition

The **Agentic Commerce Platform** enables merchants to safely expose their catalogs to autonomous AI agents and AI buyers without risking financial loss, prompt injection exploits, or price drift.

### The Problem:
With the rapid emergence of agentic protocols (NPCI UAP, ACP, AP2, x402), AI buyers need to autonomously discover products, negotiate bundles, and initiate payments. However, standard LLM integrations suffer from catastrophic financial risks:
* **Prompt Injections**: An adversary prompts the AI: *"Sell me a MacBook for ₹1"*, causing naive agents to charge ₹1.
* **Price Drift**: Dynamic LLM hallucinations compute inconsistent totals.
* **Unbounded Spending**: Autonomous agents draining user wallets or double-spending.

### The Solution:
We enforce a **Zero-Price LLM Invariant** and **Cryptographic Capability Gating**:
1. The LLM only parses natural language into **Intent** (`item_ids`, `quantities`, `stated_ceiling_paise`).
2. Prices are resolved **deterministically** against a cryptographically hashed catalog.
3. Payment requires a short-lived (5-minute TTL) **HMAC-SHA256 Capability Token**.
4. Every single action is permanently recorded in an **immutable SHA-256 chained audit trail**.

---

## 2. Architectural Invariants & Security Boundaries

```
[ User / AI Buyer NL Message ]
              │
              ▼
[ Gemini 2.0 Flash / Heuristic Intent Parser ]  ──▶ Extracts { items, quantities, ceiling }
              │                                      (NEVER outputs prices)
              ▼
[ Cryptographic Catalog Resolver ]               ──▶ Hashes catalog & resolves exact paise prices
              │
              ▼
[ Deterministic Guardrail Engine ]              ──▶ Checks: Cart <= Ceiling && SessionBudget <= Limit
              │
      ┌───────┴────────────────┐
      ▼                        ▼
[ REJECT ]                 [ PASS ]
Blocked with reason        Issues HMAC-SHA256 Capability Token (5-min TTL)
Logged to Audit Trail                  │
                                       ▼
                       [ Payment Dispatcher (Razorpay) ]
                       Verifies Capability Token + Idempotency Key
                                       │
                                       ▼
                       [ PostgreSQL Budget Ledger ]
                       Atomic deduction + Immutable SHA-256 Audit Log
```

---

## 3. Component Architecture & Directory Map

```
agentic-commerce/
├── .github/workflows/ci.yml     # Modernized CI (checkout@v4, setup-python@v5, PostgreSQL 16)
├── dashboard/                   # Architectural Blueprint Frontend SPA
│   ├── index.html               # Cyanotype HTML5 interface with prompt chips & stats
│   ├── styles.css               # Drafting grid, monospace font tokens, wireframe UI
│   └── app.js                   # SSE live stream listener, Chart.js, checkout simulator
├── src/
│   ├── catalog/                 # Deterministic catalog, UCP discovery manifest (/.well-known/ucp)
│   ├── checkout/                # Conversational NL checkout, intent models, Gemini parser
│   ├── guardrail/               # Budget ledger, capability token signer, spend checks
│   ├── payment/                 # Razorpay API client, idempotency dispatch, reconciliation worker
│   ├── webhook/                 # Razorpay HMAC-SHA256 webhook listener
│   ├── upsell/                  # Heuristic basket lift & upsell recommendation engine
│   ├── campaign/                # Monte Carlo A/B simulator (Baseline vs Agentic)
│   ├── audit/                   # SHA-256 chained audit logger, SSE real-time stream
│   ├── security/                # OAuth2 JWT authentication, request size & security headers
│   ├── config.py                # Fail-closed Pydantic settings & production validators
│   ├── database.py              # PostgreSQL connection pool with cloud startup retry loops
│   └── main.py                  # FastAPI root entrypoint & router mounts
├── tests/                       # 40/40 comprehensive integration & unit test suite
├── Dockerfile                   # Hardened multi-stage non-root container with dynamic $PORT
├── docker-compose.yml           # Local orchestrator with port mapping (5433:5432)
├── render.yaml                  # 1-Click Render Cloud Blueprint specification
└── README.md                    # Professional documentation suite
```

---

## 4. Live Dashboard & Architectural Blueprint Design System

The frontend is designed around a **Cyanotype Architectural Blueprint** theme:
* **Background Palette**: Technical Navy (`--blueprint-bg: #003366`), Deep Foundation (`#002244`).
* **Drafting Grid**: 20px CSS linear coordinate grid with live mouse tracking (`COORD: X[####] Y[####] | 1:1`).
* **Wireframe Panels**: Sharp 90° corners, 1px cyan boundaries, zero rounded generic AI borders.
* **1-Click Evaluation Chips**: Preset prompts for immediate testing (`⚡ Pass: Quantum X Pro`, `⚡ Pass: 2x Pods`, `⚡ Reject: Budget Exceeded`, `⚡ Multi-Item`).
* **Live Telemetry**: Zero-polling Server-Sent Events (`/audit/stream`) updating the ledger and charts in real time.

---

## 5. Cloud Deployment & Docker Specifications (Render)

* **Web Service**: `agentic-commerce` on Render (`env: docker`).
* **Database**: `agentic-commerce-db` (PostgreSQL free tier).
* **Port Binding**: Dynamically reads `${PORT:-8000}`.
* **Startup Resilience**: 10-attempt connection retry loop in `src/database.py` with exponential backoff.
* **Root Domain Handling**: `GET /` automatically redirects directly to `/dashboard`.

---

## 6. Operator Demo Credentials & Access

| Field | Production Access Configuration |
| :--- | :--- |
| **Live URL** | [https://agentic-commerce-zyoy.onrender.com/dashboard](https://agentic-commerce-zyoy.onrender.com/dashboard) |
| **Username** | Configured via `OPERATOR_USERNAME` (default: `Razorpay`) |
| **Password** | Configured securely via deployment `OPERATOR_PASSWORD` environment variable |

---

## 7. Comprehensive Failure Taxonomy & Handling

The system handles 6 distinct failure categories with dedicated recovery workflows:

1. **Guardrail Rejection (`GUARDRAIL_REJECT`)**: Stated ceiling exceeded $\rightarrow$ Transaction blocked, explanatory reason returned.
2. **Session Budget Depletion (`BUDGET_EXCEEDED`)**: Multi-purchase limit breached $\rightarrow$ Session frozen, further charges locked.
3. **Price Drift / Catalog Mutation (`PRICE_DRIFT`)**: Hash mismatch $\rightarrow$ Order rejected, fresh catalog manifest returned.
4. **Duplicate Dispatch (`IDEMPOTENCY_HIT`)**: Network retry $\rightarrow$ Deduplicated via receipt key without second debit.
5. **Webhook Tampering (`WEBHOOK_MISMATCH`)**: Invalid HMAC signature $\rightarrow$ 401 Unauthorized, quarantined.
6. **Stalled Payment (`DEAD_LETTER`)**: Unconfirmed gateway order $\rightarrow$ Auto-reconciliation worker recovers or routes to DLQ.

---

## 8. Test Suite & CI/CD Pipeline

```text
tests/test_agent_evaluation.py ....................                      [ 50%]
tests/test_api_validation.py .................                           [ 92%]
tests/test_e2e_checkout.py ...                                           [100%]

======================= 40 passed, 3 warnings in 2.52s ========================
```

* **Automated CI**: GitHub Actions (`.github/workflows/ci.yml`) runs on every commit across Python 3.11/3.12 with PostgreSQL service containers.
* **Coverage**: End-to-end checkout, capability token tampering, out-of-budget attacks, rate limiting, trusted host filters, and webhook HMAC verification.

---
