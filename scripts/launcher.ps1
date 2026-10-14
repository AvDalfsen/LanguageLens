$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "environment.ps1")
Write-Host "Checking the local Language Lens installation..."
if (-not (Test-LensEnvironment $ProjectRoot)) {
    Write-Host "First-time setup or installation recovery is needed. Downloads require an internet connection."
    & (Join-Path $PSScriptRoot "setup.ps1") -ProjectRoot $ProjectRoot
}
Write-Host "Starting Language Lens..."
& (Join-Path $PSScriptRoot "run.ps1") -ProjectRoot $ProjectRoot
