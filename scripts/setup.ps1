$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvironmentPath = Join-Path $ProjectRoot ".venv"

if (-not (Test-Path -LiteralPath $EnvironmentPath)) {
    python -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment." }
}

$PythonPath = Join-Path $EnvironmentPath "Scripts\python.exe"
& $PythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }
& $PythonPath -m pip install -e "$ProjectRoot[dev]"
if ($LASTEXITCODE -ne 0) { throw "Could not install Language Lens dependencies." }

Write-Host "Setup complete. Run scripts\run.ps1 to start Language Lens."

