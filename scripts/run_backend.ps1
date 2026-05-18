# Start Continuum API from repo root
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $Root "backend")
$env:PYTHONPATH = (Get-Location).Path

# VideoDB indexing uses tqdm; minimized Windows consoles throttle redraws and slow the pipeline.
$env:CONTINUUM_DISABLE_TQDM = "1"
$env:CONTINUUM_QUIET_CONSOLE = "1"
# Optional: also write INFO logs to continuum/logs/backend.log
# $env:CONTINUUM_LOG_TO_FILE = "1"

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
