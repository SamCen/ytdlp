from __future__ import annotations

import os
import sys
import traceback

# pythonw has no console. Give Qt real streams so startup does not stall.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme


def _report_startup_failure(exc: BaseException) -> None:
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("yt-dlp 下载器 启动失败")
    box.setText(f"程序无法启动：{exc}")
    box.setInformativeText(
        "常见原因是数据目录不可写（例如在受限的沙箱/受控文件夹访问下运行）。"
    )
    box.setDetailedText(traceback.format_exc())
    box.exec()


def main() -> None:
    app = QApplication(sys.argv)
    app.setOrganizationName("ytdlp")
    app.setApplicationName("desktop")
    app.setApplicationDisplayName("yt-dlp 下载器")
    font = QFont()
    font.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"])
    font.setPointSize(10)
    app.setFont(font)
    apply_theme(app)
    try:
        window = MainWindow()
    except Exception as exc:  # noqa: BLE001 - surface any startup failure to the user
        _report_startup_failure(exc)
        raise SystemExit(1) from exc
    window.showNormal()
    window.raise_()
    window.activateWindow()
    window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
