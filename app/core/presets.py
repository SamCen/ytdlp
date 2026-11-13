from __future__ import annotations

PRESET_FORMATS = {
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "audio": "ba/b",
}

PRESET_LABELS = {
    "1080p": "1080p",
    "720p": "720p",
    "audio": "仅音频",
    "custom": "自定义",
}


def format_for(preset: str, format_selector: str | None) -> str:
    if format_selector:
        return format_selector
    return PRESET_FORMATS.get(preset, PRESET_FORMATS["1080p"])


def extracts_audio(preset: str) -> bool:
    return preset == "audio"


def describe_format(fmt: dict) -> tuple[str, str, str]:
    """Return yt-dlp format selector, a short note, and a radio label."""
    format_id = str(fmt.get("format_id") or "")
    vcodec = fmt.get("vcodec") or "none"
    acodec = fmt.get("acodec") or "none"
    height = fmt.get("height")
    ext = fmt.get("ext") or ""
    has_video = vcodec not in {"none", None}
    has_audio = acodec not in {"none", None}
    if has_video and not has_audio:
        selector = f"{format_id}+bestaudio/best"
        note = "需要合并"
    elif has_audio and not has_video:
        selector = format_id
        note = "仅音频"
    else:
        selector = format_id
        note = "音视频"
    if isinstance(height, int) and height > 0:
        quality = f"{height}p"
    else:
        quality = str(fmt.get("resolution") or ext or format_id)
    label = f"{quality} {ext}".strip()
    if note == "需要合并":
        label = f"{label} 合并"
    return selector, note, label
