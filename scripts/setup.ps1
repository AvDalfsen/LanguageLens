$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvironmentPath = Join-Path $ProjectRoot ".venv"

if (-not (Test-Path -LiteralPath $EnvironmentPath)) {
    python -m venv $EnvironmentPath
}

$PythonPath = Join-Path $EnvironmentPath "Scripts\python.exe"
& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install -e "$ProjectRoot[dev]"

Write-Host "Setup complete. Run scripts\run.ps1 to start Language Lens."

