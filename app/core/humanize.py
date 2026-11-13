from __future__ import annotations


def format_bytes(amount: float | None) -> str:
    if amount is None:
        return "—"
    size = float(amount)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return "—"


def format_duration(seconds: float | None) -> str:
    if not seconds:
        return ""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def progress_text(status: str, downloaded: int, total: int | None, eta: float | None) -> str:
    if status == "downloading":
        if total:
            percent = int(downloaded * 100 / total)
            eta_text = format_eta(eta)
            if eta_text:
                return f"{percent}% · {eta_text}"
            return f"{percent}%"
        if downloaded:
            return format_bytes(downloaded)
        return "连接中"
    if status == "postprocessing":
        return "合并中"
    if status == "completed":
        return "完成"
    if status == "failed":
        return "失败"
    if status == "cancelled":
        return "已取消"
    if status == "paused":
        if total:
            percent = int(downloaded * 100 / total)
            return f"已暂停 · {percent}%"
        if downloaded:
            return f"已暂停 · {format_bytes(downloaded)}"
        return "已暂停"
    if status == "starting":
        return "等待启动"
    if status == "queued":
        return "待下载"
    return "—"


def progress_percent(status: str, downloaded: int, total: int | None) -> int | None:
    if status in {"postprocessing", "completed"}:
        return 100
    if status in {"downloading", "paused"} and total:
        return max(0, min(100, int(downloaded * 100 / total)))
    return None


def speed_text(status: str, speed: float | None) -> str:
    if status == "downloading" and speed:
        return f"{format_bytes(speed)}/s"
    return "—"
