from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PySide6.QtCore import QSettings

from app.core.cookies import apply_cookies, browser_cookie_block_reason, explain_error
from app.core.humanize import format_bytes, progress_percent, progress_text, speed_text
from app.core.presets import describe_format, extracts_audio, format_for
from app.core.probe import simplify
from app.core.store import Store, new_job
from app.core.settings import Settings
import app.core.paths as paths


class PresetTests(unittest.TestCase):
    def test_presets(self) -> None:
        self.assertIn("height<=1080", format_for("1080p", None))
        self.assertIn("height<=720", format_for("720p", None))
        self.assertEqual(format_for("audio", None), "ba/b")
        self.assertEqual(format_for("1080p", "22"), "22")
        self.assertTrue(extracts_audio("audio"))
        self.assertFalse(extracts_audio("1080p"))

    def test_video_only_format_merges_audio(self) -> None:
        selector, note, label = describe_format(
            {"format_id": "137", "ext": "mp4", "height": 1080, "vcodec": "avc1", "acodec": "none"}
        )
        self.assertEqual(selector, "137+bestaudio/best")
        self.assertEqual(note, "需要合并")
        self.assertIn("1080p", label)

    def test_audio_only_format(self) -> None:
        selector, note, _label = describe_format(
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"}
        )
        self.assertEqual(selector, "140")
        self.assertEqual(note, "仅音频")


class HumanizeTests(unittest.TestCase):
    def test_progress(self) -> None:
        self.assertEqual(progress_text("downloading", 50, 100, 65), "50% · 01:05")
        self.assertEqual(progress_text("postprocessing", 0, None, None), "合并中")
        self.assertEqual(progress_percent("downloading", 50, 100), 50)
        self.assertEqual(progress_percent("queued", 0, None), None)
        self.assertEqual(speed_text("downloading", 2048), "2.0 KB/s")
        self.assertEqual(format_bytes(None), "—")

    def test_paused_progress_is_kept(self) -> None:
        self.assertEqual(progress_text("paused", 50, 100, None), "已暂停 · 50%")
        self.assertEqual(progress_text("paused", 0, None, None), "已暂停")
        self.assertEqual(progress_percent("paused", 50, 100), 50)
        self.assertEqual(progress_text("starting", 0, None, None), "等待启动")


class CookieTests(unittest.TestCase):
    def test_browser_tuple_and_bot_message(self) -> None:
        opts: dict = {}
        with patch("app.core.cookies.uses_app_bound_encryption", return_value=False):
            apply_cookies(opts, cookiefile=None, browser="edge")
            self.assertEqual(opts["cookiesfrombrowser"], ("edge", None, None, None))
            text = explain_error("ERROR: [youtube] abc: Sign in to confirm you're not a bot.")
        self.assertIn("设置", text)
        self.assertNotIn("http", text)
        apply_cookies(opts, cookiefile="cookies.txt", browser="")
        self.assertEqual(opts["cookiefile"], "cookies.txt")

    def test_cookiefile_is_used_through_a_writable_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "export.txt"
            source.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            cache = Path(tmp) / "cache"
            opts: dict = {}
            with patch("app.core.cookies.cache_dir", return_value=cache):
                apply_cookies(opts, cookiefile=str(source), browser="")
            copy = Path(opts["cookiefile"])
            self.assertNotEqual(copy, source)
            self.assertTrue(copy.is_file())
            self.assertEqual(copy.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            # yt-dlp saves the jar back into whatever path it was given; that
            # must hit the copy, never the user's own file.
            copy.write_text("# rewritten by yt-dlp\n", encoding="utf-8")
            self.assertEqual(source.read_text(encoding="utf-8"), "# Netscape HTTP Cookie File\n")

    def test_cookiefile_path_is_kept_when_it_cannot_be_copied(self) -> None:
        opts: dict = {}
        apply_cookies(opts, cookiefile="cookies.txt", browser="")
        self.assertEqual(opts["cookiefile"], "cookies.txt")

    def test_app_bound_browser_is_skipped(self) -> None:
        opts: dict = {}
        with patch("app.core.cookies.uses_app_bound_encryption", return_value=True):
            apply_cookies(opts, cookiefile="cookies.txt", browser="chrome")
            reason = browser_cookie_block_reason("chrome")
            text = explain_error("Sign in to confirm you're not a bot")
        self.assertNotIn("cookiesfrombrowser", opts)
        self.assertEqual(opts["cookiefile"], "cookies.txt")
        self.assertIn("cookies.txt", reason or "")
        self.assertIn("cookies.txt", text)


class SimplifyTests(unittest.TestCase):
    def test_playlist_skips_entries_without_url(self) -> None:
        info = simplify(
            {
                "_type": "playlist",
                "title": "List",
                "entries": [
                    {"id": "abc", "title": "One", "url": "https://example.com/watch?v=abc"},
                    {"id": "nope", "title": "Missing"},
                ],
            },
            "https://example.com/playlist",
        )
        self.assertEqual(info["kind"], "playlist")
        self.assertEqual(len(info["entries"]), 1)

    def test_youtube_flat_entry_uses_id(self) -> None:
        info = simplify(
            {
                "_type": "playlist",
                "title": "List",
                "entries": [{"id": "abc", "title": "One", "ie_key": "Youtube"}],
            },
            "https://www.youtube.com/playlist?list=PL",
        )
        self.assertEqual(info["entries"][0]["url"], "https://www.youtube.com/watch?v=abc")

    def test_video_drops_storyboards(self) -> None:
        info = simplify(
            {
                "_type": "video",
                "id": "abc",
                "title": "Demo",
                "formats": [
                    {"format_id": "sb0", "ext": "mhtml", "format_note": "storyboard", "vcodec": "none", "acodec": "none"},
                    {"format_id": "18", "ext": "mp4", "height": 360, "vcodec": "avc1", "acodec": "mp4a", "tbr": 500},
                ],
            },
            "https://example.com/watch",
        )
        self.assertEqual(info["kind"], "video")
        self.assertEqual([item["format_id"] for item in info["formats"]], ["18"])


class PathTests(unittest.TestCase):
    def test_writable_rejects_path_under_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "file"
            blocker.write_text("x", encoding="utf-8")
            self.assertFalse(paths.is_writable(blocker / "sub"))

    def test_app_data_dir_skips_unwritable_candidates(self) -> None:
        blocked = Path("C:/definitely/not/writable")
        good = Path(tempfile.gettempdir()) / "ytdlp-paths-test"
        with patch.object(paths, "_data_dir_candidates", return_value=[blocked, good]):
            with patch.object(paths, "is_writable", side_effect=lambda p: p == good):
                with patch.object(paths, "_app_data_dir", None):
                    self.assertEqual(paths.app_data_dir(), good)


class SettingsTests(unittest.TestCase):
    def test_values_persist_between_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(paths, "_app_data_dir", Path(tmp)):
                with patch.object(Settings, "_migrate_from_registry"):
                    first = Settings()
                    first.set_download_dir(Path(tmp) / "movies")
                    first.set_cookiefile("cookies.txt")
                    first.set_max_concurrent(4)
                    self.assertTrue(first.sync())
                    self.assertTrue(first.path.exists())

                    second = Settings()
                    self.assertEqual(second.download_dir(), Path(tmp) / "movies")
                    self.assertEqual(second.cookiefile(), "cookies.txt")
                    self.assertEqual(second.max_concurrent(), 4)
                    del first, second

    def test_legacy_registry_values_are_migrated(self) -> None:
        class FakeQSettings:
            Status = QSettings.Status

            def __init__(self, *args, **kwargs):
                pass

            def status(self):
                return QSettings.Status.NoError

            def contains(self, key):
                return key == "cookiefile"

            def value(self, key):
                return "G:/download/cookies.txt"

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(paths, "_app_data_dir", Path(tmp)):
                with patch.object(Settings, "_migrate_from_registry"):
                    settings = Settings()
                with patch("app.core.settings.QSettings", FakeQSettings):
                    settings._migrate_from_registry()
                self.assertEqual(settings.cookiefile(), "G:/download/cookies.txt")
                del settings


class QueueGuardTests(unittest.TestCase):
    class FakeSettings:
        def __init__(self, directory: Path) -> None:
            self._directory = directory

        def download_dir(self) -> Path:
            return self._directory

        def max_concurrent(self) -> int:
            return 2

        def ffmpeg_override(self) -> str:
            return ""

        def existing_cookiefile(self):
            return None

        def browser(self) -> str:
            return ""

        def subtitle_langs(self) -> list[str]:
            return ["zh-Hans"]

    def test_unwritable_download_dir_pauses_the_queue(self) -> None:
        from app.core.queue import JobQueue

        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "file"
            blocker.write_text("x", encoding="utf-8")
            store = Store(Path(tmp) / "jobs.db")
            queue = JobQueue(store, self.FakeSettings(blocker / "sub"))
            messages: list[str] = []
            queue.logged.connect(messages.append)
            job = new_job(
                url="https://example.com/a",
                title="A",
                preset="1080p",
                format_selector=None,
                subtitles=False,
            )
            queue.enqueue(job)
            self.assertFalse(queue.has_running())
            self.assertEqual(store.get(job.id).status, "queued")
            queue.start([job.id])
            self.assertFalse(queue.has_running())
            self.assertEqual(store.get(job.id).status, "queued")
            self.assertTrue(any("不可写" in message for message in messages), messages)
            store.close()


class QueueStartTests(unittest.TestCase):
    def _queue(self, tmp: Path):
        from app.core.queue import JobQueue

        store = Store(tmp / "jobs.db")
        queue = JobQueue(store, QueueGuardTests.FakeSettings(tmp / "downloads"))
        return store, queue

    @staticmethod
    def _job():
        return new_job(
            url="https://example.com/a",
            title="A",
            preset="1080p",
            format_selector=None,
            subtitles=False,
        )

    def test_enqueue_waits_for_an_explicit_start(self) -> None:
        from app.core.queue import JobQueue

        with tempfile.TemporaryDirectory() as tmp:
            store, queue = self._queue(Path(tmp))
            with patch.object(JobQueue, "_start", return_value=True) as start:
                job = self._job()
                queue.enqueue(job)
                self.assertFalse(start.called)
                self.assertEqual(store.get(job.id).status, "queued")
                self.assertIsNone(store.next_starting())
            store.close()

    def test_start_moves_the_job_to_starting_and_pumps(self) -> None:
        from app.core.queue import JobQueue

        with tempfile.TemporaryDirectory() as tmp:
            store, queue = self._queue(Path(tmp))
            job = self._job()
            queue.enqueue(job)

            def fake_start(target):
                store.update(target.id, status="downloading")
                return True

            with patch.object(JobQueue, "_start", side_effect=fake_start) as start:
                queue.start([job.id])
                self.assertTrue(start.called)
                self.assertEqual(store.get(job.id).status, "downloading")
            store.close()

    def test_pause_marks_queued_job_as_paused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, queue = self._queue(Path(tmp))
            job = self._job()
            queue.enqueue(job)
            queue.pause([job.id])
            self.assertEqual(store.get(job.id).status, "paused")
            store.close()


class StoreTests(unittest.TestCase):
    def test_queue_order_and_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "jobs.db")
            first = new_job(url="https://example.com/a", title="A", preset="1080p", format_selector=None, subtitles=False)
            second = new_job(url="https://example.com/b", title="B", preset="audio", format_selector=None, subtitles=True)
            store.insert_many([first, second])
            self.assertEqual(store.next_queued().id, first.id)
            store.update(first.id, status="downloading", downloaded=10)
            self.assertEqual(store.next_queued().id, second.id)
            self.assertEqual(store.fail_interrupted(), 1)
            failed = store.get(first.id)
            self.assertEqual(failed.status, "failed")
            self.assertIn("中断", failed.error or "")
            listed = store.list_jobs()
            self.assertEqual(listed[0].id, second.id)
            store.delete(second.id)
            self.assertIsNone(store.get(second.id))
            store.close()

    def test_starting_jobs_are_reset_on_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "jobs.db")
            job = new_job(url="https://example.com/a", title="A", preset="1080p", format_selector=None, subtitles=False)
            store.insert(job)
            store.update(job.id, status="starting")
            self.assertEqual(store.next_starting().id, job.id)
            self.assertEqual(store.reset_starting(), 1)
            self.assertIsNone(store.next_starting())
            self.assertEqual(store.get(job.id).status, "queued")
            store.close()


if __name__ == "__main__":
    unittest.main()
