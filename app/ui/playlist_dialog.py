from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.core.humanize import format_duration


class PlaylistDialog(QDialog):
    def __init__(self, title: str, entries: list[dict], preset_label: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("播放列表")
        self.resize(560, 480)
        self.entries = entries

        heading = QLabel(title)
        heading.setObjectName("title")
        heading.setWordWrap(True)
        hint = QLabel(f"勾选要下载的条目，格式使用当前选项：{preset_label}")
        hint.setObjectName("muted")
        hint.setWordWrap(True)

        self.list = QListWidget()
        for entry in entries:
            duration = format_duration(entry.get("duration"))
            text = entry["title"]
            if duration:
                text = f"{text}  ({duration})"
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list.addItem(item)

        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        self.list.itemChanged.connect(lambda _item: self._sync_count())

        all_button = QPushButton("全选")
        none_button = QPushButton("全不选")
        all_button.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        none_button.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self.ok_button = QPushButton("加入队列")
        self.ok_button.setObjectName("primary")
        self.ok_button.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)

        checks = QHBoxLayout()
        checks.addWidget(all_button)
        checks.addWidget(none_button)
        checks.addStretch(1)
        checks.addWidget(self.count_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(cancel)
        actions.addWidget(self.ok_button)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(hint)
        layout.addLayout(checks)
        layout.addWidget(self.list, 1)
        layout.addLayout(actions)
        self._sync_count()

    def _set_all(self, state: Qt.CheckState) -> None:
        for index in range(self.list.count()):
            self.list.item(index).setCheckState(state)

    def _sync_count(self) -> None:
        selected = len(self.selected_entries())
        self.count_label.setText(f"已选 {selected} / {len(self.entries)}")
        self.ok_button.setEnabled(selected > 0)

    def selected_entries(self) -> list[dict]:
        chosen = []
        for index, entry in enumerate(self.entries):
            if self.list.item(index).checkState() == Qt.CheckState.Checked:
                chosen.append(entry)
        return chosen
