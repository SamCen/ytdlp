from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from app.core.paths import cache_dir

BROWSER_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "不使用"),
    ("edge", "Microsoft Edge"),
    ("chrome", "Google Chrome"),
    ("firefox", "Firefox"),
    ("brave", "Brave"),
)

_BROWSER_IDS = {key for key, _label in BROWSER_CHOICES if key}


def browser_label(browser: str) -> str:
    for key, label in BROWSER_CHOICES:
        if key == browser:
            return label
    return browser or "不使用"


def installed_browsers() -> list[str]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    candidates = [
        ("edge", local / "Microsoft" / "Edge" / "User Data"),
        ("chrome", local / "Google" / "Chrome" / "User Data"),
        ("brave", local / "BraveSoftware" / "Brave-Browser" / "User Data"),
        ("firefox", roaming / "Mozilla" / "Firefox" / "Profiles"),
    ]
    if sys.platform != "win32":
        return [key for key, _path in candidates]
    return [key for key, path in candidates if path.is_dir()]


_EXPORT_HINT = (
    "请在已登录 YouTube 的浏览器页面，用扩展 “Get cookies.txt LOCALLY” "
    "导出 Netscape 格式的 cookies.txt，然后打开「文件 → 设置」，"
    "选择该文件。"
)


def _local_state_path(browser: str) -> Path | None:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roots = {
        "chrome": local / "Google" / "Chrome" / "User Data" / "Local State",
        "edge": local / "Microsoft" / "Edge" / "User Data" / "Local State",
        "brave": local / "BraveSoftware" / "Brave-Browser" / "User Data" / "Local State",
    }
    return roots.get(browser)


def uses_app_bound_encryption(browser: str) -> bool:
    """Chromium 127+ stores cookies behind an app-bound key yt-dlp cannot unwrap."""
    path = _local_state_path(browser)
    if path is None or not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return False
    key = data.get("os_crypt", {}).get("app_bound_encrypted_key")
    return isinstance(key, str) and bool(key)


def usable_browser(browser: str | None) -> str | None:
    if browser in _BROWSER_IDS and not uses_app_bound_encryption(browser):
        return browser
    return None


def browser_cookie_block_reason(browser: str | None) -> str | None:
    if not browser or browser not in _BROWSER_IDS:
        return None
    if uses_app_bound_encryption(browser):
        return (
            f"无法读取 {browser_label(browser)} 的登录状态。"
            "这和浏览器是否已经退出、是否重新打开无关："
            "它的 cookies 使用了应用绑定加密，当前的 yt-dlp 解不开。"
            + _EXPORT_HINT
        )
    return None


def _cookie_jar(cookiefile: str) -> str:
    """Path yt-dlp should use as its cookie jar: a writable copy of the user's file.

    yt-dlp saves the cookie jar back to whatever ``cookiefile`` it was given
    every time the ``YoutubeDL`` object closes.  Pointing that at the user's own
    export means each parse tries to rewrite that file, which fails outright
    when the location is not writable (read-only share, synced folder, mapped
    drive, restricted process) and needlessly modifies a file we were only asked
    to read.  Work on a copy in our own data directory instead.
    """
    source = Path(cookiefile)
    if not source.is_file():
        return cookiefile
    try:
        target = cache_dir() / "cookies.txt"
        if source.resolve() == target.resolve():
            return str(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return str(target)
    except (OSError, RuntimeError):
        return cookiefile


def apply_cookies(opts: dict, *, cookiefile: str | None, browser: str | None) -> None:
    if cookiefile:
        opts["cookiefile"] = _cookie_jar(cookiefile)
    browser = usable_browser(browser)
    if browser:
        opts["cookiesfrombrowser"] = (browser, None, None, None)


def explain_error(message: str) -> str:
    text = (message or "").strip()
    lowered = text.lower()
    if "sign in to confirm" in lowered or "not a bot" in lowered:
        return "YouTube 要求确认你不是机器人。" + _EXPORT_HINT
    if "could not copy" in lowered and "cookie" in lowered:
        return (
            "浏览器仍在占用 cookies 文件。请在任务栏右键该浏览器图标并选择退出，"
            "直到任务管理器里没有它的进程，保持关闭后再解析。"
            "若使用的是 Chrome 或 Edge，退出后仍可能因应用绑定加密而读失败。"
            + _EXPORT_HINT
        )
    if "could not be decrypted" in lowered or "unknown cookie version" in lowered:
        return "浏览器 cookies 已读到，但解密失败。" + _EXPORT_HINT
    if text.startswith("ERROR:"):
        return text[6:].strip()
    return text
