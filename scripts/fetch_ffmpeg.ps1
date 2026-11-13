$ErrorActionPreference = 'Stop'
$dest = Join-Path $PSScriptRoot '..\vendor\ffmpeg'
$dest = [System.IO.Path]::GetFullPath($dest)
New-Item -ItemType Directory -Force -Path $dest | Out-Null
if ((Test-Path (Join-Path $dest 'ffmpeg.exe')) -and (Test-Path (Join-Path $dest 'ffprobe.exe')) -and -not $args.Contains('-Force')) {
    Write-Output "ffmpeg already present: $dest"
    exit 0
}
$zip = Join-Path $env:TEMP 'ffmpeg-ytdlp-win64.zip'
$extract = Join-Path $env:TEMP 'ffmpeg-ytdlp-extract'
curl.exe -L --fail --http1.1 --retry 3 -o $zip 'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
if ($LASTEXITCODE -ne 0) { throw "Failed to download ffmpeg (curl exit $LASTEXITCODE)" }
if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
Expand-Archive -Force -Path $zip -DestinationPath $extract
$bin = Get-ChildItem -Path $extract -Recurse -Directory -Filter bin | Select-Object -First 1
if (-not $bin) { throw 'ffmpeg bin directory not found in archive' }
Get-ChildItem $bin.FullName -File | Where-Object { $_.Name -ne 'ffplay.exe' } | ForEach-Object {
    Copy-Item $_.FullName -Destination (Join-Path $dest $_.Name) -Force
}
Get-ChildItem $extract -Recurse -File | Where-Object { $_.Name -match '^(LICENSE|COPYING)' } | ForEach-Object {
    Copy-Item $_.FullName -Destination (Join-Path $dest $_.Name) -Force
}
if (-not (Test-Path (Join-Path $dest 'ffmpeg.exe'))) { throw 'ffmpeg.exe missing after extract' }
Write-Output "ffmpeg installed to $dest"
