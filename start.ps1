$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv/Scripts/python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
$api = Start-Process -FilePath $Python -ArgumentList "-m uvicorn api.app:app --host 127.0.0.1 --port 8000" -WorkingDirectory $Root -PassThru
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
$web = Start-Process -FilePath "npm" -ArgumentList "run dev" -WorkingDirectory (Join-Path $Root "web") -PassThru
try { Wait-Process -Id $api.Id, $web.Id } finally { Stop-Process -Id $api.Id, $web.Id -Force -ErrorAction SilentlyContinue; Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue }
