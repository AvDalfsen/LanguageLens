param(
    [string]$Python = "",
    [switch]$UseExistingEnvironment
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $Python = & py -3.10 -c "import sys; print(sys.executable)"
    if ($LASTEXITCODE -ne 0) { throw "Install Windows x64 Python 3.10 to build this release." }
}
$Python = (Resolve-Path -LiteralPath $Python).Path
& $Python -c "import sys, struct; assert sys.platform == 'win32' and sys.version_info[:2] == (3, 10) and struct.calcsize('P') == 8, 'Release builds require Windows x64 Python 3.10'"
if ($LASTEXITCODE -ne 0) { throw "Unsupported release build interpreter." }
$RunId = (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$RunRoot = Join-Path $ProjectRoot "artifacts\releases\$RunId"
New-Item -ItemType Directory -Path $RunRoot -Force | Out-Null
if (-not $UseExistingEnvironment) {
    & $Python -m venv (Join-Path $RunRoot "build-env")
    if ($LASTEXITCODE -ne 0) { throw "Could not create the release build environment." }
    $Python = Join-Path $RunRoot "build-env\Scripts\python.exe"
    & $Python -m pip install "pip==26.2.1"
    if ($LASTEXITCODE -ne 0) { throw "Could not install the pinned pip version." }
    & $Python -m pip install -r (Join-Path $ProjectRoot "packaging\requirements-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install the pinned build tools." }
    & $Python -m pip install --no-build-isolation -c (Join-Path $ProjectRoot "constraints\windows-python310.txt") $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not install the pinned runtime dependencies." }
} else {
    # Resource collection reads the installed package; refresh its catalogs and metadata.
    & $Python -m pip install --no-deps --no-build-isolation --no-index $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not refresh the application in the existing build environment." }
}
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency consistency check failed." }
$DistRoot = Join-Path $RunRoot "dist"
& $Python (Join-Path $PSScriptRoot "freeze-release.py") --output $RunRoot
if ($LASTEXITCODE -ne 0) { throw "Build failed. See $RunRoot\build.log" }
$Bundle = Join-Path $DistRoot "LanguageLens"
& $Python (Join-Path $PSScriptRoot "verify-release.py") --bundle $Bundle --output (Join-Path $RunRoot "verification.json")
if ($LASTEXITCODE -ne 0) { throw "Bundled checks failed. See $RunRoot\verification.json" }
& $Python (Join-Path $PSScriptRoot "release-report.py") --bundle $Bundle --output $RunRoot
if ($LASTEXITCODE -ne 0) { throw "Could not generate the release archive and size report." }
Write-Host "Portable preview and reports: $RunRoot"
