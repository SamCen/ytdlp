from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from app.core.cookies import _BROWSER_IDS
from app.core.paths import app_data_dir, default_download_dir

_DEFAULT_SUBTITLE_LANGS = "zh-Hans,zh,en"

# Every key the app has ever stored; used to migrate the old registry store.
_LEGACY_KEYS = (
    "download_dir",
    "max_concurrent",
    "ffmpeg_override",
    "browser",
    "cookiefile",
    "subtitle_langs",
)


class Settings:
    """Persisted settings, stored next to the job database.

    The Windows registry is not used any more: a restricted process (sandbox,
    policy, roaming-profile lock) can be denied the write, QSettings then
    reports ``AccessError`` and *silently* drops every value the settings
    dialog stores, so the user sees "设置已保存" while nothing is kept.  An INI
    file in the application data directory is written wherever the database is
    written, and ``sync()`` lets the dialog verify the result.
    """

    def __init__(self) -> None:
        self.path = app_data_dir() / "settings.ini"
        existed = self.path.exists()
        self._qs = QSettings(str(self.path), QSettings.Format.IniFormat)
        if not existed:
            self._migrate_from_registry()
        self.sync()

    def _migrate_from_registry(self) -> None:
        """Copy values from the old registry location once, keeping them."""
        legacy = QSettings("ytdlp", "desktop")
        if legacy.status() != QSettings.Status.NoError:
            return
        for key in _LEGACY_KEYS:
            if legacy.contains(key):
                self._qs.setValue(key, legacy.value(key))

    def sync(self) -> bool:
        """Flush to disk; False when the values could not be stored."""
        self._qs.sync()
        return self._qs.status() == QSettings.Status.NoError

    def download_dir(self) -> Path:
        value = str(self._qs.value("download_dir", "") or "").strip()
        if value:
            return Path(value)
        return default_download_dir()

    def set_download_dir(self, path: Path) -> None:
        self._qs.setValue("download_dir", str(path))

    def max_concurrent(self) -> int:
        try:
            value = int(self._qs.value("max_concurrent", 2))
        except (TypeError, ValueError):
            value = 2
        return min(5, max(1, value))

    def set_max_concurrent(self, value: int) -> None:
        self._qs.setValue("max_concurrent", min(5, max(1, int(value))))

    def ffmpeg_override(self) -> str:
        return str(self._qs.value("ffmpeg_override", "") or "").strip()

    def set_ffmpeg_override(self, path: str) -> None:
        self._qs.setValue("ffmpeg_override", path.strip())

    def cookiefile(self) -> str:
        return str(self._qs.value("cookiefile", "") or "").strip()

    def set_cookiefile(self, path: str) -> None:
        self._qs.setValue("cookiefile", path.strip())

    def existing_cookiefile(self) -> str | None:
        path = self.cookiefile()
        if path and Path(path).is_file():
            return path
        return None

    def browser(self) -> str:
        value = str(self._qs.value("browser", "") or "").strip().lower()
        return value if value in _BROWSER_IDS else ""

    def set_browser(self, value: str) -> None:
        value = value.strip().lower()
        self._qs.setValue("browser", value if value in _BROWSER_IDS else "")

    def subtitle_langs(self) -> list[str]:
        raw = str(self._qs.value("subtitle_langs", _DEFAULT_SUBTITLE_LANGS) or "")
        langs = [part.strip() for part in raw.split(",") if part.strip()]
        return langs or ["zh-Hans", "zh", "en"]

    def set_subtitle_langs(self, value: str) -> None:
        self._qs.setValue("subtitle_langs", value.strip() or _DEFAULT_SUBTITLE_LANGS)
