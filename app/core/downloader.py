from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.core.cookies import apply_cookies
from app.core.paths import js_runtime_config


@dataclass
class DownloadRequest:
    job_id: str
    url: str
    format: str
    download_dir: str
    ffmpeg_location: str | None
    cookiefile: str | None
    browser: str | None
    subtitles: bool
    audio_extract: bool
    subtitle_langs: list[str]
    cachedir: str


def _error_message(exc: BaseException) -> str:
    message = getattr(exc, "msg", None) or str(exc)
    text = str(message).strip()
    return text or exc.__class__.__name__


def _existing(path: str | None) -> str:
    if path and Path(path).is_file() and not path.endswith(".part"):
        return path
    return ""


def final_path(info: object, fallback: str, directory: Path) -> str:
    found = _existing(fallback)
    video_id = None
    if isinstance(info, dict):
        video_id = info.get("id")
        requested = info.get("requested_downloads") or []
        for item in reversed(requested):
            path = _existing(item.get("filepath"))
            if path:
                return path
        for key in ("filepath", "_filename"):
            path = _existing(info.get(key))
            if path:
                return path
    if found:
        return found
    if not video_id:
        return ""
    media_ext = {".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".opus", ".flac", ".wav", ".ogg"}
    candidates = []
    for path in directory.glob(f"{video_id}.*"):
        if path.suffix.lower() in {".part", ".ytdl", ".temp"}:
            continue
        if path.name.endswith(".temp"):
            continue
        candidates.append(path)
    if not candidates:
        return ""
    media = [path for path in candidates if path.suffix.lower() in media_ext]
    chosen = max(media or candidates, key=lambda path: path.stat().st_mtime)
    return str(chosen)


class _Logger:
    def __init__(self, emit) -> None:
        self._emit = emit

    def _forward(self, message: object) -> None:
        text = str(message).strip()
        if not text or text.startswith("[debug]"):
            return
        if "[download]" in text and "%" in text:
            return
        self._emit(text)

    def debug(self, message: object) -> None:
        if str(message).startswith("[debug]"):
            return
        self._forward(message)

    def info(self, message: object) -> None:
        self._forward(message)

    def warning(self, message: object) -> None:
        self._forward(message)

    def error(self, message: object) -> None:
        self._forward(message)


class DownloadWorker(QThread):
    progress = Signal(str, object)
    log_line = Signal(str, str)
    succeeded = Signal(str, str)
    failed = Signal(str, str)
    cancelled = Signal(str)

    def __init__(self, request: DownloadRequest) -> None:
        super().__init__()
        self.request = request
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        from yt_dlp.utils import DownloadCancelled, DownloadError

        if self._cancel.is_set():
            self.cancelled.emit(self.request.job_id)
            return
        try:
            path = self._download(DownloadCancelled)
        except DownloadCancelled:
            self.cancelled.emit(self.request.job_id)
        except DownloadError as exc:
            self.failed.emit(self.request.job_id, _error_message(exc))
        except Exception as exc:
            self.failed.emit(self.request.job_id, _error_message(exc))
        else:
            self.succeeded.emit(self.request.job_id, path)

    def _download(self, cancel_type: type[BaseException]) -> str:
        import yt_dlp

        request = self.request
        directory = Path(request.download_dir)
        directory.mkdir(parents=True, exist_ok=True)
        captured = {"path": ""}

        def hook(data: dict) -> None:
            if self._cancel.is_set():
                raise cancel_type("已取消")
            filename = data.get("filename") or ""
            if data.get("status") == "finished" and filename:
                captured["path"] = filename
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            self.progress.emit(
                request.job_id,
                {
                    "status": data.get("status") or "downloading",
                    "downloaded": int(data.get("downloaded_bytes") or 0),
                    "total": int(total) if total else None,
                    "speed": data.get("speed"),
                    "eta": data.get("eta"),
                    "filename": filename,
                },
            )

        def pp_hook(data: dict) -> None:
            if self._cancel.is_set() and data.get("status") == "started":
                raise cancel_type("已取消")
            info = data.get("info_dict") or {}
            filepath = info.get("filepath") or ""
            if filepath:
                captured["path"] = filepath
            self.progress.emit(
                request.job_id,
                {
                    "status": "postprocessing",
                    "downloaded": 0,
                    "total": None,
                    "speed": None,
                    "eta": None,
                    "filename": filepath,
                },
            )

        opts: dict = {
            "format": request.format,
            "outtmpl": {"default": str(directory / "%(id)s.%(ext)s")},
            "paths": {"home": str(directory), "temp": str(directory)},
            "restrictfilenames": True,
            "windowsfilenames": True,
            "overwrites": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "concurrent_fragment_downloads": 4,
            "cachedir": request.cachedir,
            "js_runtimes": js_runtime_config(),
            "progress_hooks": [hook],
            "postprocessor_hooks": [pp_hook],
            "logger": _Logger(lambda text: self.log_line.emit(request.job_id, text)),
        }
        if request.ffmpeg_location:
            opts["ffmpeg_location"] = request.ffmpeg_location
        apply_cookies(opts, cookiefile=request.cookiefile, browser=request.browser)
        if request.audio_extract:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        else:
            opts["merge_output_format"] = "mp4"
            if request.subtitles and request.subtitle_langs:
                opts["writesubtitles"] = True
                opts["writeautomaticsub"] = True
                opts["subtitleslangs"] = list(request.subtitle_langs)
                opts["subtitlesformat"] = "srt/vtt/best"
                opts["embedsubtitles"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(request.url, download=True)
            info = ydl.sanitize_info(info)
        return final_path(info, captured["path"], directory)
