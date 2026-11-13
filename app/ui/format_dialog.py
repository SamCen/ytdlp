from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.humanize import format_bytes
from app.core.presets import describe_format


class FormatDialog(QDialog):
    def __init__(self, formats: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择格式")
        self.resize(760, 460)
        self.choice: tuple[str, str] | None = None
        self._formats = formats

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["格式", "说明", "分辨率", "封装", "大小", "备注"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._accept_current)
        for fmt in formats:
            selector, note, _label = describe_format(fmt)
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                str(fmt.get("format_id") or ""),
                str(fmt.get("format_note") or ""),
                str(fmt.get("resolution") or "—"),
                str(fmt.get("ext") or ""),
                format_bytes(fmt.get("filesize")) if fmt.get("filesize") else "未知",
                note,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, selector)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_current)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.table.itemSelectionChanged.connect(self._sync_ok)

        hint = QLabel("只包含这次解析到的格式。标成「需要合并」的会自动配上最佳音轨。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)
        if not formats:
            empty = QLabel("这次解析没有列出可选格式，请使用 1080p、720p 或仅音频。")
            empty.setObjectName("muted")
            layout.insertWidget(1, empty)

    def _sync_ok(self) -> None:
        self.ok_button.setEnabled(bool(self.table.selectionModel().selectedRows()))

    def _accept_current(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        fmt = self._formats[rows[0].row()]
        selector, _note, label = describe_format(fmt)
        self.choice = (selector, label)
        self.accept()
