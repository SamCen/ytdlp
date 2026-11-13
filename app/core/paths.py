from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths


def _app_names() -> tuple[str, str]:
    app = QCoreApplication.instance()
    organization = (app.organizationName() if app else "") or "ytdlp"
    name = (app.applicationName() if app else "") or "desktop"
    return organization, name


def _qt_data_dir(
    kind: QStandardPaths.StandardLocation, env_var: str, fallback_root: Path
) -> Path:
    """Qt's per-application data folder for *kind*, with an env-var fallback.

    Qt only appends organization/application when the application has a name;
    without one it returns a shared folder such as ``...\\LocalLow``, which we
    must not use for our database.
    """
    organization, name = _app_names()
    value = QStandardPaths.writableLocation(kind)
    if value:
        path = Path(value)
        if path.name == name and path.parent.name == organization:
            return path
    root = os.environ.get(env_var)
    base = Path(root) if root else fallback_root
    return base / organization / name


def is_writable(directory: Path) -> bool:
    """True only when we can really create a file in *directory*.

    Checking permissions is not enough: a sandboxed process can be granted
    read+execute on a folder that already exists.  SQLite then opens the
    database read-only and fails later on PRAGMA journal_mode=WAL, so probe
    the folder with an actual write.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-probe"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _data_dir_candidates() -> list[Path]:
    candidates = [
        _qt_data_dir(
            QStandardPaths.StandardLocation.AppDataLocation,
            "APPDATA",
            Path.home() / "AppData" / "Roaming",
        ),
        _qt_data_dir(
            QStandardPaths.StandardLocation.AppLocalDataLocation,
            "LOCALAPPDATA",
            Path.home() / "AppData" / "Local",
        ),
    ]
    if getattr(sys, "frozen", False):
        # Portable fallback: next to the executable (works when the roaming
        # profile is not writable, e.g. inside a sandbox).
        candidates.append(Path(sys.executable).resolve().parent / "data")
    else:
        candidates.append(project_root() / "data")
    candidates.append(Path(tempfile.gettempdir()) / "ytdlp-desktop")
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


_app_data_dir: Path | None = None


def app_data_dir() -> Path:
    global _app_data_dir
    if _app_data_dir is not None:
        return _app_data_dir
    tried: list[str] = []
    for candidate in _data_dir_candidates():
        if is_writable(candidate):
            _app_data_dir = candidate
            return candidate
        tried.append(str(candidate))
    raise RuntimeError(
        "找不到可写的数据目录，无法保存任务列表。已尝试：\n" + "\n".join(tried)
    )


def db_path() -> Path:
    return app_data_dir() / "jobs.db"


def cache_dir() -> Path:
    path = app_data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def bundled_ffmpeg_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "ffmpeg"
    return project_root() / "vendor" / "ffmpeg"


def default_download_dir() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)
    return Path(location) if location else Path.home() / "Videos"


def _has_ffmpeg(directory: Path) -> bool:
    return (directory / "ffmpeg.exe").is_file() and (directory / "ffprobe.exe").is_file()


def _as_directory(value: str) -> Path:
    raw = Path(value)
    return raw.parent if raw.is_file() else raw


@dataclass(frozen=True)
class FfmpegStatus:
    location: str | None
    source: str
    ok: bool


def ffmpeg_status(override: str) -> FfmpegStatus:
    if override.strip():
        directory = _as_directory(override.strip())
        if _has_ffmpeg(directory):
            return FfmpegStatus(str(directory), "override", True)
    bundled = bundled_ffmpeg_dir()
    if _has_ffmpeg(bundled):
        return FfmpegStatus(str(bundled), "bundled", True)
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return FfmpegStatus(None, "path", True)
    return FfmpegStatus(None, "missing", False)


def ffmpeg_location_for(override: str) -> str | None:
    status = ffmpeg_status(override)
    if status.ok and status.source != "path":
        return status.location
    return None


def js_runtime() -> str | None:
    for name in ("deno", "node", "bun"):
        if shutil.which(name):
            return name
    return None


def js_runtime_config() -> dict[str, dict]:
    """Enable every JS runtime that is actually installed.

    yt-dlp otherwise only turns on Deno, so a machine with Node alone cannot
    solve YouTube challenges.
    """
    config: dict[str, dict] = {}
    for name in ("deno", "node", "bun"):
        located = shutil.which(name)
        if located:
            config[name] = {"path": located}
    return config or {"deno": {}}
