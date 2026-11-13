from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_UPDATABLE = {
    "title",
    "preset",
    "format_selector",
    "subtitles",
    "status",
    "downloaded",
    "total",
    "speed",
    "eta",
    "error",
    "output_path",
    "finished_at",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_job(
    *,
    url: str,
    title: str,
    preset: str,
    format_selector: str | None,
    subtitles: bool,
) -> Job:
    return Job(
        id=uuid.uuid4().hex,
        url=url,
        title=title or url,
        preset=preset,
        format_selector=format_selector,
        subtitles=subtitles,
        status="queued",
        downloaded=0,
        total=None,
        speed=None,
        eta=None,
        error=None,
        output_path=None,
        created_at=now_iso(),
        finished_at=None,
    )


@dataclass
class Job:
    id: str
    url: str
    title: str
    preset: str
    format_selector: str | None
    subtitles: bool
    status: str
    downloaded: int
    total: int | None
    speed: float | None
    eta: int | None
    error: str | None
    output_path: str | None
    created_at: str
    finished_at: str | None


def _job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        url=row["url"],
        title=row["title"],
        preset=row["preset"],
        format_selector=row["format_selector"],
        subtitles=bool(row["subtitles"]),
        status=row["status"],
        downloaded=row["downloaded"] or 0,
        total=row["total"],
        speed=row["speed"],
        eta=row["eta"],
        error=row["error"],
        output_path=row["output_path"],
        created_at=row["created_at"],
        finished_at=row["finished_at"],
    )


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            # WAL needs to create side files next to the database; a plain
            # rollback journal is enough when that is not possible.
            self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                preset TEXT NOT NULL,
                format_selector TEXT,
                subtitles INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                downloaded INTEGER NOT NULL DEFAULT 0,
                total INTEGER,
                speed REAL,
                eta INTEGER,
                error TEXT,
                output_path TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at)"
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def insert(self, job: Job) -> None:
        self.insert_many([job])

    def insert_many(self, jobs: list[Job]) -> None:
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO jobs (
                    id, url, title, preset, format_selector, subtitles, status,
                    downloaded, total, speed, eta, error, output_path, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        job.id,
                        job.url,
                        job.title,
                        job.preset,
                        job.format_selector,
                        int(job.subtitles),
                        job.status,
                        job.downloaded,
                        job.total,
                        job.speed,
                        job.eta,
                        job.error,
                        job.output_path,
                        job.created_at,
                        job.finished_at,
                    )
                    for job in jobs
                ],
            )

    def update(self, job_id: str, **fields: object) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise KeyError(f"cannot update {sorted(unknown)}")
        if not fields:
            return
        if "subtitles" in fields:
            fields["subtitles"] = int(bool(fields["subtitles"]))
        columns = ", ".join(f"{name} = ?" for name in fields)
        values = list(fields.values()) + [job_id]
        with self.conn:
            self.conn.execute(f"UPDATE jobs SET {columns} WHERE id = ?", values)

    def delete(self, job_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def get(self, job_id: str) -> Job | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job(row) if row else None

    def list_jobs(self) -> list[Job]:
        rows = self.conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC").fetchall()
        return [_job(row) for row in rows]

    def next_queued(self) -> Job | None:
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC, rowid ASC LIMIT 1"
        ).fetchone()
        return _job(row) if row else None

    def next_starting(self) -> Job | None:
        """The next job the user explicitly asked to start."""
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'starting' ORDER BY created_at ASC, rowid ASC LIMIT 1"
        ).fetchone()
        return _job(row) if row else None

    def reset_starting(self) -> int:
        """Drop start requests that never reached a worker (app quit, restart)."""
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE jobs SET status = 'queued', speed = NULL, eta = NULL WHERE status = 'starting'"
            )
        return cursor.rowcount

    def fail_interrupted(self) -> int:
        message = "程序上次退出时任务中断，可重试"
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', error = ?, speed = NULL, eta = NULL, finished_at = ?
                WHERE status IN ('downloading', 'postprocessing')
                """,
                (message, now_iso()),
            )
        return cursor.rowcount
