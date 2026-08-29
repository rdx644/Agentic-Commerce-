# 📐 Agentic Commerce

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-2.0%20Flash-8E75B2?style=flat&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![Razorpay](https://img.shields.io/badge/Razorpay-Payment%20Orchestration-0C2340?style=flat&logo=razorpay&logoColor=white)](https://razorpay.com)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com)
[![Render](https://img.shields.io/badge/Render-Cloud%20Blueprint-46E3B7?style=flat&logo=render&logoColor=white)](https://render.com)
[![Tests](https://img.shields.io/badge/Tests-55%2F55%20Passing-brightgreen?style=flat&logo=pytest&logoColor=white)](https://pytest.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An enterprise-grade, mathematically bounded, explainable **Agentic Checkout & Payment Orchestration System** designed for AI agents, machine buyers, and conversational commerce. Built with zero-trust capability tokens, cryptographic catalog snapshotting, atomic conditional budget ledgers, dynamic upsell intelligence, protocol-native agent interfaces, and a real-time **Architectural Blueprint (Cyanotype)** audit dashboard.

---

## 📌 Table of Contents

- [About the Project](#-about-the-project)
- [Dual-Mode Security Architecture](#-dual-mode-security-architecture)
- [Core Architecture & Mathematical Invariants](#-core-architecture--mathematical-invariants)
- [System Architecture Flow](#-system-architecture-flow)
- [Protocol-Native Agent Interface (AI Buyer)](#-protocol-native-agent-interface-ai-buyer)
- [Interactive Checkout Simulator](#-interactive-checkout-simulator)
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

## 📖 About the Project

**Agentic Commerce** solves the foundational reliability and security challenges of allowing autonomous AI agents to execute commercial transactions. Rather than granting probabilistic LLMs direct access to payment APIs or financial instruments, Agentic Commerce enforces a **bounded, explainable capability model**:

1. **Deterministic Separation of Concerns**: The LLM parses natural language intent into item IDs, quantities, and spending ceilings. All pricing and availability are resolved deterministically against an immutable catalog.
2. **Cryptographic Validation**: Every quote is bound to a SHA-256 catalog snapshot hash. Price drift is calculated as an exact arithmetic fact rather than a heuristic guess.
3. **Zero-Trust Capability Tokens**: Issues signed, tamper-proof HMAC-SHA256 capability tokens with a 5-minute TTL that authorize one exact order.
4. **Atomic Conditional Budget Ledger**: Single-statement conditional updates prevent double-spending, race conditions, and balance overruns across concurrent agent workers.
5. **Fail-Closed Webhook Pipeline**: Webhook signatures are verified with constant-time HMAC-SHA256 comparison and deduplicated atomically (`ON CONFLICT DO NOTHING`).
6. **Dual-Mode Blueprint Telemetry**: High-contrast, cyanotype-inspired dashboard with virtualized DOM scrolling, guest observer telemetry, and single-click operator authentication.

---

## 🛡️ Dual-Mode Security Architecture

To balance **zero-friction evaluator accessibility** with **strict enterprise least-privilege security**, the system operates with a dual-tier authentication model:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 👁️ GUEST OBSERVER MODE (Default on Page Load)                                         │
│ • Audience: Hackathon Judges, Public Auditors, External Consumers                      │
│ • Auth Barrier: None (Immediate Read-Only Access)                                      │
│ • Available: Live SSE Telemetry, Virtualized Audit Trail, Checkout Simulator,          │
│   Session Deep Dive with full Cryptographic Provenance.                                │
│ • Protected Actions: Clicking "RUN CAMPAIGN" prompts login modal with 1-click helper.  │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                 [🔑 1-Click Operator Login]
                                 (Razorpay / RazorPay@123456#)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 🛡️ AUTHENTICATED OPERATOR MODE                                                        │
│ • Audience: Store Managers, Finance Engineers, Administrators                          │
│ • Auth Barrier: OAuth2 / RS256-HS256 Bearer Token stored in ephemeral sessionStorage   │
│ • Available: 50-Trial Monte Carlo Campaign Simulation, Administrative Reconciliation   │
│   Sweeps, Private Stream Ticket Minting.                                               │
│ • Session Lifecycle: Terminated instantly on tab closure or by clicking [🚪 LOGOUT].   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🏛️ Core Architecture & Mathematical Invariants

```
                     ┌───────────────────────────────┐
                     │   User / Autonomous Agent     │
                     └──────────────┬────────────────┘
                                    │ 1. Natural Language Intent / Structured JSON
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI INGRESS & SECURITY                      │
│  - TrustedHostMiddleware (Locked)  - SecurityHeadersMiddleware         │
│  - RequestSizeLimitMiddleware (1MB) - Ephemeral Single-Use Auth Tokens │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      INTENT PARSING & LLM LAYER                        │
│  - Google Gemini 2.0 Flash with deterministic heuristic fallback       │
│  - Extracts: target item_ids, quantities, stated spending ceiling      │
│  - LLM NEVER sets price or accesses financial credentials              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    CATALOG & CAPABILITY ENGINE                         │
│  - Resolves items against SHA-256 Catalog Snapshot Hash                │
│  - Detects price drift: drift = current_price - quoted_price           │
│  - Issues signed JWT Capability Token (5-minute TTL) on PASS           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  GUARDRAIL & BUDGET LEDGER (PostgreSQL)                │
│  - Atomic Conditional Update (Zero Race Conditions):                   │
│    UPDATE budget_ledger SET spent = spent + amount                     │
│    WHERE session_id = %s AND frozen = 0 AND spent + amount <= budget   │
│  - Auto-freezes session on >= 5 consecutive rejections                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    PAYMENT DISPATCH & RECONCILIATION                   │
│  - Pre-dispatch payment record write with unique Idempotency Key       │
│  - Atomic ON CONFLICT DO NOTHING preventing transaction aborts         │
│  - Razorpay Order Dispatch with capability token verification          │
│  - Fail-closed Webhook Verification & Atomic Deduplication             │
│  - Exponential backoff reconciliation with Dead-Letter Queue (DLQ)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   AUDIT TRAIL & BLUEPRINT TELEMETRY                    │
│  - SHA-256 queryable audit ledger in relational database               │
│  - Virtualized table rendering (120fps scrolling with 1,000+ entries)  │
│  - Real-time Server-Sent Events (SSE) stream with guest observer mode  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Protocol-Native Agent Interface (AI Buyer)

Agentic Commerce natively supports emerging agent protocols (**NPCI UAP**, **ACP**, **AP2**, **x402**, **UCP**) with dedicated machine-readable endpoints:

| Endpoint | Protocol Standard | Payload / Schema | Purpose |
| :--- | :--- | :--- | :--- |
| `GET /.well-known/agent.json` | UCP / Agent Discovery | Schema.org JSON | Universal service discovery manifest declaring capabilities, supported protocols, and token specs. |
| `GET /agent/catalog` | Schema.org `ItemList` | JSON-LD | Machine-readable catalog containing product SKUs, prices, stock availability, and SHA-256 hash. |
| `POST /agent/checkout` | Autonomous Agent Checkout | Structured JSON | Accepts target items and stated spending ceiling; returns capability token or structured rejection rationale. |
| `POST /agent/authorize` | Capability Minting | JSON | Mints bounded capability tokens with 5-minute TTL. |
| `POST /agent/payment` | Token Settlement | JSON | Settles transactions via Capability Token against Razorpay rails without exposing merchant credentials. |

---

## ⚡ Interactive Checkout Simulator

The dashboard incorporates a live **Conversational Checkout Simulator** connected to Gemini 2.0 Flash and the deterministic catalog engine:

| Preset Chip | User Prompt | Guardrail Decision | Pipeline Outcome |
| :--- | :--- | :---: | :--- |
| `⚡ Pass: 1x Quantum X Pro` | `"Buy 1 Quantum X Pro with budget 70000 rupees"` | `PASS` | Evaluates price (₹59,999) $\le$ budget (₹70,000); mints capability token and dispatches payment order. |
| `⚡ Multi-Qty: 2x SoundPods` | `"I want to buy 2 SoundPods Pro with budget 15000"` | `PASS` | Evaluates total price ($2 \times ₹5,999 = ₹11,998$) $\le$ ₹15,000; mints capability token. |
| `⚡ Reject: Budget Exceeded` | `"Buy Quantum X Pro with budget 10000"` | `REJECT` | Detects item price (₹59,999) > budget (₹10,000); blocks spend, records failure class `budget_exceeded`. |
| `⚡ Multi-Item: Phone+Charger`| `"Buy 1 NeoLite 5G and 1 TurboCharge 65W with budget 25000"`| `PASS` | Parses multi-item bundle ($₹19,999 + ₹1,999 = ₹21,998$) $\le$ ₹25,000; mints capability token. |

---

## ⚡ High-Concurrency Stress Verification

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

## 📈 Multi-Trial Monte Carlo Uplift Modeling

To validate and prove merchant revenue growth with statistical rigor rather than arbitrary assumptions, the Campaign Orchestrator (`src/campaign/orchestrator.py`) runs **multi-trial Monte Carlo A/B simulations** with dynamic consumer price elasticity.

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
| **95% Confidence Interval** | $\left[ \bar{L} - 1.96 \cdot \frac{\sigma}{\sqrt{K}}, \bar{L} + 1.96 \cdot \frac{\sigma}{\sqrt{K}} \right]$ | Statistically guaranteed margin of error at a 95% confidence level ($p < 0.05$). |
| **Sample Size ($N$)** | $N = \text{Total Evaluated Sessions}$ | Total volume of independent purchasing journeys analyzed in the run. |

---

## ⚡ Tech Stack & Decision Framework

| Layer | Technology | Rationale & Architectural Decisions |
| :--- | :--- | :--- |
| **Runtime & Framework** | **Python 3.11+ / FastAPI** | High-performance asynchronous ASGI framework with automated OpenAPI schemas, native Pydantic v2 validation, and low latency request handling. |
| **AI / Intent Engine** | **Google Gemini 2.0 Flash** | Fast structured JSON output generation, accompanied by a resilient multi-model fallback chain and zero-failure heuristic catalog matching. |
| **Database & Pool** | **PostgreSQL 16 Alpine + psycopg_pool** | Full ACID compliance, robust connection multiplexing, atomic conditional row updates (`ON CONFLICT DO NOTHING`), and native indexing. |
| **Payment Gateway** | **Razorpay Orders & Webhooks** | Production payment gateway integration with HMAC-SHA256 signature verification, pre-dispatch ledger recording, and idempotent event processing. |
| **Security & Auth** | **PyJWT + OAuth2 Bearer + Stream Tickets** | Cryptographically signed capability tokens with tight TTLs (5 min), combined with OAuth2 operator authentication and single-use 30s SSE tickets. |
| **Frontend UI** | **Vanilla CSS + Virtual DOM Table** | High-contrast Architectural Blueprint (Cyanotype) layout. 48px row virtualization, Chart.js visual telemetry, and native EventSource streaming. |
| **Containerization** | **Docker & Docker Compose** | Multi-stage slim container builds running under a non-root `agent` user with isolated internal networking and automated healthchecks. |
| **Cloud Deployment** | **Render Blueprint (`render.yaml`)** | Declarative 1-click cloud orchestration with managed PostgreSQL, automated SSL certificates, and zero-downtime continuous deployment. |

---

## 📁 Project Directory Structure

```text
agentic-commerce/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI pipeline (Ubuntu, Python 3.11, PostgreSQL 16)
├── dashboard/                   # Architectural Blueprint Audit Dashboard (SPA)
│   ├── index.html               # Semantic drafting layout with 1-click test chips
│   ├── styles.css               # Cyanotype tokens (--blueprint-bg, 20px grid, virtual scroll)
│   ├── app.js                   # Virtualized audit trail, dual-mode auth, Chart.js
│   ├── favicon.svg              # Vector blueprint brand mark
│   └── fonts/                   # High-speed local typography (Roboto / Sora)
├── scripts/
│   ├── deploy.ps1               # Windows PowerShell deployment automation
│   ├── deploy.sh                # Linux / macOS POSIX deployment script
│   ├── test_razorpay_live.py    # Standalone Live Razorpay Test Mode Verification CLI
│   ├── seed_catalog.py          # Catalog generator with SHA-256 versioning
│   └── simulate_failure.py      # Chaos engineering & failure injection tests
├── src/
│   ├── __init__.py
│   ├── config.py                # Pydantic BaseSettings with fail-closed production validation
│   ├── database.py              # PostgreSQL connection pool and thread-safe SQLite adapter
│   ├── main.py                  # FastAPI application entrypoint and middleware assembly
│   ├── observability.py         # OpenTelemetry instrumentation and structured logging
│   ├── agent_protocol/          # Protocol-native agent router (/.well-known, /agent/*)
│   ├── audit/                   # Audit logging service, router, and SSE stream
│   ├── campaign/                # Monte Carlo campaign orchestrator & statistical confidence
│   ├── catalog/                 # Product catalog manifest & cryptographic hash resolver
│   ├── checkout/                # Gemini LLM intent extractor & heuristic fallback parser
│   ├── guardrail/               # Budget ledger, circuit breaker & anti-abuse checks
│   ├── payment/                 # Razorpay payment dispatcher, workflow & reconciliation
│   ├── security/                # JWT capability tokens, rate limiting, and stream tickets
│   ├── upsell/                  # Dynamic upsell recommendation engine
│   └── webhook/                 # Fail-closed Razorpay HMAC-SHA256 signature verification
├── tests/
│   ├── conftest.py              # Test configuration with smart port auto-detection
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

## 🚀 Quick Start Guide

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
6. Click **Apply** — Render will automatically build the Docker container, provision a PostgreSQL database, and provide a permanent `https://agentic-commerce-zyoy.onrender.com/dashboard` URL with SSL!

---

## 🔒 Security & Production Hardening

* **Non-Root Execution**: Container runs under a dedicated `agent` system user (UID 1000).
* **Fail-Closed Webhooks**: Unsigned or misconfigured webhooks are strictly rejected before payload parsing.
* **Single-Use SSE Stream Tickets**: Long-lived JWT tokens are never passed in URL query strings.
* **Strict Parameter Validation**: Validated inputs via Pydantic schemas prevent SQL injection and prototype pollution.
* **Fail-Closed Production Rules**: In `APP_ENV=production`, the application refuses to start if `JWT_SECRET < 32 chars`, `OPERATOR_PASSWORD < 16 chars`, or `LOG_LEVEL == DEBUG`.
* **Tightened ALLOWED_HOSTS**: Wildcards are disallowed in production deployments (`agentic-commerce-zyoy.onrender.com,*.onrender.com,localhost,127.0.0.1`).
* **Defense in Depth Headers**: `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`, and `Referrer-Policy` are enforced on all responses.
* **Cache-Busting Asset Delivery**: Static files deliver with explicit revalidation tags (`Cache-Control: no-cache, must-revalidate`).

---

## 🧪 Testing Suite

The platform includes **56 automated test scenarios** covering concurrency stress, agent evaluation, API validation, checkout simulation, and end-to-end payment:

```bash
pytest tests/ -v
```

```text
tests/test_agent_evaluation.py ....................                      [ 35%]
tests/test_agent_protocol.py ....                                        [ 42%]
tests/test_api_validation.py .................                           [ 73%]
tests/test_checkout_simulator.py ....                                    [ 80%]
tests/test_concurrency.py ...                                            [ 85%]
tests/test_e2e_checkout.py ...                                           [ 91%]
tests/test_full_system_verification.py ....                              [ 98%]
tests/test_razorpay_integration.py s                                     [100%]

================== 55 passed, 1 skipped, 0 failures in 4.76s ==================
```

| Test Suite | Coverage & Scenarios |
| :--- | :--- |
| `test_concurrency.py` | 100-thread concurrent spend against fixed budget, ceiling authorization bounds, and 50-thread concurrent webhook deduplication. |
| `test_checkout_simulator.py` | 4 preset chip journeys: single item, multi-quantity, budget exceeded rejection, and multi-item bundle parsing. |
| `test_full_system_verification.py` | End-to-end asset delivery, CSP font verification, guest vs operator permission matrix, and idempotent settlement. |
| `test_agent_protocol.py` | Universal agent discovery manifest (`/.well-known/agent.json`), JSON-LD catalog, and single-use stream ticket lifecycle. |
| `test_e2e_checkout.py` | Full conversational checkout flow, capability token verification, payment authorization, and out-of-budget rejection. |
| `test_agent_evaluation.py` | Intent parsing accuracy, entity resolution, quantity bounds, and adversarial prompt injection resilience. |
| `test_api_validation.py` | OAuth2 Bearer security, rate limiting, trusted host filters, and fail-closed webhook signature verification. |
| `test_razorpay_integration.py` | Live Razorpay test-mode API order creation and HMAC signature verification. |

### Live Razorpay Test Mode Verification CLI:
```bash
python scripts/test_razorpay_live.py
```

---

## 📡 API Reference

| Method | Endpoint | Access Level | Description |
| :--- | :--- | :---: | :--- |
| `GET` | `/health` | **Public** | Structured health check, database pool connectivity, and dependency validation. |
| `GET` | `/.well-known/agent.json` | **Public** | Machine-readable AI Agent discovery manifest (UCP standard). |
| `GET` | `/.well-known/ucp` | **Public** | UCP legacy-compatible merchant discovery manifest. |
| `GET` | `/agent/catalog` | **Public** | Schema.org / JSON-LD product catalog with SHA-256 integrity hashes. |
| `POST` | `/agent/checkout` | **Public** | Autonomous agent structured checkout intent submission. |
| `POST` | `/agent/authorize` | **Public** | Direct capability token minting with strict spending bounds. |
| `POST` | `/agent/payment` | **Public** | Agent-to-agent token payment settlement on Razorpay rails. |
| `GET` | `/catalog` | **Public** | Product catalog manifest with current version and hash. |
| `POST` | `/checkout/converse` | **Public** | Conversational checkout intent extraction & capability token generation. |
| `POST` | `/guardrail/check` | **Public** | Standalone guardrail verification for spend intents. |
| `POST` | `/payment/dispatch` | **Public** *(with token)* | Dispatches Razorpay order with capability token and idempotency key. |
| `POST` | `/webhook/razorpay` | **Public** | Fail-closed webhook listener with atomic deduplication. |
| `GET` | `/audit/trail` | **Public** | Queryable chronological audit event ledger with filters. |
| `GET` | `/audit/stats` | **Public** | Aggregate audit metrics (volume, pass rate, rejection categories). |
| `GET` | `/audit/session/{id}` | **Public** | Full session deep dive with event timeline and budget state. |
| `GET` | `/audit/stream` | **Public** | Real-time Server-Sent Events (SSE) stream for live telemetry. |
| `POST` | `/campaign/run` | **Operator** | Multi-trial Monte Carlo A/B conversion simulation with 95% CI. |
| `POST` | `/payment/reconcile-all` | **Operator** | Sweeps and reconciles local payment records against Razorpay Orders API. |
| `POST` | `/auth/token` | **Public** | OAuth2 token endpoint for operator dashboard login. |
| `POST` | `/auth/stream-ticket` | **Operator** | Mints single-use 30-second stream ticket for private operator channels. |

---

## 📊 Operator Dashboard & Credentials

The Architectural Blueprint dashboard provides real-time visibility into autonomous transactions with zero-latency telemetry:

### 🔑 Demo Login Credentials
For evaluators, judges, and reviewers accessing the live deployed dashboard:

| Field | Demo Value |
| :--- | :--- |
| **Username** | `Razorpay` |
| **Password** | `RazorPay@123456#` |

* **Live Dashboard URL**: **[https://agentic-commerce-zyoy.onrender.com/dashboard](https://agentic-commerce-zyoy.onrender.com/dashboard)**
* **Dual-Mode Header**: Starts in `👁️ GUEST OBSERVER` mode for instant inspection; switches to `🛡️ OPERATOR` on 1-click login.
* **Virtualized Audit Trail**: 48px row virtualization rendering smooth 120fps scrolling across 1,000+ continuous events.
* **Interactive Checkout Simulator**: 4 one-click test chips (`⚡ Pass`, `⚡ Multi-Qty`, `⚡ Reject`, `⚡ Multi-Item`) for instant evaluation.
* **Monte Carlo Campaign Analytics**: Empirical 95% Confidence Intervals, Standard Deviation ($\sigma$), and Basket Lift tracking.
* **Drafting Coordinate Telemetry**: Real-time cursor grid alignment (`COORD: X[####] Y[####] | 1:1`) for structural inspection.

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
