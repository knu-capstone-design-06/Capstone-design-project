param(
    [int]$FrontendPort = 5173,
    [int]$BackendPort = 8000
)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $frontendUrl = "http://127.0.0.1:$FrontendPort"
    $page = Invoke-WebRequest -UseBasicParsing -Uri $frontendUrl -TimeoutSec 10
    if ($page.Content -notmatch 'id="root"' -or $page.Content -notmatch '/assets/') {
        throw 'Frontend build was not served'
    }
    $health = Invoke-WebRequest -UseBasicParsing -Uri "$frontendUrl/healthz" -TimeoutSec 10
    if ($health.Content.Trim() -ne 'ok') { throw 'Frontend health failed' }
    foreach ($url in @("$frontendUrl/backend/health", "http://127.0.0.1:$BackendPort/health")) {
        $result = Invoke-RestMethod -Uri $url -TimeoutSec 10
        if ($result.status -ne 'ok' -or $result.service -ne 'backend') { throw "Health failed: $url" }
    }
    try {
        $null = Invoke-WebRequest -UseBasicParsing -Uri "$frontendUrl/backend/not-an-api" -TimeoutSec 10
        throw 'Missing API must return 404, not the SPA HTML'
    } catch {
        if ($null -eq $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404) { throw }
    }
    Write-Output 'PASS: frontend HTML, frontend health, proxied/direct backend health, API 404'
    Get-Content -Raw -LiteralPath "$PSScriptRoot/check-ai.py" | docker compose exec -T backend python -
    if ($LASTEXITCODE -ne 0) { throw 'Backend -> AI check failed' }
} finally {
    Pop-Location
}
