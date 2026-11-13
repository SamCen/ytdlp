from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from app.core.humanize import progress_percent, progress_text, speed_text
from app.core.presets import PRESET_LABELS
from app.core.store import Job
from app.ui.theme import ACCENT, DANGER, MUTED, OK, SELECT, SURFACE, SURFACE_ALT, TEXT, WARN

PERCENT_ROLE = Qt.ItemDataRole.UserRole + 1

STATUS_LABELS = {
    "queued": "待下载",
    "starting": "启动中",
    "downloading": "下载中",
    "postprocessing": "后处理",
    "paused": "已暂停",
    "completed": "完成",
    "failed": "失败",
    "cancelled": "已取消",
}

_ACTIVE_STATUSES = {"downloading", "postprocessing", "starting"}

_STATUS_COLORS = {
    "downloading": QColor(ACCENT),
    "postprocessing": QColor(WARN),
    "paused": QColor(WARN),
    "completed": QColor(OK),
    "failed": QColor(DANGER),
    "cancelled": QColor(MUTED),
}

ACTION_COLUMN = 4
ACTION_BUTTON_WIDTH = 56
ACTION_BUTTON_HEIGHT = 24
ACTION_BUTTON_GAP = 8


def action_button_rects(cell: QRect) -> tuple[QRect, QRect]:
    """Start/暂停 button rectangles inside one action cell."""
    total = ACTION_BUTTON_WIDTH * 2 + ACTION_BUTTON_GAP
    left = cell.left() + max(0, (cell.width() - total) // 2)
    top = cell.top() + max(0, (cell.height() - ACTION_BUTTON_HEIGHT) // 2)
    start = QRect(left, top, ACTION_BUTTON_WIDTH, ACTION_BUTTON_HEIGHT)
    pause = QRect(
        left + ACTION_BUTTON_WIDTH + ACTION_BUTTON_GAP,
        top,
        ACTION_BUTTON_WIDTH,
        ACTION_BUTTON_HEIGHT,
    )
    return start, pause


def action_button_at(cell: QRect, position: QPoint) -> str | None:
    start, pause = action_button_rects(cell)
    if start.contains(position):
        return "start"
    if pause.contains(position):
        return "pause"
    return None


class QueueModel(QAbstractTableModel):
    headers = ["标题", "状态", "进度", "速度", "操作"]

    def __init__(self, jobs: list[Job] | None = None) -> None:
        super().__init__()
        self._jobs = list(jobs or [])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._jobs)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return 5

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        job = self._jobs[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return job.title
            if column == 1:
                label = STATUS_LABELS.get(job.status, job.status)
                preset = PRESET_LABELS.get(job.preset, job.preset)
                return f"{label} · {preset}"
            if column == 2:
                return progress_text(job.status, job.downloaded, job.total, job.eta)
            if column == 3:
                return speed_text(job.status, job.speed)
            if column == 4:
                return ""
        if role == PERCENT_ROLE and column == 2:
            return progress_percent(job.status, job.downloaded, job.total)
        if role == Qt.ItemDataRole.ForegroundRole and column == 1:
            return _STATUS_COLORS.get(job.status)
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 4:
                if job.status in _ACTIVE_STATUSES:
                    return "下载中：可暂停；暂停后从断点续传"
                if job.status == "completed":
                    return "已完成：点「开始」重新下载"
                return "点「开始」立即下载，点「暂停」保留断点"
            lines = [job.title, job.url]
            if job.error:
                lines.append(job.error)
            if job.output_path:
                lines.append(job.output_path)
            return "\n".join(lines)
        if role == Qt.ItemDataRole.TextAlignmentRole and column in {0, 1, 2, 3}:
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def insert_job(self, job: Job) -> None:
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._jobs.insert(0, job)
        self.endInsertRows()

    def update_job(self, job_id: str, **fields: object) -> None:
        row = self._row(job_id)
        if row is None:
            return
        job = self._jobs[row]
        for key, value in fields.items():
            if hasattr(job, key):
                setattr(job, key, value)
        top = self.index(row, 0)
        bottom = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top, bottom)

    def remove_job(self, job_id: str) -> None:
        row = self._row(job_id)
        if row is None:
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._jobs[row]
        self.endRemoveRows()

    def contains(self, job_id: str) -> bool:
        return self._row(job_id) is not None

    def job_at(self, row: int) -> Job | None:
        if 0 <= row < len(self._jobs):
            return self._jobs[row]
        return None

    def _row(self, job_id: str) -> int | None:
        for index, job in enumerate(self._jobs):
            if job.id == job_id:
                return index
        return None


def paint_row_background(painter, option, index: QModelIndex) -> None:
    selected = bool(option.state & QStyle.StateFlag.State_Selected)
    if selected:
        painter.fillRect(option.rect, QColor(SELECT))
    elif index.row() % 2:
        painter.fillRect(option.rect, QColor(SURFACE_ALT))
    else:
        painter.fillRect(option.rect, QColor(SURFACE))


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        painter.save()
        paint_row_background(painter, option, index)
        painter.setPen(QColor(TEXT))
        text_rect = option.rect.adjusted(10, 2, -10, -8)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        percent = index.data(PERCENT_ROLE)
        if isinstance(percent, int):
            bar = option.rect.adjusted(10, option.rect.height() - 7, -10, -3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#2c3846"))
            painter.drawRoundedRect(bar, 2, 2)
            width = int(bar.width() * percent / 100)
            if width > 0:
                painter.setBrush(QColor(ACCENT))
                painter.drawRoundedRect(bar.adjusted(0, 0, width - bar.width(), 0), 2, 2)
        painter.restore()


class ActionDelegate(QStyledItemDelegate):
    """Draws the per-row 开始 / 暂停 buttons inside the action column."""

    def paint(self, painter, option, index) -> None:
        painter.save()
        paint_row_background(painter, option, index)
        model = index.model()
        job = model.job_at(index.row()) if hasattr(model, "job_at") else None
        if job is None:
            painter.restore()
            return
        start_rect, pause_rect = action_button_rects(option.rect)
        active = job.status in _ACTIVE_STATUSES
        self._draw_button(painter, start_rect, "开始", enabled=not active, primary=True)
        self._draw_button(painter, pause_rect, "暂停", enabled=active, primary=False)
        painter.restore()

    @staticmethod
    def _draw_button(painter, rect: QRect, text: str, *, enabled: bool, primary: bool) -> None:
        if enabled and primary:
            background = QColor(ACCENT)
            border = QColor(ACCENT)
            color = QColor("#17200a")
        elif enabled:
            background = QColor("#1b2836")
            border = QColor("#3d4d60")
            color = QColor(TEXT)
        else:
            background = QColor("#151d26")
            border = QColor("#24303c")
            color = QColor("#5d6b7c")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 6, 6)
        pen = QPen(border)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
