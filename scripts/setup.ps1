$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
py -3 -m venv .venv
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m pip install -U pip
& $python -m pip install -e .
& (Join-Path $PSScriptRoot 'fetch_ffmpeg.ps1')
Write-Output 'Ready. Start with: .\.venv\Scripts\python.exe -m app'
