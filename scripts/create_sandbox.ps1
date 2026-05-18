# Create VideoDB sandbox using the backend venv (hackathon SDK).
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Continuum = Split-Path -Parent $Root
$Python = Join-Path $Continuum "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Missing $Python — run: cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

Set-Location $Continuum
& $Python (Join-Path $Root "create_sandbox.py")
