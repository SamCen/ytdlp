from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.paths import is_writable
from app.core.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(640, 320)
        self._settings = settings

        self.download_edit = QLineEdit(str(settings.download_dir()))
        download_row = self._path_row(self.download_edit, self._browse_download, clearable=False)

        self.concurrent = QSpinBox()
        self.concurrent.setRange(1, 5)
        self.concurrent.setValue(settings.max_concurrent())

        self.ffmpeg_edit = QLineEdit(settings.ffmpeg_override())
        self.ffmpeg_edit.setPlaceholderText("留空则使用附带的 ffmpeg，其次才找系统 PATH")
        ffmpeg_row = self._path_row(self.ffmpeg_edit, self._browse_ffmpeg, clearable=True)

        self.cookie_edit = QLineEdit(settings.cookiefile())
        self.cookie_edit.setPlaceholderText("Netscape cookies.txt，可留空")
        cookie_row = self._path_row(self.cookie_edit, self._browse_cookie, clearable=True)

        self.langs_edit = QLineEdit(",".join(settings.subtitle_langs()))
        self.langs_edit.setPlaceholderText("zh-Hans,zh,en")

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("下载目录", download_row)
        form.addRow("同时下载", self.concurrent)
        form.addRow("ffmpeg 目录", ffmpeg_row)
        form.addRow("cookies 文件", cookie_row)
        form.addRow("字幕语言", self.langs_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(buttons)

    def _path_row(self, edit: QLineEdit, browse, clearable: bool) -> QWidget:
        button = QPushButton("浏览…")
        button.clicked.connect(browse)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        row.addWidget(button)
        if clearable:
            clear = QPushButton("清除")
            clear.clicked.connect(edit.clear)
            row.addWidget(clear)
        holder = QWidget()
        holder.setLayout(row)
        return holder

    def _browse_download(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "下载目录", self.download_edit.text())
        if path:
            self.download_edit.setText(path)

    def _browse_ffmpeg(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "ffmpeg 所在目录", self.ffmpeg_edit.text())
        if path:
            self.ffmpeg_edit.setText(path)

    def _browse_cookie(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "cookies.txt",
            self.cookie_edit.text(),
            "Cookies (*.txt);;所有文件 (*.*)",
        )
        if path:
            self.cookie_edit.setText(path)

    def _save(self) -> None:
        text = self.download_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "设置", "请填写下载目录。")
            return
        directory = Path(text)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "设置", f"无法创建下载目录：{exc}")
            return
        if not is_writable(directory):
            QMessageBox.warning(
                self,
                "设置",
                "这个目录当前无法写入，下载会失败：\n\n"
                f"{directory}\n\n"
                "请换一个目录；如果程序是被受限方式启动的，"
                "从资源管理器双击运行，或改用它自己目录下的位置。",
            )
            return
        cookie = self.cookie_edit.text().strip()
        if cookie and not Path(cookie).is_file():
            QMessageBox.warning(self, "设置", "cookies 文件不存在。")
            return
        self._settings.set_download_dir(directory)
        self._settings.set_max_concurrent(self.concurrent.value())
        self._settings.set_ffmpeg_override(self.ffmpeg_edit.text().strip())
        self._settings.set_cookiefile(cookie)
        self._settings.set_subtitle_langs(self.langs_edit.text())
        if not self._settings.sync():
            QMessageBox.warning(
                self,
                "设置",
                "设置未能写入磁盘，已放弃保存。\n\n"
                f"位置：{self._settings.path}\n"
                "请确认该目录可写后再试。",
            )
            return
        self.accept()
