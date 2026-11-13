from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal

from app.core.cookies import explain_error, usable_browser
from app.core.downloader import DownloadRequest, DownloadWorker
from app.core.paths import cache_dir, ffmpeg_location_for, is_writable
from app.core.presets import extracts_audio, format_for
from app.core.settings import Settings
from app.core.store import Job, Store, now_iso

# 任务由用户点「开始」后才进入 starting，等待并发槽位或立刻开工。
_ACTIVE = {"downloading", "postprocessing", "starting"}
_PAUSABLE = {"downloading", "postprocessing", "starting"}
_RETRYABLE = {"failed", "cancelled", "paused"}


class JobQueue(QObject):
    added = Signal(object)
    changed = Signal(str, object)
    removed = Signal(str)
    logged = Signal(str)

    def __init__(self, store: Store, settings: Settings) -> None:
        super().__init__()
        self.store = store
        self.settings = settings
        self._running: dict[str, DownloadWorker] = {}
        self._last_persist: dict[str, float] = {}
        self._saw_postprocess: set[str] = set()
        self._pause_requested: set[str] = set()

    def has_running(self) -> bool:
        return bool(self._running)

    def has_starting(self) -> bool:
        return self.store.next_starting() is not None

    # ------------------------------------------------------------------ 入队

    def enqueue(self, job: Job) -> None:
        self.enqueue_many([job])

    def enqueue_many(self, jobs: list[Job]) -> None:
        """Add jobs to the pending list without downloading anything yet."""
        if not jobs:
            return
        self.store.insert_many(jobs)
        for job in jobs:
            self.added.emit(job)
        self.logged.emit(
            f"已加入 {len(jobs)} 个任务，选中后点「开始」下载" if len(jobs) > 1
            else f"已加入队列：{jobs[0].title}（点「开始」下载）"
        )

    # ------------------------------------------------------------ 用户操作

    def start(self, job_ids: list[str]) -> None:
        """Queue the selected jobs for download; the user asks for them now."""
        ids = list(job_ids)
        started = 0
        for job_id in ids:
            job = self.store.get(job_id)
            if job is None or job.status in _ACTIVE:
                continue
            fields: dict[str, object] = {
                "status": "starting",
                "error": None,
                "speed": None,
                "eta": None,
                "finished_at": None,
            }
            if job.status == "completed" or job.output_path:
                # 重新下载：清掉旧的进度和输出路径。
                fields.update(downloaded=0, total=None, output_path=None)
            self._mark(job_id, **fields)
            started += 1
        if not started:
            return
        self.logged.emit(f"开始下载 {started} 个任务")
        self.pump()

    def pump(self) -> None:
        """Start queued ``starting`` jobs while concurrency allows it."""
        while len(self._running) < self.settings.max_concurrent():
            job = self.store.next_starting()
            if job is None or job.id in self._running:
                return
            if not self._start(job):
                return

    def pause(self, job_ids: list[str]) -> None:
        """Stop the download but keep the partial file for resuming later."""
        for job_id in job_ids:
            job = self.store.get(job_id)
            if job is None:
                continue
            worker = self._running.get(job_id)
            if worker is not None:
                # yt-dlp 无法真正挂起连接：立即取消，重新开始时从 .part 续传。
                self._pause_requested.add(job_id)
                worker.request_cancel()
                self.logged.emit(f"正在暂停：{job.title}（继续时从断点续传）")
                continue
            if job.status in {"queued", "starting"}:
                self._mark(job_id, status="paused", speed=None, eta=None)
                self.logged.emit(f"已暂停：{job.title}")

    def cancel(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            job = self.store.get(job_id)
            if job is None:
                continue
            worker = self._running.get(job_id)
            if worker is not None:
                worker.request_cancel()
                self.logged.emit(f"正在取消：{job.title}")
                continue
            if job.status in {"queued", "starting", "paused"}:
                self._mark(
                    job_id,
                    status="cancelled",
                    speed=None,
                    eta=None,
                    finished_at=now_iso(),
                )

    def cancel_all_running(self) -> None:
        for worker in list(self._running.values()):
            worker.request_cancel()

    def wait_all(self, timeout_ms: int = 2000) -> None:
        for worker in list(self._running.values()):
            worker.wait(timeout_ms)

    def retry(self, job_ids: list[str]) -> None:
        targets = []
        for job_id in job_ids:
            job = self.store.get(job_id)
            if job is not None and job.status in _RETRYABLE:
                targets.append(job)
        if not targets:
            return
        for job in targets:
            self._mark(
                job.id,
                status="starting",
                error=None,
                speed=None,
                eta=None,
                finished_at=None,
            )
        self.logged.emit(f"重新排队 {len(targets)} 个任务")
        self.pump()

    def remove(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            if job_id in self._running:
                continue
            job = self.store.get(job_id)
            if job is None or job.status in {"downloading", "postprocessing"}:
                continue
            self.store.delete(job_id)
            self.removed.emit(job_id)

    # ------------------------------------------------------------ 下载线程

    def _start(self, job: Job) -> bool:
        directory = self.settings.download_dir()
        if not is_writable(directory):
            # Do not hand this to yt-dlp: it would fail part-way through with an
            # opaque "unable to open for writing" and leave a .part file behind.
            self._mark(job.id, status="queued", speed=None, eta=None)
            self.logged.emit(
                f"下载目录不可写，队列已暂停：{directory}\n"
                "请在「文件 → 设置」里换成可写的目录，或改用普通方式启动本程序"
                "（从资源管理器双击），受限环境下只能写入程序自己的目录。"
            )
            return False
        self._mark(
            job.id,
            status="downloading",
            error=None,
            speed=None,
            eta=None,
            finished_at=None,
        )
        request = DownloadRequest(
            job_id=job.id,
            url=job.url,
            format=format_for(job.preset, job.format_selector),
            download_dir=str(directory),
            ffmpeg_location=ffmpeg_location_for(self.settings.ffmpeg_override()),
            cookiefile=self.settings.existing_cookiefile(),
            browser=usable_browser(self.settings.browser() or None),
            subtitles=job.subtitles and not extracts_audio(job.preset),
            audio_extract=extracts_audio(job.preset),
            subtitle_langs=self.settings.subtitle_langs(),
            cachedir=str(cache_dir()),
        )
        worker = DownloadWorker(request)
        worker.progress.connect(self._on_progress)
        worker.log_line.connect(self._on_log)
        worker.succeeded.connect(self._on_succeeded)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        worker.finished.connect(worker.deleteLater)
        self._running[job.id] = worker
        self.logged.emit(f"开始下载：{job.title}")
        worker.start()
        return True

    def _on_progress(self, job_id: str, payload: object) -> None:
        if not isinstance(payload, dict) or job_id not in self._running:
            return
        if job_id in self._pause_requested:
            return
        status = payload.get("status")
        fields: dict[str, object] = {
            "downloaded": int(payload.get("downloaded") or 0),
            "total": payload.get("total"),
            "speed": payload.get("speed"),
            "eta": payload.get("eta"),
        }
        if status in {"finished", "postprocessing"}:
            fields["status"] = "postprocessing"
            fields["speed"] = None
            fields["eta"] = None
        elif status == "downloading":
            fields["status"] = "downloading"
        self.changed.emit(job_id, fields)
        now = time.monotonic()
        if fields.get("status") == "postprocessing" and job_id not in self._saw_postprocess:
            self._saw_postprocess.add(job_id)
            self.store.update(job_id, status="postprocessing", speed=None, eta=None)
            self._last_persist[job_id] = now
            return
        if now - self._last_persist.get(job_id, 0) >= 0.5:
            self._last_persist[job_id] = now
            self.store.update(
                job_id,
                downloaded=fields["downloaded"],
                total=fields["total"],
                speed=fields["speed"],
                eta=fields["eta"],
            )

    def _on_log(self, job_id: str, text: str) -> None:
        job = self.store.get(job_id)
        title = job.title if job else job_id
        self.logged.emit(f"{title}：{text}")

    def _on_succeeded(self, job_id: str, path: str) -> None:
        self._clear_runtime(job_id)
        job = self.store.get(job_id)
        self._mark(
            job_id,
            status="completed",
            output_path=path or None,
            error=None,
            speed=None,
            eta=None,
            finished_at=now_iso(),
        )
        if job:
            self.logged.emit(f"已完成：{job.title}")
        self.pump()

    def _on_failed(self, job_id: str, message: str) -> None:
        self._clear_runtime(job_id)
        job = self.store.get(job_id)
        self._mark(job_id, status="failed", error=explain_error(message), speed=None, eta=None, finished_at=now_iso())
        title = job.title if job else job_id
        self.logged.emit(f"{title} 失败：{explain_error(message)}")
        self.pump()

    def _on_cancelled(self, job_id: str) -> None:
        paused = job_id in self._pause_requested
        self._clear_runtime(job_id)
        job = self.store.get(job_id)
        self._mark(
            job_id,
            status="paused" if paused else "cancelled",
            speed=None,
            eta=None,
            finished_at=None if paused else now_iso(),
        )
        if job:
            self.logged.emit(f"已暂停：{job.title}" if paused else f"已取消：{job.title}")
        self.pump()

    def _clear_runtime(self, job_id: str) -> None:
        self._running.pop(job_id, None)
        self._last_persist.pop(job_id, None)
        self._saw_postprocess.discard(job_id)
        self._pause_requested.discard(job_id)

    def _mark(self, job_id: str, **fields: object) -> None:
        self.store.update(job_id, **fields)
        self.changed.emit(job_id, fields)
