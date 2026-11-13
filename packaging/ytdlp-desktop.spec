# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
root = Path(SPECPATH).resolve().parent


def _collect(name):
    try:
        return collect_all(name)
    except Exception:
        return [], [], []


yt_datas, yt_binaries, yt_hidden = _collect("yt_dlp")
curl_datas, curl_binaries, curl_hidden = _collect("curl_cffi")
ejs_datas, ejs_binaries, ejs_hidden = _collect("yt_dlp_ejs")

try:
    import yt_dlp

    hookspath = [str(Path(yt_dlp.__file__).resolve().parent / "__pyinstaller")]
except Exception:
    hookspath = []

a = Analysis(
    [str(root / "app" / "__main__.py")],
    pathex=[str(root)],
    binaries=yt_binaries + curl_binaries + ejs_binaries,
    datas=yt_datas + curl_datas + ejs_datas,
    hiddenimports=yt_hidden + curl_hidden + ejs_hidden + ["curl_cffi", "yt_dlp_ejs"],
    hookspath=hookspath,
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ytdlp-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ytdlp-desktop",
)
