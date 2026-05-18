$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $Root "frontend")
if (-not (Test-Path "node_modules")) {
  npm install
}
npm run dev
