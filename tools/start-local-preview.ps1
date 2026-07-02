param(
    [string]$BackendEnvFile = ".env",
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendEnvPath = Join-Path $RepoRoot $BackendEnvFile
$WebEnvPath = Join-Path $RepoRoot "web\.env.local"
$PreviewLoginEnvPath = Join-Path $RepoRoot "tools\local-preview-login.env"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Env file not found: $Path"
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name -match "^[A-Za-z_][A-Za-z0-9_]*$") {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

function Add-CorsOrigin {
    param([string]$Origin)

    $origins = @()
    if ($env:APP_CORS_ORIGINS) {
        $origins = $env:APP_CORS_ORIGINS -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    }

    if ($origins -notcontains $Origin) {
        $origins += $Origin
    }

    $env:APP_CORS_ORIGINS = ($origins -join ",")
}

Import-DotEnv -Path $BackendEnvPath

if (Test-Path -LiteralPath $WebEnvPath) {
    Import-DotEnv -Path $WebEnvPath
}

if (Test-Path -LiteralPath $PreviewLoginEnvPath) {
    Import-DotEnv -Path $PreviewLoginEnvPath
}

$env:UNLXCK_ENV = "development"
$env:APP_ENV = "development"
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$ApiPort"
$env:NEXT_PUBLIC_SITE_URL = "http://localhost:$WebPort"

Add-CorsOrigin -Origin "http://127.0.0.1:$WebPort"
Add-CorsOrigin -Origin "http://localhost:$WebPort"

$envSnapshot = @{}
Get-ChildItem Env: | ForEach-Object {
    $envSnapshot[$_.Name] = $_.Value
}

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

Write-Host "Starting Unlxck local preview"
Write-Host "API: http://127.0.0.1:$ApiPort"
Write-Host "Web: http://localhost:$WebPort"
Write-Host "Backend env: $BackendEnvFile"
if ($env:UNLXCK_PREVIEW_EMAIL) {
    Write-Host "Preview login: $env:UNLXCK_PREVIEW_EMAIL"
}
Write-Host "Press Ctrl+C to stop both services."

$backendJob = Start-Job -Name "unlxck-api" -ArgumentList $RepoRoot, $envSnapshot, $python, $ApiPort -ScriptBlock {
    param($RepoRoot, $EnvSnapshot, $Python, $ApiPort)

    Set-Location $RepoRoot
    foreach ($key in $EnvSnapshot.Keys) {
        Set-Item -Path "Env:$key" -Value $EnvSnapshot[$key]
    }

    & $Python -m uvicorn api.app:app --reload --host 127.0.0.1 --port $ApiPort 2>&1 | ForEach-Object { Write-Output $_ }
}

$webJob = Start-Job -Name "unlxck-web" -ArgumentList $RepoRoot, $envSnapshot, $WebPort -ScriptBlock {
    param($RepoRoot, $EnvSnapshot, $WebPort)

    Set-Location (Join-Path $RepoRoot "web")
    foreach ($key in $EnvSnapshot.Keys) {
        Set-Item -Path "Env:$key" -Value $EnvSnapshot[$key]
    }

    & npm run dev -- --hostname localhost --port $WebPort 2>&1 | ForEach-Object { Write-Output $_ }
}

try {
    while ($true) {
        Receive-Job -Job $backendJob, $webJob -ErrorAction Continue

        $failedJob = Get-Job -Id $backendJob.Id, $webJob.Id | Where-Object { $_.State -in @("Failed", "Stopped", "Completed") } | Select-Object -First 1
        if ($failedJob) {
            Receive-Job -Job $backendJob, $webJob -ErrorAction Continue
            throw "Preview service exited: $($failedJob.Name) ($($failedJob.State))"
        }

        Start-Sleep -Seconds 1
    }
}
finally {
    Stop-Job -Job $backendJob, $webJob -ErrorAction SilentlyContinue
    Remove-Job -Job $backendJob, $webJob -Force -ErrorAction SilentlyContinue
}
