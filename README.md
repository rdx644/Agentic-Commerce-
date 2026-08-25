# Agentic Commerce

A FastAPI reference implementation for bounded, explainable checkout and payment orchestration.

## Run locally

```powershell
Copy-Item .env.example .env
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/dashboard` for the audit console. Run `python -m pytest -q` to execute the test suite.

## Deploy with Docker

Build the image, then provide production secrets and the public perimeter explicitly:

```powershell
docker build -t agentic-commerce .
docker run --rm -p 8000:8000 -v agentic-commerce-data:/data `
  -e APP_ENV=production `
  -e JWT_SECRET=<unique-32-plus-character-secret> `
  -e RAZORPAY_KEY_ID=<key-id> `
  -e RAZORPAY_KEY_SECRET=<key-secret> `
  -e RAZORPAY_WEBHOOK_SECRET=<webhook-secret> `
  -e OPERATOR_USERNAME=<operator-name> `
  -e OPERATOR_PASSWORD=<unique-16-plus-character-operator-secret> `
  -e ALLOWED_HOSTS=commerce.example.com `
  -e CORS_ORIGINS=https://commerce.example.com `
  agentic-commerce
```

The application refuses to start in production with a default/short JWT secret, absent Razorpay or operator secrets, or debug logging. The dashboard, audit APIs, campaign controls, reconciliation, and guardrail session administration require HTTP Basic operator authentication; browsers handle this same-origin credential without exposing it to dashboard JavaScript. It serves `/health` for container orchestration. SQLite is appropriate for a single instance with a persistent volume; use a managed transactional database before horizontally scaling the payment workload.
