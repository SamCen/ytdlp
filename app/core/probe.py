from __future__ import annotations

from PySide6.QtCore import QThread, Signal

_SKIP_EXT = {"jpg", "png", "webp", "mhtml"}


def _useful_format(fmt: dict) -> bool:
    if not fmt.get("format_id"):
        return False
    if (fmt.get("ext") or "") in _SKIP_EXT:
        return False
    note = (fmt.get("format_note") or "").lower()
    if note == "storyboard" or "storyboard" in note:
        return False
    vcodec = fmt.get("vcodec") or "none"
    acodec = fmt.get("acodec") or "none"
    return not (vcodec == "none" and acodec == "none")


def _entry_url(entry: dict, page_url: str) -> str | None:
    for key in ("webpage_url", "url"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    video_id = entry.get("id")
    ie_key = (entry.get("ie_key") or "").lower()
    if isinstance(video_id, str) and video_id and (
        "youtube" in ie_key or "youtube.com" in page_url or "youtu.be" in page_url
    ):
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def simplify(info: dict, page_url: str) -> dict:
    kind = info.get("_type")
    if kind in {"playlist", "multi_video"}:
        entries = []
        for entry in info.get("entries") or []:
            if not entry:
                continue
            url = _entry_url(entry, page_url)
            if not url:
                continue
            entries.append(
                {
                    "id": entry.get("id"),
                    "title": entry.get("title") or entry.get("id") or url,
                    "url": url,
                    "duration": entry.get("duration"),
                }
            )
        return {
            "kind": "playlist",
            "source_url": page_url,
            "title": info.get("title") or "播放列表",
            "channel": info.get("channel") or info.get("uploader") or "",
            "thumbnail": info.get("thumbnail"),
            "entries": entries,
        }

    formats = []
    for fmt in info.get("formats") or []:
        if not _useful_format(fmt):
            continue
        formats.append(
            {
                "format_id": fmt.get("format_id"),
                "ext": fmt.get("ext"),
                "resolution": fmt.get("resolution"),
                "height": fmt.get("height"),
                "fps": fmt.get("fps"),
                "vcodec": fmt.get("vcodec"),
                "acodec": fmt.get("acodec"),
                "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                "format_note": fmt.get("format_note") or "",
                "tbr": fmt.get("tbr"),
            }
        )
    formats.sort(key=lambda item: ((item.get("height") or 0), (item.get("tbr") or 0)), reverse=True)
    return {
        "kind": "video",
        "source_url": page_url,
        "id": info.get("id"),
        "title": info.get("title") or info.get("id") or "未命名",
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or page_url,
        "formats": formats,
    }


def _error_message(exc: BaseException) -> str:
    message = getattr(exc, "msg", None) or str(exc)
    text = str(message).strip()
    return text or exc.__class__.__name__


class ProbeWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, cookiefile: str | None, browser: str | None, cachedir: str) -> None:
        super().__init__()
        self.url = url
        self.cookiefile = cookiefile
        self.browser = browser
        self.cachedir = cachedir

    def run(self) -> None:
        try:
            info = self._extract()
        except Exception as exc:
            self.failed.emit(_error_message(exc))
            return
        self.succeeded.emit(info)

    def _extract(self) -> dict:
        import yt_dlp

        from app.core.cookies import apply_cookies
        from app.core.paths import js_runtime_config

        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "noplaylist": False,
            "cachedir": self.cachedir,
            "socket_timeout": 20,
            "js_runtimes": js_runtime_config(),
        }
        apply_cookies(opts, cookiefile=self.cookiefile, browser=self.browser)
        with yt_dlp.YoutubeDL(opts) as ydl:
            raw = ydl.sanitize_info(ydl.extract_info(self.url, download=False))
        if not isinstance(raw, dict):
            raise RuntimeError("解析结果无法读取")
        if raw.get("_type") not in {"playlist", "multi_video"} and not raw.get("formats"):
            full_opts = dict(opts)
            full_opts["extract_flat"] = False
            full_opts["noplaylist"] = True
            with yt_dlp.YoutubeDL(full_opts) as ydl:
                raw = ydl.sanitize_info(ydl.extract_info(self.url, download=False))
            if not isinstance(raw, dict):
                raise RuntimeError("解析结果无法读取")
        result = simplify(raw, self.url)
        if result["kind"] == "playlist" and not result["entries"]:
            raise RuntimeError("播放列表里没有可下载的条目")
        return result
