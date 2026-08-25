# 📐 Agentic Commerce

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-3.6%20Flash-8E75B2?style=flat&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![Razorpay](https://img.shields.io/badge/Razorpay-Payment%20Orchestration-0C2340?style=flat&logo=razorpay&logoColor=white)](https://razorpay.com)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com)
[![Render](https://img.shields.io/badge/Render-Cloud%20Blueprint-46E3B7?style=flat&logo=render&logoColor=white)](https://render.com)
[![Tests](https://img.shields.io/badge/Tests-40%2F40%20Passing-brightgreen?style=flat&logo=pytest&logoColor=white)](https://pytest.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 📌 Table of Contents

- [About the Project](#-about-the-project)
- [Core Architecture & Security Design](#-core-architecture--security-design) 
- [System Architecture Flow](#-system-architecture-flow)
- [Tech Stack & Decision Framework](#-tech-stack--decision-framework)
- [Project Directory Structure](#-project-directory-structure)
- [Quick Start Guide](#-quick-start-guide)
  - [Option A: Automated Docker Deployment (Recommended)](#option-a-automated-docker-deployment-recommended)
  - [Option B: Native Local Development](#option-b-native-local-development)
  - [Option C: 1-Click Cloud Deployment (Render)](#option-c-1-click-cloud-deployment-render)
- [Security & Production Hardening](#-security--production-hardening)
- [Testing Suite](#-testing-suite)
- [API Reference](#-api-reference)
- [Operator Dashboard](#-operator-dashboard)

---

## 📖 About the Project

**Agentic Commerce** solves the critical reliability and security challenges of allowing autonomous AI agents to execute commercial transactions. Rather than granting LLMs direct access to payment APIs or financial instruments, Agentic Commerce implements a **bounded, explainable capability model**:

1. **Conversational Intent Extraction**: Google Gemini 3.6 Flash interprets natural language buying instructions into structured checkout requests with resilient heuristic fallback.
2. **Cryptographic Validation**: Product items, quantities, and prices are validated against immutable SHA-256 catalog snapshots.
3. **Zero-Trust Capability Tokens**: Generates tamper-proof, short-lived JWT tokens that strictly authorize specific purchases.
4. **Hard Budget Enforcement**: Atomic conditional database updates prevent balance overruns and double-spending across concurrent agent workers.
5. **Real-Time Blueprint Telemetry**: High-contrast, cyanotype-inspired audit dashboard with Server-Sent Events (SSE) streaming, live cursor coordinate mapping, and conversion analytics.

---

## 🏛️ Core Architecture & Security Design

```
                     ┌───────────────────────────────┐
                     │   User / Autonomous Agent     │
                     └──────────────┬────────────────┘
                                    │ 1. Natural Language Intent
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI INGRESS & MIDDLEWARE                    │
│  - TrustedHostMiddleware  - RateLimiter  - SecurityHeadersMiddleware   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      INTENT PARSING & LLM LAYER                        │
│  - Google Gemini 3.6 Flash / Heuristic Catalog Resolver                │
│  - Extracts: target item, quantity, max acceptable budget              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    CATALOG & CAPABILITY ENGINE                         │
│  - Validates item availability against Catalog Version (SHA-256 Hash)  │
│  - Mints short-lived (5 min) JWT Capability Token                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  GUARDRAIL & BUDGET LEDGER (PostgreSQL)                │
│  - Atomic UPDATE budget_ledger (WHERE spent + amount <= budget)        │
│  - Freezes session if consecutive rejections > 5                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    PAYMENT DISPATCH & RECONCILIATION                   │
│  - Razorpay Order Dispatch with Idempotency Key                        │
│  - Webhook HMAC-SHA256 Signature Verification                          │
│  - Exponential Backoff Auto-Reconciliation & Dead-Letter Queue (DLQ)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   AUDIT TRAIL & BLUEPRINT TELEMETRY                    │
│  - Immutable Chronological Event Log in PostgreSQL                     │
│  - Real-time Server-Sent Events (SSE) Stream -> Architectural Dashboard│
└────────────────────────────────────────────────────────────────────────┘
```

### Architectural Tenets:
* **LLMs Propose, Deterministic Systems Dispose**: The LLM *never* dispatches money directly. It parses intent; cryptographic tokens and relational ledgers validate and execute.
* **Two-Phase Commit Ledger**: Budget reservation and payment dispatch are decoupled and idempotent.
* **Fail-Closed Production Rules**: The application refuses to boot in production if secrets are missing, tokens are insecure, or debug logging is active.

---

## ⚡ Tech Stack & Decision Framework

| Layer | Technology | Rationale & Architectural Decisions |
| :--- | :--- | :--- |
| **Runtime & Framework** | **Python 3.11+ / FastAPI** | High-performance asynchronous ASGI framework with automated OpenAPI schemas, native Pydantic v2 validation, and low latency request handling. |
| **AI / Intent Engine** | **Google Gemini 3.6 Flash** | Sub-second response times, precise structured JSON output adherence, accompanied by a resilient multi-model fallback chain and zero-failure heuristic catalog matching. |
| **Database & Pool** | **PostgreSQL 16 Alpine + psycopg_pool** | Full ACID compliance, robust connection multiplexing, atomic conditional row updates, and native indexing for high-frequency audit streaming. |
| **Payment Gateway** | **Razorpay Orders & Webhooks** | Production payment gateway integration with HMAC-SHA256 signature verification, pre-dispatch ledger recording, and idempotent event processing. |
| **Security & Auth** | **PyJWT + OAuth2 Bearer** | Cryptographically signed capability tokens with tight TTLs (5 min), combined with OAuth2 operator authentication for administrative surfaces. |
| **Frontend UI** | **Vanilla CSS + SSE (No Bundler)** | High-contrast Architectural Blueprint (Cyanotype) layout. Zero bloated `node_modules` dependency chains, lightning-fast rendering, Chart.js visual telemetry, and native EventSource streaming. |
| **Containerization** | **Docker & Docker Compose** | Multi-stage slim container builds running under a non-root `agent` user with isolated internal networking and automated healthchecks. |
| **Cloud Deployment** | **Render Blueprint (`render.yaml`)** | Declarative 1-click cloud orchestration with managed PostgreSQL, automated SSL certificates, and zero-downtime continuous deployment. |

---

## 📁 Project Directory Structure

```text
agentic-commerce/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI pipeline (Pytest + Docker build)
├── dashboard/                   # Architectural Blueprint Audit Dashboard (SPA)
│   ├── index.html               # Semantic drafting layout with coordinate tracking
│   ├── styles.css               # Cyanotype color tokens (--blueprint-bg, 20px grid)
│   ├── app.js                   # Real-time SSE telemetry, Chart.js, Simulator
│   ├── favicon.svg              # Vector blueprint brand mark
│   └── fonts/                   # High-speed local typography (Roboto / Sora)
├── scripts/
│   ├── deploy.ps1               # Windows PowerShell 1-click deployment automation
│   ├── deploy.sh                # Linux / macOS / POSIX deployment script
│   ├── seed_catalog.py          # Catalog generator with SHA-256 versioning
│   ├── simulate_failure.py      # Chaos engineering & failure injection tests
│   └── build_graph_db.py        # Knowledge graph generation utility
├── src/
│   ├── __init__.py
│   ├── config.py                # Pydantic BaseSettings with fail-closed production validation
│   ├── database.py              # PostgreSQL connection pool and migration schemas
│   ├── main.py                  # FastAPI application entrypoint and middleware assembly
│   ├── observability.py         # OpenTelemetry instrumentation and structured logging
│   ├── audit/                   # Audit logging service, router, and SSE stream
│   ├── campaign/                # A/B testing campaign orchestrator & conversion lift
│   ├── catalog/                 # Product catalog manifest & cryptographic hash resolver
│   ├── checkout/                # Gemini LLM intent extractor & conversational checkout
│   ├── guardrail/               # Budget ledger, circuit breaker & anti-abuse checks
│   ├── payment/                 # Razorpay payment dispatcher, workflow & reconciliation
│   ├── security/                # JWT capability tokens, rate limiting, and auth guards
│   ├── upsell/                  # Dynamic upsell recommendation engine
│   └── webhook/                 # Razorpay HMAC-SHA256 signature verification handler
├── tests/
│   ├── conftest.py              # Test configuration and environment fixtures
│   ├── test_agent_evaluation.py # LLM benchmark and intent extraction validation
│   ├── test_api_validation.py   # HTTP status, security header, and auth tests
│   └── test_e2e_checkout.py     # Complete end-to-end checkout & payment integration
├── .dockerignore                # Build context exclusion rules
├── .env.example                 # Sanitized environment variable template
├── .gitignore                   # Git exclusion rules (prevents secret leaks)
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
* **Docker Desktop** (for containerized execution)
* **Git**

---

### Option A: Automated Docker Deployment (Recommended)

Run the automated single-command deployment pipeline:

**On Windows (PowerShell):**
```powershell
.\scripts\deploy.ps1
```

**On Linux / macOS:**
```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

This script will automatically:
1. Stop any stale containers.
2. Build the production Docker image with non-root security.
3. Start PostgreSQL 16 Alpine and wait for healthchecks.
4. Launch the FastAPI application on port `8000`.

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

Deploy permanently to Render using the included Infrastructure Blueprint:

1. Push your repository to GitHub.
2. Log into [**dashboard.render.com**](https://dashboard.render.com).
3. Click **New +** $\rightarrow$ select **Blueprint**.
4. Select your `Agentic-Commerce-` repository.
5. Provide your environment secrets (`RAZORPAY_KEY_ID`, `GEMINI_API_KEY`, etc.) when prompted.
6. Click **Apply** — Render will automatically build the Docker container, provision a PostgreSQL database, and give you a permanent `https://agentic-commerce.onrender.com/dashboard` URL with SSL!

---

## 🔒 Security & Production Hardening

* **Non-Root Execution**: Container runs under a dedicated `agent` system user (UID 1000).
* **Strict Parameter Validation**: Validated inputs via Pydantic schemas prevent SQL injection, path traversal, and prototype pollution.
* **Fail-Closed Configuration**: In `APP_ENV=production`, the application refuses to start if `JWT_SECRET < 32 chars`, `OPERATOR_PASSWORD < 16 chars`, or `LOG_LEVEL == DEBUG`.
* **HMAC-SHA256 Webhook Verification**: All incoming webhook events are cryptographically authenticated against `RAZORPAY_WEBHOOK_SECRET` before parsing.
* **Defense in Depth Headers**: `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`, and `Referrer-Policy` are enforced on all responses.

---

## 🧪 Testing Suite

The platform includes a comprehensive test suite covering unit, security, and end-to-end integration tests:

```bash
pytest tests/ -v
```

```text
tests/test_agent_evaluation.py ....................                      [ 50%]
tests/test_api_validation.py .................                           [ 92%]
tests/test_e2e_checkout.py ...                                           [100%]

======================= 40 passed, 3 warnings in 2.52s ========================
```

| Test Suite | Coverage & Scenarios |
| :--- | :--- |
| `test_e2e_checkout.py` | Full conversational checkout flow, capability token verification, payment authorization, and out-of-budget rejection. |
| `test_agent_evaluation.py` | Intent parsing accuracy, entity resolution, quantity bounds, and adversarial prompt resilience. |
| `test_api_validation.py` | OAuth2 Bearer security, rate limiting, trusted host filters, and webhook signature verification. |

---

## 📡 API Reference

| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Public | System status, database pool connectivity, and configuration checks. |
| `POST` | `/checkout/converse` | Public | Conversational checkout intent extraction & capability token generation. |
| `POST` | `/checkout/verify` | Public | Validates a capability token against catalog hash and budget ledger. |
| `POST` | `/payment/order` | Public | Dispatches Razorpay order with idempotency check. |
| `POST` | `/webhook/razorpay` | Public | Secure webhook listener for payment capture & refund events. |
| `POST` | `/campaign/run` | Operator | Triggers A/B conversion simulation batch. |
| `GET` | `/audit/logs` | Operator | Retrieves chronological audit event history. |
| `GET` | `/audit/events` | Operator | Server-Sent Events (SSE) real-time event stream for the dashboard. |
| `POST` | `/auth/token` | Public | OAuth2 token endpoint for operator dashboard authentication. |

---

## 📊 Operator Dashboard & Live Demo

The dashboard provides real-time visibility into autonomous transactions with zero-latency telemetry:

### 🔑 Demo Login Credentials
For evaluators, judges, and reviewers accessing the live deployed dashboard:

| Field | Demo Value |
| :--- | :--- |
| **Username** | `Razorpay` |
| **Password** | `RazorPay@123456#` |

> [!NOTE]
> In custom self-hosted deployments, operator credentials can be modified via the `OPERATOR_USERNAME` and `OPERATOR_PASSWORD` environment variables.

* **Live Audit Trail**: Chronological event logs with session hashes, action types, status badges, and execution rationale.
* **Interactive Checkout Simulator**: Natural language testing console to execute and monitor conversational agent purchases.
* **A/B Campaign Intelligence**: Live metric tracking comparing Baseline vs. Agentic Upsell conversion rates and basket lift.
* **Drafting Coordinate Tracker**: Real-time cursor grid alignment (`COORD: X[####] Y[####] | 1:1`) for structural audit precision.

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
