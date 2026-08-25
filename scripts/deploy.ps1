# ==============================================================================
# Automated Docker Deployment Pipeline (Windows PowerShell)
# ==============================================================================

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "[*] Starting Automated Agentic Commerce Deployment..." -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# Step 1: Verify .env exists
if (-not (Test-Path ".env")) {
    Write-Host "[!] .env file not found! Copying from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

# Step 2: Stop and clean existing containers
Write-Host ""
Write-Host "[1/4] Stopping existing containers..." -ForegroundColor Green
docker compose down --remove-orphans

# Step 3: Build and launch services in background
Write-Host ""
Write-Host "[2/4] Building image and starting services..." -ForegroundColor Green
docker compose up --build -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker Compose failed to start!" -ForegroundColor Red
    exit 1
}

# Step 4: Wait for application healthcheck
Write-Host ""
Write-Host "[3/4] Waiting for services to become healthy..." -ForegroundColor Green
$healthy = $false
for ($i = 1; $i -le 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 3 -ErrorAction Stop
        if ($response.status -eq "healthy") {
            $healthy = $true
            break
        }
    } catch {
        Write-Host "  ... waiting for backend initialization ($i/15)" -ForegroundColor DarkGray
    }
}

if ($healthy) {
    Write-Host ""
    Write-Host "[4/4] [SUCCESS] Deployment Succeeded!" -ForegroundColor Green
    Write-Host "------------------------------------------------------" -ForegroundColor Cyan
    Write-Host "API Root:   http://localhost:8000" -ForegroundColor White
    Write-Host "Dashboard:  http://localhost:8000/dashboard" -ForegroundColor Yellow
    Write-Host "Health:     http://localhost:8000/health" -ForegroundColor White
    Write-Host "------------------------------------------------------" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "[WARN] Service did not respond healthy in time. Checking logs:" -ForegroundColor Yellow
    docker compose logs --tail=20 app
}
