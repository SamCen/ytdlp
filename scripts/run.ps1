$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
    Write-Error 'Missing .venv. Run scripts\setup.ps1 first.'
}
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Start-Process -FilePath $pythonw -ArgumentList '-m', 'app' -WorkingDirectory $root -WindowStyle Normal
