#!/usr/bin/env bash
# ==============================================================================
# Automated Docker Deployment Pipeline (Linux / macOS / Cloud)
# ==============================================================================
set -euo pipefail

echo -e "\033[1;36m======================================================"
echo -e "🚀 Starting Automated Agentic Commerce Deployment..."
echo -e "======================================================\033[0m"

# Step 1: Check .env file
if [ ! -f ".env" ]; then
    echo -e "\033[1;33m⚠️ .env file not found! Copying from .env.example...\033[0m"
    cp .env.example .env
fi

# Step 2: Stop old containers
echo -e "\n\033[1;32m[1/4] Stopping existing containers...\033[0m"
docker compose down --remove-orphans

# Step 3: Build & Launch Stack
echo -e "\n\033[1;32m[2/4] Building image and starting services in background...\033[0m"
docker compose up --build -d

# Step 4: Healthcheck Polling
echo -e "\n\033[1;32m[3/4] Waiting for services to become healthy...\033[0m"
HEALTHY=false
for i in {1..15}; do
    sleep 2
    if curl -s -f http://127.0.0.1:8000/health > /dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    echo "  ... waiting for backend initialization ($i/15)"
done

if [ "$HEALTHY" = true ]; then
    echo -e "\n\033[1;32m[4/4] 🌟 Deployment Succeeded!\033[0m"
    echo -e "\033[1;36m------------------------------------------------------\033[0m"
    echo -e "🌐 API Root:   http://localhost:8000"
    echo -e "📊 Dashboard:  http://localhost:8000/dashboard"
    echo -e "❤️ Health:     http://localhost:8000/health"
    echo -e "\033[1;36m------------------------------------------------------\033[0m"
else
    echo -e "\033[1;31m❌ Service health check failed. Showing container logs:\033[0m"
    docker compose logs --tail=25 app
    exit 1
fi
