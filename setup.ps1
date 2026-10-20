$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
python -m venv (Join-Path $Root ".venv")
& (Join-Path $Root ".venv/Scripts/python.exe") -m pip install --upgrade pip
& (Join-Path $Root ".venv/Scripts/python.exe") -m pip install -r (Join-Path $Root "requirements.txt") -e $Root
Push-Location (Join-Path $Root "web"); npm install; Pop-Location
Write-Host "TraceWeave is ready. Run .\start.ps1"
