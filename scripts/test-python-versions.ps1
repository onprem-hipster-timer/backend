# Python 버전 호환성 테스트 스크립트 (PowerShell)
# 사용법: .\scripts\test-python-versions.ps1 [버전...]
#
# 예시:
#   .\scripts\test-python-versions.ps1              # 모든 버전 테스트
#   .\scripts\test-python-versions.ps1 3.12 3.13    # 특정 버전만 테스트

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Versions
)

$ErrorActionPreference = "Continue"

# 프로젝트 디렉토리로 이동
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

# 기본 테스트 버전
$DefaultVersions = @("3.15", "3.14", "3.13", "3.12", "3.11")

# 인자가 있으면 해당 버전만, 없으면 기본 버전 모두 테스트
if ($Versions.Count -eq 0) {
    $Versions = $DefaultVersions
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║          Python Version Compatibility Test Suite           ║" -ForegroundColor Blue
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""
Write-Host "Testing versions: " -NoNewline
Write-Host ($Versions -join ", ") -ForegroundColor Yellow
Write-Host ""

# 결과 저장
$Results = @{}

# 각 버전 테스트
foreach ($Version in $Versions) {
    $ServiceName = "python" + ($Version -replace "\.", "")
    
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
    Write-Host "  Testing Python $Version..." -ForegroundColor Blue
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
    Write-Host ""
    
    # Docker Compose로 테스트 실행
    $process = Start-Process -FilePath "docker" -ArgumentList "compose", "-f", "docker-compose.python-matrix.yaml", "up", "--build", "--abort-on-container-exit", $ServiceName -Wait -PassThru -NoNewWindow
    
    if ($process.ExitCode -eq 0) {
        $Results[$Version] = "PASS"
        Write-Host "✅ Python ${Version}: PASSED" -ForegroundColor Green
    } else {
        $Results[$Version] = "FAIL"
        Write-Host "❌ Python ${Version}: FAILED" -ForegroundColor Red
    }
    
    # 컨테이너 정리
    docker compose -f docker-compose.python-matrix.yaml down --volumes --remove-orphans 2>$null
    
    Write-Host ""
}

# 최종 결과 요약
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║                      Test Summary                          ║" -ForegroundColor Blue
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

$PassCount = 0
$FailCount = 0

foreach ($Version in $Versions) {
    $Result = $Results[$Version]
    if ($Result -eq "PASS") {
        Write-Host "  Python ${Version}: " -NoNewline
        Write-Host "✅ PASSED" -ForegroundColor Green
        $PassCount++
    } else {
        Write-Host "  Python ${Version}: " -NoNewline
        Write-Host "❌ FAILED" -ForegroundColor Red
        $FailCount++
    }
}

Write-Host ""
Write-Host "────────────────────────────────────────────────────────────" -ForegroundColor Blue
Write-Host "  Total: " -NoNewline
Write-Host "$PassCount passed" -ForegroundColor Green -NoNewline
Write-Host ", " -NoNewline
Write-Host "$FailCount failed" -ForegroundColor Red
Write-Host "────────────────────────────────────────────────────────────" -ForegroundColor Blue
Write-Host ""

# 이미지 정리 (선택사항)
$cleanup = Read-Host "Clean up Docker images? (y/N)"
if ($cleanup -eq "y" -or $cleanup -eq "Y") {
    Write-Host "Cleaning up..."
    docker compose -f docker-compose.python-matrix.yaml down --volumes --rmi local 2>$null
    Write-Host "Done."
}

# 실패가 있으면 exit code 1
if ($FailCount -gt 0) {
    exit 1
}
