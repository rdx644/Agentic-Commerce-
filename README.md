#  Agentic Commerce

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-2.0%20Flash-8E75B2?style=flat&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![Razorpay](https://img.shields.io/badge/Razorpay-Payment%20Orchestration-0C2340?style=flat&logo=razorpay&logoColor=white)](https://razorpay.com)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com)
[![Render](https://img.shields.io/badge/Render-Cloud%20Blueprint-46E3B7?style=flat&logo=render&logoColor=white)](https://render.com)
[![Tests](https://img.shields.io/badge/Tests-100%20Passing%20(100%25)-brightgreen?style=flat&logo=pytest&logoColor=white)](https://pytest.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An enterprise-grade, mathematically bounded, explainable **Agentic Checkout & Payment Orchestration System** designed for AI agents, machine buyers, and conversational commerce. Built with zero-trust capability tokens, cryptographic catalog snapshotting, atomic conditional budget ledgers, dynamic upsell intelligence, protocol-native agent interfaces, central payment state machines, and a real-time **Architectural Blueprint (Cyanotype)** audit dashboard.

> **Core Architectural Invariant**:  
> *"Probabilistic AI decides what the buyer intends. Deterministic systems decide whether money may move."*

###  Live Deployment & Interactive Endpoints
*  **Live Audit Blueprint Dashboard**: **[https://agentic-commerce-zyoy.onrender.com/dashboard](https://agentic-commerce-zyoy.onrender.com/dashboard)**
*  **Interactive System Architecture Graph**: **[https://agentic-commerce-zyoy.onrender.com/graph](https://agentic-commerce-zyoy.onrender.com/graph)**
*  **Interactive OpenAPI Documentation**: Available in local/non-production mode (`http://localhost:8000/docs`); disabled in production.
*  **Agent Protocol Discovery Manifest**: **[https://agentic-commerce-zyoy.onrender.com/.well-known/agent.json](https://agentic-commerce-zyoy.onrender.com/.well-known/agent.json)**
*  **Evaluator Credentials**: `Razorpay` / `RazorPay@123456#` *(Demo-only evaluator credentials — not production secrets.)*

---

##  Table of Contents

- [About the Project](#-about-the-project)
- [Dual-Mode Security Architecture](#-dual-mode-security-architecture)
- [Core Architecture & Mathematical Invariants](#-core-architecture--mathematical-invariants)
- [System Architecture Flow](#-system-architecture-flow)
- [Protocol-Native Agent Interface (AI Buyer)](#-protocol-native-agent-interface-ai-buyer)
- [Interactive Checkout Simulator](#-interactive-checkout-simulator)
- [Interactive Architecture Blueprint Graph](#-interactive-architecture-blueprint-graph)
- [High-Concurrency Stress Verification](#-high-concurrency-stress-verification)
- [Multi-Trial Monte Carlo Uplift Modeling](#-multi-trial-monte-carlo-uplift-modeling)
- [Tech Stack & Decision Framework](#-tech-stack--decision-framework)
- [Project Directory Structure](#-project-directory-structure)
- [Quick Start Guide](#-quick-start-guide)
  - [Option A: Automated Docker Deployment (Recommended)](#option-a-automated-docker-deployment-recommended)
  - [Option B: Native Local Development](#option-b-native-local-development)
  - [Option C: 1-Click Cloud Deployment (Render)](#option-c-1-click-cloud-deployment-render)
- [Security & Production Hardening](#-security--production-hardening)
- [Testing Suite](#-testing-suite)
- [API Reference](#-api-reference)
- [Operator Dashboard & Credentials](#-operator-dashboard--credentials)

---

##  About the Project

> **Production Scope**: Designed as a controlled single-merchant agentic-commerce demonstration, not a multi-tenant payment platform.

**Agentic Commerce** solves the foundational reliability and security challenges of allowing autonomous AI agents to execute commercial transactions. Rather than granting probabilistic LLMs direct access to payment APIs or financial instruments, Agentic Commerce enforces a **bounded, explainable capability model**:

1. **Deterministic Separation of Concerns**: The LLM parses natural language intent into item IDs, quantities, and spending ceilings. All pricing and availability are resolved deterministically against an immutable catalog manifest.
2. **Cryptographic Catalog Snapshotting**: Every quote is bound to a SHA-256 catalog snapshot hash. Price drift is calculated as an exact arithmetic fact rather than a heuristic guess.
3. **Zero-Trust Capability Tokens**: Issues cryptographically signed HS256 JWT tokens with unique token IDs (`jti`), strict 5-minute TTL, server-determined merchant binding, item scope enforcement, and atomic single-use database consumption.
4. **Authoritative Central Payment State Machine**: All payment-status transitions route through `transition_payment_state()`. Direct SQL `UPDATE payment_records SET status = ...` is strictly banned. Terminal states (`CAPTURED`, `FAILED`, `DEAD_LETTER`) cannot regress.
5. **Fail-Closed Webhook Pipeline & Recovery**: Webhooks verify HMAC-SHA256 signatures over raw request bytes and fail closed if monetary fields (`amount`, `currency`) are missing or mismatched. Features durably tracked and recoverable webhook events across service restarts (`POST /webhook/recover`).
6. **Atomic Conditional Budget Ledger**: Single-statement conditional updates prevent double-spending, race conditions, and balance overruns across concurrent agent workers.
7. **Zero-Sink Blueprint Telemetry**: High-contrast, cyanotype-inspired dashboard with virtualized DOM scrolling, self-hosted D3 v7 and Chart.js 4.4.0, with no known unsafe DOM sinks in audited frontend assets, and strict Content Security Policy (`script-src 'self'`).

---

##  Dual-Mode Security Architecture

To balance **zero-friction evaluator accessibility** with **strict enterprise least-privilege security**, the system operates with a dual-tier authentication model:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  GUEST OBSERVER MODE (Default on Page Load)                                         │
│ • Audience: Hackathon Judges, Public Auditors, External Consumers                      │
│ • Auth Barrier: None (Immediate Public Visibility)                                     │
│ • Available: Live Aggregated Stats (/audit/stats), Sanitized Real-time SSE Stream,     │
│   Public Catalog Manifest, Interactive Blueprint Graph (/graph), Checkout Simulator.   │
│ • Protected Actions: Full Session Deep Dives and Raw Compliance Exports require login. │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                  [ Operator Login]
                        (Configured via Server Environment)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  AUTHENTICATED OPERATOR MODE                                                        │
│ • Audience: Store Managers, Finance Engineers, Compliance Auditors                     │
│ • Auth Barrier: OAuth2-style password authentication issuing HS256-signed bearer JWTs │
│ • Available: Full Session Deep Dives (/audit/session/{id}), Compliance Data Exports,    │
│   50-Trial Monte Carlo Campaign Simulation, Payment Reconciliation, DLQ Sweeps.        │
│ • Session Lifecycle: Terminated instantly on tab closure or by clicking [ LOGOUT].  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

##  Core Architecture & Mathematical Invariants

```
                     ┌───────────────────────────────┐
                     │   User / Autonomous Agent     │
                     └──────────────┬────────────────┘
                                    │ 1. Natural Language Intent / Structured JSON (Max 1,000 chars)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI INGRESS & SECURITY                      │
│  - TrustedHostMiddleware (Locked)  - SecurityHeadersMiddleware (CSP)   │
│  - RequestSizeLimitMiddleware (1MB) - In-Memory Sliding Rate Limiter   │
│  - Ephemeral OAuth2 Bearer Tokens  - Zero 'unsafe-inline' scripts      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      INTENT PARSING & LLM LAYER                        │
│  - Google Gemini 2.0 Flash with deterministic heuristic fallback       │
│  - Extracts: target item_ids, quantities, stated spending ceiling      │
│  - Input clamped to MAX_NL_MESSAGE_LENGTH (1,000 chars)                │
│  - LLM NEVER sets price or accesses financial credentials              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    CATALOG & CAPABILITY ENGINE                         │
│  - Resolves items against SHA-256 Catalog Snapshot Hash                │
│  - Bounded to unified MAX_PAYMENT_PAISE = 100,000,000 (₹10,00,000)     │
│  - Detects price drift: drift = current_price - quoted_price           │
│  - Issues signed HS256 Capability Token (5-minute TTL) on PASS         │
│  - Server-determined merchant binding + allowed_item_ids enforcement   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  GUARDRAIL & BUDGET LEDGER (PostgreSQL)                │
│  - Atomic Conditional Update (Zero Race Conditions):                   │
│    UPDATE budget_ledger SET spent = spent + amount                     │
│    WHERE session_id = %s AND frozen = 0 AND spent + amount <= budget   │
│  - Auto-freezes session on >= 5 consecutive rejections                 │
│  - Atomic single-use token burn (consumed_at = CURRENT_TIMESTAMP)      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                CENTRAL PAYMENT STATE MACHINE & GATEWAY                 │
│  - All payment transitions route through transition_payment_state()    │
│  - Zero direct SQL status updates; terminal states cannot regress      │
│  - Exact amount match + capability token idempotency key derivation    │
│  - Fail-closed Webhook Verification (HMAC-SHA256 + amount/currency)    │
│  - Durably tracked and recoverable webhook events (RECEIVED -> DONE)   │
│  - Exponential backoff reconciliation with Dead-Letter Queue (DLQ)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   AUDIT TRAIL & BLUEPRINT TELEMETRY                    │
│  - Append-only, queryable audit trail in PostgreSQL                    │
│  - Operator-authenticated session deep dive (/audit/session/{id})      │
│  - Sanitized real-time Server-Sent Events (SSE) telemetry stream       │
│  - No known unsafe DOM sinks in audited frontend assets; local D3/Chart│
└────────────────────────────────────────────────────────────────────────┘
```

---

##  Protocol-Native Agent Interface (AI Buyer)

Agent-native interfaces aligned with emerging agent-commerce protocols including UAP/ACP/AP2/x402/UCP:

| Endpoint | Protocol Standard | Payload / Schema | Purpose |
| :--- | :--- | :--- | :--- |
| `GET /.well-known/agent.json` | UCP / Agent Discovery | Schema.org JSON | Universal service discovery manifest declaring capabilities, supported protocols, and token specs. |
| `GET /.well-known/ucp` | UCP Discovery | JSON | Legacy-compatible merchant capability declaration. |
| `GET /agent/catalog` | Schema.org `ItemList` | JSON-LD | Machine-readable catalog containing product SKUs, prices, stock availability, and SHA-256 hash. |
| `POST /agent/checkout` | Autonomous Agent Checkout | Structured JSON | Accepts target items and stated spending ceiling; returns capability token or structured rejection rationale. |
| `POST /agent/authorize` | Capability Minting | JSON | Mints bounded capability tokens with 5-minute TTL and server merchant binding. |
| `POST /agent/payment` | Token Settlement | JSON | Settles transactions via Capability Token against Razorpay rails without exposing merchant credentials. |

---

##  Interactive Checkout Simulator

The dashboard incorporates a live **Conversational Checkout Simulator** connected to Gemini 2.0 Flash and the deterministic catalog engine:

| Preset Chip | User Prompt | Guardrail Decision | Pipeline Outcome |
| :--- | :--- | :---: | :--- |
| ` Pass: 1x Quantum X Pro` | `"Buy 1 Quantum X Pro with budget 70000 rupees"` | `PASS` | Evaluates price (₹59,999) $\le$ budget (₹70,000); mints capability token and dispatches payment order. |
| ` Multi-Qty: 2x SoundPods` | `"I want to buy 2 SoundPods Pro with budget 15000"` | `PASS` | Evaluates total price ($2 \times ₹5,999 = ₹11,998$) $\le$ ₹15,000; mints capability token. |
| ` Reject: Budget Exceeded` | `"Buy Quantum X Pro with budget 10000"` | `REJECT` | Detects item price (₹59,999) > budget (₹10,000); blocks spend, records failure class `budget_exceeded`. |
| ` Multi-Item: Phone+Charger`| `"Buy 1 NeoLite 5G and 1 TurboCharge 65W with budget 25000"`| `PASS` | Parses multi-item bundle ($₹19,999 + ₹1,999 = ₹21,998$) $\le$ ₹25,000; mints capability token. |

---

##  Interactive Architecture Blueprint Graph

The full architectural blueprint is served as an interactive, force-directed graph visualization powered by local D3.js:

* **Direct Route**: [`https://agentic-commerce-zyoy.onrender.com/graph`](https://agentic-commerce-zyoy.onrender.com/graph) (or `/architecture-graph`)
* **Zero External CDNs**: Scripts load exclusively from `/dashboard/static/d3.min.js`.
* **Zero Dangerous DOM Sinks**: Clean DOM element creation with `textContent` with no known unsafe DOM sinks in audited frontend assets.
* **Component Inspection**: Click on any node (Client, Security, AI Gateway, Catalog, Ledger, Payment Gateway) to view its mathematical constraints, security boundary, and code implementation path.

---

##  High-Concurrency Stress Verification

The system includes dedicated multi-threaded concurrency stress tests (`tests/test_concurrency.py`) to verify financial and ledger invariants under heavy transaction contention:

### 100-Thread Concurrent Spend Scenario
* **Configured Session Budget**: ₹10,000 (1,000,000 paise)
* **Concurrent Contenders**: 100 simultaneous threads attempting to charge ₹1,000 (100,000 paise) each.
* **Empirical Execution Result**:
  * **Total Authorized Amount**: `10 × ₹1,000 = ₹10,000` (Exactly matches budget limit)
  * **Successful Debits**: `10`
  * **Gated / Rejected Debits**: `90` (`BUDGET_EXCEEDED` / `SESSION_FROZEN`)
  * **Financial Overspend**: **₹0.00**
* **Underlying Mechanism**: Atomic single-statement database operations (`UPDATE budget_ledger SET spent = spent + amount WHERE spent + amount <= budget`) guarantee zero race conditions without requiring slow distributed application locks.

---

##  Multi-Trial Monte Carlo Uplift Modeling

To simulate potential merchant uplift under defined assumptions with statistical rigor, the Campaign Orchestrator (`src/campaign/orchestrator.py`) runs **multi-trial Monte Carlo A/B simulations** with dynamic consumer price elasticity.

### 1. Dynamic Price-Elasticity Formulation
Instead of hardcoding a static conversion rate, the model dynamically computes the acceptance probability $P(\text{Acceptance})$ based on the ratio between the add-on item's price and remaining budget headroom:

$$P(\text{Acceptance}) = \beta \cdot \left(1 - \left(\frac{\text{Offer Price}}{\text{Remaining Budget Headroom}}\right)^{1.5}\right) + \epsilon$$

Where:
* $\beta$: Base upsell receptivity coefficient ($0.65$).
* $\text{Remaining Headroom} = \text{Stated Budget} - \text{Primary Order Amount}$.
* $\epsilon$: Uniform stochastic perturbation ($[-0.05, +0.05]$) simulating behavioral variance.
* If $\text{Offer Price} > \text{Remaining Headroom}$, $P(\text{Acceptance}) = 0$ (Hard Guardrail Enforcement).

### 2. Multi-Trial Statistical Confidence Metrics
For every campaign simulation run across baseline and agentic cohorts, $K$ independent randomized trials are computed:

| Metric | Formula | Description |
| :--- | :--- | :--- |
| **Mean Revenue Lift ($\bar{L}$)** | $\bar{L} = \frac{1}{K} \sum_{k=1}^{K} \text{Lift}_k$ | Average percentage uplift in merchant gross merchandise value across all simulation trials. |
| **Standard Deviation ($\sigma$)** | $\sigma = \sqrt{\frac{1}{K-1} \sum_{k=1}^{K} (\text{Lift}_k - \bar{L})^2}$ | Measures trial-to-trial variance and distribution stability under stochastic demand. |
| **95% Confidence Interval** | $\left[ \bar{L} - 1.96 \cdot \frac{\sigma}{\sqrt{K}}, \bar{L} + 1.96 \cdot \frac{\sigma}{\sqrt{K}} \right]$ | Estimated under the simulation assumptions at a 95% confidence level ($p < 0.05$). |
| **Sample Size ($N$)** | $N = \text{Total Evaluated Sessions}$ | Total volume of independent purchasing journeys analyzed in the run (capped at $N \le 200$). |

---

##  Tech Stack & Decision Framework

| Layer | Technology | Rationale & Architectural Decisions |
| :--- | :--- | :--- |
| **Runtime & Framework** | **Python 3.11+ / FastAPI** | High-performance asynchronous ASGI framework with automated OpenAPI schemas, native Pydantic v2 validation, and low-latency request handling. |
| **AI / Intent Engine** | **Google Gemini 2.0 Flash** | Fast structured JSON output generation, bounded inputs (1,000 chars), accompanied by a resilient multi-model fallback chain and heuristic matching. |
| **Database & Pool** | **PostgreSQL 16 Alpine + psycopg_pool** | PostgreSQL required in production; SQLite is development/test only. Full ACID compliance, connection multiplexing, and idempotent forward schema migrations. |
| **Payment Gateway** | **Razorpay Orders & Webhooks** | Razorpay test-mode payment integration with HMAC-SHA256 signature verification, central state machine gating, and fail-closed monetary validation. |
| **Security & Auth** | **PyJWT + Bearer Auth + Rate Limiting** | Cryptographically signed HS256 capability tokens with tight TTLs (5 min), combined with OAuth2-style password authentication issuing HS256-signed bearer JWTs, single-use 30s SSE tickets, and in-memory sliding-window rate limiting for the single-instance deployment. |
| **Frontend UI** | **Vanilla CSS + Safe Virtual DOM Table** | High-contrast Architectural Blueprint (Cyanotype) layout. 48px row virtualization, local Chart.js 4.4.0, local D3.js v7, and zero innerHTML sinks. |
| **Containerization** | **Docker & Docker Compose** | Multi-stage slim container builds running under a dedicated non-root `agent` user (UID 1000) with health checks. |
| **Cloud Deployment** | **Render Blueprint (`render.yaml`)** | Automated deployment with managed PostgreSQL, automated SSL, zero-downtime container rollouts, and `autoDeploy: true`. |

---

##  Project Directory Structure

```text
agentic-commerce/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI pipeline (Ubuntu, Python 3.11, PostgreSQL 16, Zero-Sink Linter)
├── dashboard/                   # Architectural Blueprint Audit Dashboard (SPA)
│   ├── index.html               # Semantic drafting layout with 1-click test chips
│   ├── styles.css               # Cyanotype tokens (--blueprint-bg, 20px grid, virtual scroll)
│   ├── app.js                   # Virtualized audit trail, dual-mode auth, Chart.js, safe DOM nodes
│   ├── d3.min.js                # Official self-hosted D3 v7 minified bundle (279 KB)
│   ├── chart.min.js             # Official self-hosted Chart.js v4.4.0 bundle (205 KB)
│   ├── architecture_graph.html  # Interactive Blueprint force-directed graph
│   ├── favicon.svg              # Vector blueprint brand mark
│   └── fonts/                   # High-speed local typography (Roboto / Sora)
├── scripts/
│   ├── deploy.ps1               # Windows PowerShell deployment automation
│   ├── deploy.sh                # Linux / macOS POSIX deployment script
│   ├── test_razorpay_live.py    # Standalone Live Razorpay Test Mode Verification CLI
│   ├── seed_catalog.py          # Catalog generator with SHA-256 versioning
│   ├── generate_graph_html.py   # Safe DOM architecture graph generator
│   └── simulate_failure.py      # Chaos engineering & failure injection tests
├── src/
│   ├── __init__.py
│   ├── config.py                # Pydantic BaseSettings with fail-closed production validation
│   ├── database.py              # PostgreSQL connection pool with idempotent forward migrations
│   ├── main.py                  # FastAPI application entrypoint, graph routes, and middleware assembly
│   ├── observability.py         # OpenTelemetry instrumentation and structured logging
│   ├── agent_protocol/          # Protocol-native agent router (/.well-known, /agent/*)
│   ├── audit/                   # Audit logging service, operator session inspection, and SSE stream
│   ├── campaign/                # Monte Carlo campaign orchestrator & statistical confidence
│   ├── catalog/                 # Product catalog manifest & cryptographic hash resolver
│   ├── checkout/                # Gemini LLM intent extractor & bounded heuristic fallback parser
│   ├── guardrail/               # Budget ledger, circuit breaker & anti-abuse checks
│   ├── payment/                 # State machine, Razorpay dispatcher, and durable reconciliation
│   │   ├── state_machine.py     # Authoritative transition_payment_state() (zero direct SQL)
│   │   ├── service.py           # Single payment boundary, merchant binding & item scope
│   │   ├── reconciliation.py    # Fail-closed payment record reconciliation & DLQ
│   │   └── models.py            # Unified MAX_PAYMENT_PAISE and payment schemas
│   ├── security/                # JWT capability tokens, sliding-window rate limiter, stream tickets
│   ├── upsell/                  # Dynamic upsell recommendation engine
│   └── webhook/                 # Fail-closed HMAC-SHA256 verification & durably tracked and recoverable webhook events
├── tests/
│   ├── conftest.py              # Test configuration with smart port auto-detection
│   ├── test_submission_security.py # 18 security regression tests (state machine, tokens, DOM, webhooks)
│   ├── test_checkout_simulator.py # Simulator chip preset integration tests
│   ├── test_concurrency.py      # 100-thread concurrent spend & deduplication stress tests
│   ├── test_full_system_verification.py # End-to-end judge verification & asset pipeline tests
│   ├── test_razorpay_integration.py # Live Razorpay test-mode API integration tests
│   ├── test_agent_evaluation.py # LLM benchmark and intent extraction validation
│   ├── test_api_validation.py   # HTTP status, security header, and auth tests
│   └── test_e2e_checkout.py     # Complete end-to-end checkout & payment integration
├── Dockerfile                   # Multi-stage production container definition
├── docker-compose.yml           # Multi-container orchestration (App + PostgreSQL 16)
├── pyproject.toml               # Python project configuration
├── render.yaml                  # 1-Click Render Cloud Infrastructure Blueprint
└── requirements.txt             # Locked production dependencies
```

---

##  Quick Start Guide

### Prerequisites
* **Python 3.11+**
* **Docker Desktop** (optional for local containers)
* **Git**

---

### Option A: Automated Docker Deployment (Recommended)

**On Windows (PowerShell):**
```powershell
.\scripts\deploy.ps1
```

**On Linux / macOS:**
```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

---

### Option B: Native Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/rdx644/Agentic-Commerce-.git
   cd Agentic-Commerce-
   ```

2. **Create a virtual environment & install dependencies:**
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   ```
   *Update `.env` with your `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `GEMINI_API_KEY`.*

4. **Start the application:**
   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

### Option C: 1-Click Cloud Deployment (Render)

1. Push your repository to GitHub.
2. Log into [**dashboard.render.com**](https://dashboard.render.com).
3. Click **New +** $\rightarrow$ select **Blueprint**.
4. Select your `Agentic-Commerce-` repository.
5. Provide your environment secrets (`RAZORPAY_KEY_ID`, `GEMINI_API_KEY`, etc.) when prompted.
6. Click **Apply** — Render automatically builds the Docker container, provisions managed PostgreSQL, and provides a permanent `https://agentic-commerce-zyoy.onrender.com/dashboard` URL with SSL!

---

##  Security & Production Hardening

* **Central Payment State Machine**: All payment-status transitions route through `transition_payment_state()`. Zero direct SQL `UPDATE payment_records SET status = ...` exist repository-wide. Terminal states (`CAPTURED`, `FAILED`, `DEAD_LETTER`) cannot regress.
* **Server-Determined Merchant Binding**: Payment dispatch validates `token_payload.merchant_id == trusted_merchant_id` and strictly verifies item IDs against `token_payload.allowed_item_ids`.
* **Fail-Closed Webhook Validation & Recovery**: Missing or mismatched `amount` or `currency` immediately fails closed with `WEBHOOK_MISMATCH` audit logging. Webhooks are durably tracked and recoverable webhook events (`processing_status`) across service restarts.
* **Database Architecture**: PostgreSQL required in production; SQLite is development/test only. In `APP_ENV=production`, SQLite fallback is strictly blocked via Pydantic validators and startup `RuntimeError`.
* **Zero Dangerous DOM Sinks**: Completely eliminated all `innerHTML`, `outerHTML`, `document.write`, and `eval()` sinks, with no known unsafe DOM sinks in audited frontend assets. Self-hosted D3 v7 and Chart.js 4.4.0 ensure strict script isolation.
* **Transactional HTTP Rate Limiter**: In-memory sliding-window rate limiting for the single-instance deployment limits traffic to `/auth/token`, `/checkout/converse`, `/agent/*`, `/payment/dispatch`, and `/upsell/*`.
* **Bounded AI Inputs**: Natural language messages clamped to 1,000 characters; simulation runs capped at 200 sessions.
* **Non-Root Execution**: Container runs under a dedicated `agent` system user (UID 1000).
* **Strict Parameter Validation**: Validated inputs via Pydantic v2 schemas prevent SQL injection and prototype pollution.
* **Defense in Depth Headers**: `Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'` enforced on all responses.

---

##  Testing Suite

The platform includes **101 automated test scenarios** (**100 passed, 1 skipped** when live Razorpay API keys are not in environment) covering concurrency stress, agent evaluation, capability token lifecycles, catalog immutability, fail-closed webhooks, production config security, UI simulator flows, and end-to-end payment:

```bash
pytest tests/ -q
```

```text
======================================================================
100 passed, 1 skipped in 15.74s (100% PASS RATE)
======================================================================
```

| Test Suite | Scenarios & Verifications |
| :--- | :--- |
| `test_simulator_flows.py` | **7 tests**: End-to-end simulation of all 4 UI preset chips (single item, multi-quantity, budget-exceeded rejection, multi-item cart), operator auth & provenance inspection, 50-trial Monte Carlo execution, and ledger reconciliation. |
| `test_submission_security.py` | **18 tests**: Single payment boundary verification, central state machine legal/illegal transitions, conflicting payment ID overwrite rejection, merchant binding rejection, item scope mismatch rejection, fail-closed webhook monetary consistency, durable webhook recovery, operator session privacy, production SQLite ban, rate limiting, and zero DOM sinks. |
| `test_security_config.py` | Production fail-closed environment validation, secret length & entropy enforcement, forbidden default credential auditing. |
| `test_capability_tokens.py` | Single-use cryptographic capability tokens, DB persistence, atomic burning on payment, tamper protection, and idempotency reuse. |
| `test_catalog_immutability.py` | Immutable catalog snapshots, deterministic SHA-256 integrity hashing, conflict rejection on price/item mutation. |
| `test_concurrency.py` | 100-thread concurrent spend against fixed budget, ceiling authorization bounds, and 50-thread concurrent webhook deduplication. |
| `test_checkout_simulator.py` | 4 preset chip journeys: single item, multi-quantity, budget exceeded rejection, and multi-item bundle parsing. |
| `test_full_system_verification.py` | End-to-end asset delivery, CSP font verification, guest vs operator permission matrix, and idempotent settlement. |
| `test_agent_evaluation.py` | Intent parsing accuracy, entity resolution, quantity bounds, and adversarial prompt injection resilience. |
| `test_api_validation.py` | OAuth2 Bearer security, rate limiting, trusted host filters, and fail-closed webhook signature verification. |
| `test_e2e_checkout.py` | Full conversational checkout flow, capability token verification, payment authorization, and out-of-budget rejection. |
| `test_razorpay_integration.py` | Live Razorpay test-mode API order creation and HMAC signature verification. |

### Live Razorpay Test Mode Verification CLI:
```bash
python scripts/test_razorpay_live.py
```

---

##  API Reference

| Method | Endpoint | Access Level | Description |
| :--- | :--- | :---: | :--- |
| `GET` | `/health` | **Public** | Structured health check, database pool connectivity, and dependency validation. |
| `GET` | `/.well-known/agent.json` | **Public** | Machine-readable AI Agent discovery manifest (UCP standard). |
| `GET` | `/.well-known/ucp` | **Public** | UCP discovery manifest for agentic commerce agents. |
| `GET` | `/agent/catalog` | **Public** | Schema.org / JSON-LD product catalog with SHA-256 integrity hashes. |
| `POST` | `/agent/checkout` | **Public** *(Rate Limited)* | Autonomous agent structured checkout intent submission. |
| `POST` | `/agent/authorize` | **Public** *(Rate Limited)* | Direct capability token minting with strict spending bounds. |
| `POST` | `/agent/payment` | **Public** *(Rate Limited)* | Agent-to-agent token payment settlement on Razorpay rails. |
| `GET` | `/catalog` | **Public** | Product catalog manifest with current version and hash. |
| `POST` | `/checkout/converse` | **Public** *(Rate Limited)* | Conversational checkout intent extraction & capability token generation. |
| `POST` | `/guardrail/check` | **Public** | Standalone guardrail verification for spend intents. |
| `POST` | `/payment/dispatch` | **Public** *(Rate Limited)* | Dispatches Razorpay order with capability token and idempotency key. |
| `POST` | `/webhook/razorpay` | **Public** | Fail-closed webhook listener with atomic deduplication. |
| `POST` | `/webhook/recover` | **Operator** | Recovers unhandled or failed webhook events from durable queue. |
| `GET` | `/audit/trail` | **Public** | Append-only, queryable audit trail event ledger with filters. |
| `GET` | `/audit/stats` | **Public** | Aggregate audit metrics (volume, pass rate, rejection categories). |
| `GET` | `/audit/session/{id}` | **Operator** | Detailed session provenance deep dive with complete timeline. |
| `GET` | `/audit/export` | **Operator** | High-limit compliance audit data export. |
| `GET` | `/audit/stream` | **Public** | Real-time Server-Sent Events (SSE) stream (sanitized tokens). |
| `GET` | `/graph` | **Public** | Interactive force-directed architecture graph blueprint (local D3). |
| `GET` | `/dashboard` | **Public** | Architectural Blueprint Audit Dashboard SPA. |
| `POST` | `/campaign/run` | **Operator** | Multi-trial Monte Carlo A/B conversion simulation with 95% CI. |
| `POST` | `/payment/reconcile-all` | **Operator** | Sweeps and reconciles local payment records against Razorpay Orders API. |
| `POST` | `/auth/token` | **Public** *(Rate Limited)* | OAuth2-style password token endpoint issuing HS256-signed bearer JWTs. |
| `POST` | `/auth/stream-ticket` | **Operator** | Mints single-use 30-second stream ticket for private operator channels. |

---

##  Operator Dashboard & Credentials

The Architectural Blueprint dashboard provides real-time visibility into autonomous transactions with zero-latency telemetry:

###  Demo Operator Credentials (For Evaluators & Judges)
> **Notice**: *Demo-only evaluator credentials — not production secrets.*

For evaluators, judges, and reviewers accessing the live deployed dashboard:

| Field | Demo Value | Description |
| :--- | :--- | :--- |
| **Username** | `Razorpay` | Demo-only operator administrative account |
| **Password** | `RazorPay@123456#` | Demo-only evaluator credentials — not production secrets. (Configured in Render cloud deployment) |

> **Evaluator 1-Click Walkthrough**:
> 1. Open the live dashboard: **[https://agentic-commerce-zyoy.onrender.com/dashboard](https://agentic-commerce-zyoy.onrender.com/dashboard)**.
> 2. By default, the interface loads in **` GUEST OBSERVER`** mode allowing public aggregate stats inspection, live telemetry, and checkout simulation.
> 3. Click the **` OPERATOR LOGIN`** button in the top right corner.
> 4. Enter Username: `Razorpay` and Password: `RazorPay@123456#` to authenticate.
> 5. **Inspect Session Deep Dive**: Click any row in the **Live Audit Trail** table to view the full session provenance timeline, budget state, and payment records for that session.
> 6. **Run Campaign**: Click **` RUN CAMPAIGN`** to trigger a 50-trial Monte Carlo A/B conversion simulation with real-time Chart.js visual telemetry.
> 7. **Interactive Blueprint**: Visit **[https://agentic-commerce-zyoy.onrender.com/graph](https://agentic-commerce-zyoy.onrender.com/graph)** to inspect the force-directed D3 system topology.

* **Dual-Mode Header**: Starts in ` GUEST OBSERVER` mode for instant inspection; switches to ` OPERATOR` on login.
* **Virtualized Audit Trail**: 48px row virtualization rendering smooth 120fps scrolling across 1,000+ continuous events.
* **Interactive Checkout Simulator**: 4 one-click test chips (` Pass`, ` Multi-Qty`, ` Reject`, ` Multi-Item`) for instant evaluation.
* **Monte Carlo Campaign Analytics**: Empirical 95% Confidence Intervals, Standard Deviation ($\sigma$), and Basket Lift tracking.

---

##  License

Distributed under the **MIT License**. See `LICENSE` for more information.
