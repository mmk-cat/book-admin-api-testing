param(
    [ValidateSet("dev", "test")]
    [string]$Env = "dev",
    [switch]$Install
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if ($Install) {
    python -m pip install -r requirements.txt
}

if ($Env -eq "test") {
    Write-Host "MySQL 模式需要先启动服务：docker compose up -d --build" -ForegroundColor Yellow
}

python scripts/run_regression.py --env $Env
exit $LASTEXITCODE
