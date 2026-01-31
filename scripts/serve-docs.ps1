# 로컬 문서 서버 실행 (openapi.json 생성 후 mkdocs serve)
# 사용: .\scripts\serve-docs.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Generating docs/api/openapi.json..." -ForegroundColor Cyan
$env:OIDC_ENABLED = "false"
$env:DATABASE_URL = "sqlite:///:memory:"
& "$root\.venv\Scripts\python.exe" -c @"
import os
os.environ['OIDC_ENABLED'] = 'false'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app.main import app
import json
with open('docs/api/openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
print('openapi.json generated.')
"@
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to generate openapi.json. Ensure .venv is set up and requirements are installed." -ForegroundColor Red
    exit 1
}

Write-Host "Starting mkdocs serve..." -ForegroundColor Cyan
& "$root\.venv\Scripts\python.exe" -m mkdocs serve @args
