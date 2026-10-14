param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = "Stop"
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CatalogPath = Join-Path $ProjectRoot "src\language_lens\data\translation-providers.json"
$Catalog = Get-Content -LiteralPath $CatalogPath -Raw | ConvertFrom-Json
$AssetsPath = Join-Path $ProjectRoot "src\language_lens\_translation_assets"
$NeedsAssets = $false
foreach ($Kind in @("small", "m2m")) {
    foreach ($File in $Catalog.models.$Kind.files) {
        $Target = Join-Path (Join-Path $AssetsPath $Kind) $File.name
        if (-not (Test-Path -LiteralPath $Target -PathType Leaf) -or (Get-Item -LiteralPath $Target).Length -ne $File.bytes) {
            $NeedsAssets = $true
        }
    }
}
if (-not $NeedsAssets) { return }
Write-Host "Preparing the local translation model resources (first-time source installation)."
$BuilderPath = Join-Path $ProjectRoot "build\translation-builder"
$BuilderPython = Join-Path $BuilderPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $BuilderPython)) {
    & $PythonPath -m venv --system-site-packages $BuilderPath
    if ($LASTEXITCODE -ne 0) { throw "Could not create the translation model build environment." }
}
& $BuilderPython -m pip install -r (Join-Path $ProjectRoot "packaging\requirements-translation-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Could not prepare the translation model build tools." }
& $BuilderPython (Join-Path $PSScriptRoot "prepare-translation-assets.py")
if ($LASTEXITCODE -ne 0) { throw "Could not prepare the verified translation models. Retry the launcher." }
