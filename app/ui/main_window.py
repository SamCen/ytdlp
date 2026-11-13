from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import yt_dlp
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QFont, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.core.cookies import browser_cookie_block_reason, explain_error, usable_browser
from app.core.humanize import format_duration
from app.core.paths import cache_dir, db_path, ffmpeg_status, js_runtime
from app.core.presets import PRESET_LABELS
from app.core.probe import ProbeWorker
from app.core.queue import JobQueue
from app.core.settings import Settings
from app.core.store import Job, Store, new_job
from app.ui.format_dialog import FormatDialog
from app.ui.playlist_dialog import PlaylistDialog
from app.ui.queue_model import (
    ACTION_COLUMN,
    ActionDelegate,
    ProgressDelegate,
    QueueModel,
    action_button_at,
)
from app.ui.settings_dialog import SettingsDialog

_ACTIVE_STATUSES = {"downloading", "postprocessing", "starting"}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("yt-dlp 下载器")
        self.resize(1120, 760)
        self.setMinimumSize(960, 640)

        self.settings = Settings()
        self.store = Store(db_path())
        interrupted = self.store.fail_interrupted()
        self.store.reset_starting()
        jobs = self.store.list_jobs()
        self.model_pending = QueueModel([job for job in jobs if job.status != "completed"])
        self.model_completed = QueueModel([job for job in jobs if job.status == "completed"])
        self.queue = JobQueue(self.store, self.settings)
        self.queue.added.connect(self._on_added)
        self.queue.changed.connect(self._on_changed)
        self.queue.removed.connect(self._on_removed)
        self.queue.logged.connect(self._append_log)
        self.nam = QNetworkAccessManager(self)
        self._probe: dict | None = None
        self._probed_url = ""
        self._probe_gen = 0
        self._probe_workers: set[ProbeWorker] = set()
        self._custom_selector: str | None = None
        self._thumb_reply: QNetworkReply | None = None

        self._build_ui()
        self._build_menu()
        if interrupted:
            self._append_log(f"{interrupted} 个未完成任务已标为失败，可以重试")
        self._refresh_banner()
        self._sync_counts()
        self._sync_actions()

    def _build_ui(self) -> None:
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("url")
        self.url_edit.setPlaceholderText("粘贴视频或播放列表链接")
        self.url_edit.returnPressed.connect(self._probe_url)
        self.url_edit.textChanged.connect(self._on_url_changed)

        self.probe_btn = QPushButton("解析")
        self.probe_btn.clicked.connect(self._probe_url)
        self.enqueue_btn = QPushButton("加入队列")
        self.enqueue_btn.setObjectName("primary")
        self.enqueue_btn.setEnabled(False)
        self.enqueue_btn.clicked.connect(self._enqueue_clicked)
        self.advanced_btn = QPushButton("高级格式")
        self.advanced_btn.setEnabled(False)
        self.advanced_btn.clicked.connect(self._choose_format)

        self.radio_1080 = QRadioButton("1080p")
        self.radio_720 = QRadioButton("720p")
        self.radio_audio = QRadioButton("仅音频")
        self.custom_radio = QRadioButton("自定义")
        self.custom_radio.hide()
        self.radio_1080.setChecked(True)
        self.presets = QButtonGroup(self)
        for button in (self.radio_1080, self.radio_720, self.radio_audio, self.custom_radio):
            self.presets.addButton(button)

        self.subs_check = QCheckBox("嵌入字幕")
        self.subs_check.setToolTip("包含自动生成字幕。仅音频不会嵌入字幕。语言在设置里修改。")

        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.probe_btn)

        quality = QFrame()
        quality.setObjectName("quality")
        quality_row = QHBoxLayout(quality)
        quality_row.setContentsMargins(3, 3, 3, 3)
        quality_row.setSpacing(0)
        quality_row.addWidget(self.radio_1080)
        quality_row.addWidget(self.radio_720)
        quality_row.addWidget(self.radio_audio)
        quality_row.addWidget(self.custom_radio)

        option_row = QHBoxLayout()
        option_row.setSpacing(10)
        option_row.addWidget(quality)
        option_row.addWidget(self.subs_check)
        option_row.addStretch(1)
        option_row.addWidget(self.advanced_btn)
        option_row.addWidget(self.enqueue_btn)

        self.thumb = QLabel("封面")
        self.thumb.setObjectName("thumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFixedSize(240, 135)
        self.preview_title = QLabel("等待解析")
        self.preview_title.setObjectName("headline")
        self.preview_title.setWordWrap(True)
        self.preview_meta = QLabel("支持单个视频和播放列表")
        self.preview_meta.setObjectName("muted")
        self.preview_meta.setWordWrap(True)
        preview_text = QVBoxLayout()
        preview_text.setSpacing(6)
        preview_text.addStretch(1)
        preview_text.addWidget(self.preview_title)
        preview_text.addWidget(self.preview_meta)
        preview_text.addStretch(1)
        preview_row = QHBoxLayout()
        preview_row.setSpacing(16)
        preview_row.addWidget(self.thumb)
        preview_row.addLayout(preview_text, 1)

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner_btn = QPushButton("设置")
        self.banner_btn.clicked.connect(self._open_settings)
        banner_row = QHBoxLayout()
        banner_row.addWidget(self.banner, 1)
        banner_row.addWidget(self.banner_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.banner_wrap = QWidget()
        self.banner_wrap.setLayout(banner_row)

        self.pending_table = self._make_table(self.model_pending)
        self.completed_table = self._make_table(self.model_completed)

        self.pending_empty = QLabel("待下载是空的。解析链接后加入队列。")
        self.pending_empty.setObjectName("muted")
        self.completed_empty = QLabel("还没有已完成的任务。下载完成后会自动移到「已完成」。")
        self.completed_empty.setObjectName("muted")

        pending_page = QWidget()
        pending_layout = QVBoxLayout(pending_page)
        pending_layout.setContentsMargins(0, 4, 0, 0)
        pending_layout.setSpacing(8)
        pending_layout.addWidget(self.pending_empty)
        pending_layout.addWidget(self.pending_table, 1)

        completed_page = QWidget()
        completed_layout = QVBoxLayout(completed_page)
        completed_layout.setContentsMargins(0, 4, 0, 0)
        completed_layout.setSpacing(8)
        completed_layout.addWidget(self.completed_empty)
        completed_layout.addWidget(self.completed_table, 1)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(pending_page, "待下载")
        self.tabs.addTab(completed_page, "已完成")
        self.tabs.currentChanged.connect(lambda _index: self._sync_actions())

        self.start_btn = QPushButton("开始")
        self.start_btn.setObjectName("primary")
        self.pause_btn = QPushButton("暂停")
        self.cancel_btn = QPushButton("取消")
        self.retry_btn = QPushButton("重试")
        self.open_btn = QPushButton("打开所在位置")
        self.remove_btn = QPushButton("从列表移除")
        self.start_btn.clicked.connect(self._start_selected)
        self.pause_btn.clicked.connect(self._pause_selected)
        self.cancel_btn.clicked.connect(self._cancel_selected)
        self.retry_btn.clicked.connect(self._retry_selected)
        self.open_btn.clicked.connect(self._open_selected)
        self.remove_btn.clicked.connect(self._remove_selected)
        actions = QHBoxLayout()
        actions.addWidget(self.start_btn)
        actions.addWidget(self.pause_btn)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.retry_btn)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.remove_btn)
        actions.addStretch(1)

        queue_label = QLabel("下载队列")
        queue_label.setObjectName("section")
        queue_page = QWidget()
        queue_layout = QVBoxLayout(queue_page)
        queue_layout.setContentsMargins(0, 4, 0, 0)
        queue_layout.setSpacing(8)
        queue_layout.addWidget(queue_label)
        queue_layout.addWidget(self.tabs, 1)
        queue_layout.addLayout(actions)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText("日志")
        log_font = QFont("Cascadia Mono", 9)
        log_font.setStyleHint(QFont.StyleHint.Monospace)
        self.log.setFont(log_font)
        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.setContentsMargins(0, 8, 0, 0)
        log_label = QLabel("日志")
        log_label.setObjectName("section")
        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log, 1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(queue_page)
        splitter.addWidget(log_page)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([460, 160])

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 8, 20, 12)
        root.setSpacing(14)
        root.addWidget(self.banner_wrap)
        root.addLayout(url_row)
        root.addLayout(option_row)
        root.addLayout(preview_row)
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        self.setStatusBar(status)
        runtime = js_runtime() or "无 JS 运行时"
        status.showMessage(f"yt-dlp {yt_dlp.version.__version__}  ·  {runtime}")

    def _make_table(self, model: QueueModel) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.setItemDelegateForColumn(2, ProgressDelegate(table))
        table.setItemDelegateForColumn(ACTION_COLUMN, ActionDelegate(table))
        table.verticalHeader().setDefaultSectionSize(42)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, view=table: self._open_menu_at(view, pos)
        )
        table.doubleClicked.connect(lambda index: self._on_table_double_clicked(index))
        table.clicked.connect(lambda index, view=table: self._on_table_clicked(view, index))
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(ACTION_COLUMN, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 140)
        table.setColumnWidth(2, 160)
        table.setColumnWidth(3, 110)
        table.setColumnWidth(ACTION_COLUMN, 150)
        table.selectionModel().selectionChanged.connect(lambda *_args: self._sync_actions())
        model.rowsInserted.connect(lambda *_args: self._sync_counts())
        model.rowsRemoved.connect(lambda *_args: self._sync_counts())
        model.dataChanged.connect(lambda *_args: self._sync_actions())
        return table

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        file_menu.addAction("打开下载目录", self._open_download_dir)
        file_menu.addAction("设置…", self._open_settings)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)
        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction("关于", self._about)

    def _probe_url(self) -> None:
        url = self.url_edit.text().strip()
        if not url.startswith(("http://", "https://")):
            self.preview_meta.setText("请输入 http 或 https 链接")
            return
        browser = self.settings.browser() or None
        block = browser_cookie_block_reason(browser)
        if block and not self.settings.existing_cookiefile():
            self.preview_title.setText("无法读取浏览器登录")
            self.preview_meta.setText(block)
            self._append_log(f"解析失败：{block}")
            answer = QMessageBox.question(
                self,
                "无法读取浏览器登录",
                block + "\n\n现在打开设置？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._open_settings()
            return
        self._probe_gen += 1
        generation = self._probe_gen
        self.probe_btn.setEnabled(False)
        self.probe_btn.setText("解析中…")
        self.preview_title.setText("正在解析")
        self.preview_meta.setText(url)
        worker = ProbeWorker(
            url,
            self.settings.existing_cookiefile(),
            usable_browser(browser),
            str(cache_dir()),
        )
        worker.succeeded.connect(lambda info, gen=generation: self._probe_ok(gen, info))
        worker.failed.connect(lambda message, gen=generation: self._probe_fail(gen, message))
        worker.finished.connect(lambda gen=generation: self._probe_finished(gen))
        worker.finished.connect(lambda w=worker: self._probe_workers.discard(w))
        worker.finished.connect(worker.deleteLater)
        self._probe_workers.add(worker)
        worker.start()

    def _probe_ok(self, generation: int, info: object) -> None:
        if generation != self._probe_gen or not isinstance(info, dict):
            return
        self._probe = info
        self._probed_url = str(info.get("source_url") or "")
        self._custom_selector = None
        self.custom_radio.hide()
        self.custom_radio.setChecked(False)
        if not self.presets.checkedButton():
            self.radio_1080.setChecked(True)
        self.preview_title.setText(str(info.get("title") or "未命名"))
        self._load_thumbnail(info.get("thumbnail"))
        if info.get("kind") == "playlist":
            count = len(info.get("entries") or [])
            channel = info.get("channel") or ""
            meta = f"播放列表 · {count} 条"
            if channel:
                meta = f"{channel}  ·  {meta}"
            self.preview_meta.setText(meta)
            self.enqueue_btn.setText("选择条目")
            self.enqueue_btn.setEnabled(True)
            self.advanced_btn.setEnabled(False)
            return
        bits = []
        if info.get("channel"):
            bits.append(str(info["channel"]))
        duration = format_duration(info.get("duration"))
        if duration:
            bits.append(duration)
        bits.append(f"{len(info.get('formats') or [])} 个格式")
        self.preview_meta.setText("  ·  ".join(bits))
        self.enqueue_btn.setText("加入队列")
        self.enqueue_btn.setEnabled(True)
        self.advanced_btn.setEnabled(bool(info.get("formats")))

    def _probe_fail(self, generation: int, message: str) -> None:
        if generation != self._probe_gen:
            return
        text = explain_error(message)
        self._probe = None
        self._probed_url = ""
        self.enqueue_btn.setEnabled(False)
        self.advanced_btn.setEnabled(False)
        self.preview_title.setText("解析失败")
        self.preview_meta.setText(text)
        self._append_log(f"解析失败：{text}")
        if "不是机器人" in text and not self.settings.browser() and not self.settings.existing_cookiefile():
            answer = QMessageBox.question(
                self,
                "需要登录",
                text + "\n\n现在打开设置？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._open_settings()

    def _probe_finished(self, generation: int) -> None:
        if generation != self._probe_gen:
            return
        self.probe_btn.setEnabled(True)
        self.probe_btn.setText("解析")

    def _on_url_changed(self, text: str) -> None:
        if text.strip() == self._probed_url:
            return
        self._probe_gen += 1
        had_probe = self._probe is not None or bool(self._probed_url)
        self._probe = None
        self._probed_url = ""
        self._custom_selector = None
        self.custom_radio.hide()
        self.custom_radio.setChecked(False)
        self.enqueue_btn.setEnabled(False)
        self.enqueue_btn.setText("加入队列")
        self.advanced_btn.setEnabled(False)
        if had_probe:
            self.preview_title.setText("等待解析")
            self.preview_meta.setText("链接已更改，请重新解析")
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("无封面")
        if not self.probe_btn.isEnabled():
            self.probe_btn.setEnabled(True)
            self.probe_btn.setText("解析")

    def _enqueue_clicked(self) -> None:
        if not self._probe:
            return
        if self._probe.get("kind") == "playlist":
            self._enqueue_playlist()
        else:
            self._enqueue_video()

    def _enqueue_video(self) -> None:
        preset, selector = self._current_format()
        url = str(self._probe.get("webpage_url") or self._probed_url)
        job = new_job(
            url=url,
            title=str(self._probe.get("title") or url),
            preset=preset,
            format_selector=selector,
            subtitles=self.subs_check.isChecked() and preset != "audio",
        )
        self.queue.enqueue(job)

    def _enqueue_playlist(self) -> None:
        preset, selector = self._current_format()
        if preset == "custom":
            preset, selector = "1080p", None
            self.radio_1080.setChecked(True)
            self._append_log("播放列表使用 1080p。高级格式只对单个视频生效。")
        dialog = PlaylistDialog(
            str(self._probe.get("title") or "播放列表"),
            list(self._probe.get("entries") or []),
            PRESET_LABELS.get(preset, preset),
            self,
        )
        if not dialog.exec():
            return
        jobs = [
            new_job(
                url=entry["url"],
                title=str(entry.get("title") or entry["url"]),
                preset=preset,
                format_selector=selector,
                subtitles=self.subs_check.isChecked() and preset != "audio",
            )
            for entry in dialog.selected_entries()
        ]
        self.queue.enqueue_many(jobs)

    def _current_format(self) -> tuple[str, str | None]:
        if self.custom_radio.isChecked() and self._custom_selector:
            return "custom", self._custom_selector
        if self.radio_audio.isChecked():
            return "audio", None
        if self.radio_720.isChecked():
            return "720p", None
        return "1080p", None

    def _choose_format(self) -> None:
        if not self._probe or self._probe.get("kind") != "video":
            return
        dialog = FormatDialog(list(self._probe.get("formats") or []), self)
        if not dialog.exec() or not dialog.choice:
            return
        selector, label = dialog.choice
        self._custom_selector = selector
        self.custom_radio.setText(label if len(label) <= 28 else label[:27] + "…")
        self.custom_radio.setToolTip(selector)
        self.custom_radio.setVisible(True)
        self.custom_radio.setChecked(True)

    def _load_thumbnail(self, url: object) -> None:
        if self._thumb_reply is not None:
            self._thumb_reply.abort()
            self._thumb_reply = None
        if not isinstance(url, str) or not url.startswith("http"):
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("无封面")
            return
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0")
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        reply = self.nam.get(request)
        self._thumb_reply = reply
        reply.finished.connect(lambda r=reply: self._thumb_ready(r))

    def _thumb_ready(self, reply: QNetworkReply) -> None:
        if reply is not self._thumb_reply:
            reply.deleteLater()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        self._thumb_reply = None
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.thumb.setText("无封面")
            return
        scaled = pixmap.scaled(
            self.thumb.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.thumb.setText("")
        self.thumb.setPixmap(scaled)

    # -------------------------------------------------------------- 队列事件

    def _on_added(self, job: object) -> None:
        if isinstance(job, Job):
            self.model_pending.insert_job(job)
            self._sync_counts()

    def _on_changed(self, job_id: str, fields: object) -> None:
        if not isinstance(fields, dict):
            return
        moved = False
        if "status" in fields:
            job = self.store.get(job_id)
            if job is None:
                return
            if job.status == "completed" and self.model_pending.contains(job_id):
                self.model_pending.remove_job(job_id)
                self.model_completed.insert_job(job)
                moved = True
            elif job.status != "completed" and self.model_completed.contains(job_id):
                self.model_completed.remove_job(job_id)
                self.model_pending.insert_job(job)
                moved = True
        self.model_pending.update_job(job_id, **fields)
        self.model_completed.update_job(job_id, **fields)
        if moved:
            self._sync_counts()

    def _on_removed(self, job_id: str) -> None:
        self.model_pending.remove_job(job_id)
        self.model_completed.remove_job(job_id)
        self._sync_counts()

    # -------------------------------------------------------------- 队列操作

    def _current_table(self) -> QTableView:
        return self.completed_table if self.tabs.currentIndex() == 1 else self.pending_table

    def _selected_jobs(self) -> list[Job]:
        table = self._current_table()
        model = table.model()
        rows = sorted({index.row() for index in table.selectionModel().selectedRows()})
        jobs: list[Job] = []
        for row in rows:
            job = model.job_at(row) if hasattr(model, "job_at") else None
            if job is not None:
                jobs.append(job)
        return jobs

    def _sync_actions(self) -> None:
        jobs = self._selected_jobs()
        statuses = {job.status for job in jobs}
        self.start_btn.setEnabled(any(status not in _ACTIVE_STATUSES for status in statuses))
        self.pause_btn.setEnabled(any(status in _ACTIVE_STATUSES for status in statuses))
        self.cancel_btn.setEnabled(
            any(status in {"queued", "starting", "downloading", "postprocessing"} for status in statuses)
        )
        self.retry_btn.setEnabled(any(status in {"failed", "cancelled", "paused"} for status in statuses))
        self.open_btn.setEnabled(any(bool(job.output_path) or job.status == "completed" for job in jobs))
        self.remove_btn.setEnabled(any(status not in _ACTIVE_STATUSES for status in statuses))

    def _sync_counts(self) -> None:
        pending = self.model_pending.rowCount()
        completed = self.model_completed.rowCount()
        self.tabs.setTabText(0, f"待下载（{pending}）" if pending else "待下载")
        self.tabs.setTabText(1, f"已完成（{completed}）" if completed else "已完成")
        self.pending_empty.setVisible(pending == 0)
        self.completed_empty.setVisible(completed == 0)
        self._sync_actions()

    def _on_table_clicked(self, table: QTableView, index) -> None:
        if not index.isValid() or index.column() != ACTION_COLUMN:
            return
        model = table.model()
        job = model.job_at(index.row()) if hasattr(model, "job_at") else None
        if job is None:
            return
        position = table.viewport().mapFromGlobal(QCursor.pos())
        hit = action_button_at(table.visualRect(index), position)
        if hit == "start":
            self.queue.start([job.id])
        elif hit == "pause":
            self.queue.pause([job.id])
        self._sync_actions()

    def _on_table_double_clicked(self, index) -> None:
        if index.column() == ACTION_COLUMN:
            return
        self._open_selected()

    def _start_selected(self) -> None:
        jobs = self._selected_jobs()
        if jobs:
            self.queue.start([job.id for job in jobs])
            self._sync_actions()

    def _pause_selected(self) -> None:
        jobs = self._selected_jobs()
        if jobs:
            self.queue.pause([job.id for job in jobs])
            self._sync_actions()

    def _cancel_selected(self) -> None:
        jobs = self._selected_jobs()
        if jobs:
            self.queue.cancel([job.id for job in jobs])
            self._sync_actions()

    def _retry_selected(self) -> None:
        jobs = self._selected_jobs()
        if jobs:
            self.queue.retry([job.id for job in jobs])
            self._sync_actions()

    def _remove_selected(self) -> None:
        jobs = self._selected_jobs()
        if not jobs:
            return
        removable = []
        skipped = 0
        for job in jobs:
            if job.status in _ACTIVE_STATUSES:
                skipped += 1
                continue
            removable.append(job.id)
        if removable:
            self.queue.remove(removable)
        if skipped:
            self._append_log(f"{skipped} 个进行中的任务没有移除，请先暂停或取消")
        self._sync_actions()

    def _open_selected(self) -> None:
        jobs = self._selected_jobs()
        paths = [job.output_path for job in jobs if job.output_path and Path(job.output_path).exists()]
        if not paths:
            self._open_download_dir()
            return
        folders: dict[str, list[str]] = {}
        for path in paths:
            folders.setdefault(str(Path(path).parent), []).append(path)
        for folder, files in folders.items():
            if len(files) == 1:
                subprocess.run(["explorer", f"/select,{files[0]}"], check=False)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _open_menu_at(self, table: QTableView, pos) -> None:
        index = table.indexAt(pos)
        if not index.isValid():
            return
        selected_rows = {item.row() for item in table.selectionModel().selectedRows()}
        if index.row() not in selected_rows:
            table.selectRow(index.row())
        popup = QMenu(self)
        popup.addAction("开始", self._start_selected)
        popup.addAction("暂停", self._pause_selected)
        popup.addSeparator()
        popup.addAction("取消", self._cancel_selected)
        popup.addAction("重试", self._retry_selected)
        popup.addSeparator()
        popup.addAction("打开所在位置", self._open_selected)
        popup.addAction("从列表移除", self._remove_selected)
        popup.exec(table.viewport().mapToGlobal(pos))

    def _open_download_dir(self) -> None:
        folder = self.settings.download_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "打开下载目录", f"无法创建下载目录：\n{folder}\n\n{exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self._refresh_banner()
            self.queue.pump()
            self._append_log("设置已保存")

    def _refresh_banner(self) -> None:
        status = ffmpeg_status(self.settings.ffmpeg_override())
        notes = []
        if not status.ok:
            notes.append("没有找到 ffmpeg。音视频合并和音频转码需要它。")
        if js_runtime() is None:
            notes.append("没有找到 Deno、Node 或 Bun。YouTube 解析需要其中之一。")
        if notes:
            self.banner.setText(" ".join(notes))
            self.banner_wrap.setVisible(True)
        else:
            self.banner_wrap.setVisible(False)

    def _append_log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"{stamp}  {text}")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            f"yt-dlp 下载器 {__version__}\n\n"
            f"yt-dlp {yt_dlp.version.__version__}\n\n"
            "下载你有权保存的内容，只在这台电脑上使用。",
        )

    def closeEvent(self, event) -> None:
        if self.queue.has_running() or self.queue.has_starting():
            answer = QMessageBox.question(
                self,
                "退出",
                "还有任务在下载或等待开始。退出后未完成的任务会中断，下次启动可以重试。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.queue.cancel_all_running()
            self.queue.wait_all(1500)
        self.queue.blockSignals(True)
        self.store.reset_starting()
        self.store.close()
        event.accept()
