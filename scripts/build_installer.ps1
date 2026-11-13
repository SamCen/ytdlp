$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& (Join-Path $root 'scripts\fetch_ffmpeg.ps1')
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m pip install pyinstaller
& $python -m PyInstaller --noconfirm (Join-Path $root 'packaging\ytdlp-desktop.spec')
$dist = Join-Path $root 'dist\ytdlp-desktop'
Copy-Item -Recurse -Force (Join-Path $root 'vendor\ffmpeg') (Join-Path $dist 'ffmpeg')
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc (Join-Path $root 'packaging\installer.iss')
    Write-Output 'Installer written to dist\'
} else {
    Write-Output 'PyInstaller folder is ready. Install Inno Setup 6 to compile packaging\installer.iss'
}
