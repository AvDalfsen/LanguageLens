$ErrorActionPreference = "Stop"
$PrototypeProject = Split-Path -Parent $PSScriptRoot
$PrototypePython = Join-Path $PrototypeProject "artifacts\pronunciation\.venv\Scripts\python.exe"
$PrototypeBasePython = Join-Path $PrototypeProject ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PrototypeBasePython)) {
    throw "Set up Language Lens first. The prototype uses its Python interpreter to create a separate environment."
}
& $PrototypeBasePython -c "import sys, struct; sys.exit(0 if sys.platform == 'win32' and struct.calcsize('P') == 8 and (3,10) <= sys.version_info[:2] <= (3,12) else 1)"
if ($LASTEXITCODE -ne 0) { throw "The prototype requires Windows x64 and 64-bit Python 3.10-3.12." }
if (-not (Test-Path -LiteralPath $PrototypePython)) {
    & $PrototypeBasePython -m venv (Join-Path $PrototypeProject "artifacts\pronunciation\.venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create the prototype environment." }
}
& $PrototypePython -m pip install -r (Join-Path $PrototypeProject "prototypes\pronunciation\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Could not install pronunciation prototype dependencies." }
Write-Host "Prototype environment ready. See prototypes\pronunciation\README.md for voice downloads and the listening report."
