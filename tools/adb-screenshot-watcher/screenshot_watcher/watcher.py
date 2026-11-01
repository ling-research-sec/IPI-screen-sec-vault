"""Polling state machine, separate from ADB, persistence, and UI."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from .adb import AdbError, Cancelled, RemoteFile
from .storage import utc_now


@dataclass
class Pending:
    remote: RemoteFile
    stable_since: float
    detected_at: str
    detected_monotonic: float
    observations: int = 1
    attempts: int = 0
    retry_after: float = 0


class Watcher:
    def __init__(self, adb, store, directories: list[str] | None = None,
                 interval: float = .5, stable_for: float = .5,
                 stop: threading.Event | None = None, emit: Callable | None = None):
        if not .05 <= interval <= 3600 or not .05 <= stable_for <= 3600:
            raise ValueError("interval 和 stable-for 必须在 0.05～3600 秒之间")
        self.adb = adb
        self.store = store
        self.custom = directories
        self.interval = interval
        self.stable_for = stable_for
        self.stop = stop if stop is not None else adb.stop
        self.emit = emit or (lambda kind, value: None)
        self.directories: list[str] = []
        self.seen: set[tuple] = set()
        self.saved_versions: dict[tuple, str] = {}
        self.pending: dict[str, Pending] = {}
        self.initialized = False
        self.last_status = ""
        self.was_disconnected = False

    def status(self, value: str) -> None:
        if value != self.last_status:
            self.emit("status", value)
            self.last_status = value

    def initialize(self) -> None:
        self.directories, notes = self.adb.discover(self.custom)
        for note in notes:
            self.emit("log", note)
        files = self.adb.scan(self.directories)
        self.seen = {f.identity for f in files}
        # One-time, device-local hashes prevent old files with delayed ctime-only
        # MediaStore updates from being mistaken for newly created screenshots.
        self.saved_versions = {f.version: self.adb.sha256(f.path) for f in files if f.size > 0}
        try:
            self.store.clock_info = self.adb.clock()
        except (AdbError, ValueError) as exc:
            self.emit("log", f"时钟估计未完成: {exc}")
        self.store.metadata({"device_serial": self.adb.serial, "baseline_at": utc_now(),
                             "baseline_file_count": len(files), "directories": self.directories,
                             "interval_seconds": self.interval, "stable_for_seconds": self.stable_for,
                             "clock": self.store.clock_info,
                             "latency_note": "mtime is not creation time; wall-clock estimate only"})
        self.initialized = True
        self.emit("ready", {"baseline": len(files), "session": str(self.store.directory)})

    def process(self, files: list[RemoteFile], now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        detected_at = utc_now()
        ready = []
        present = {f.path for f in files}
        for path in list(self.pending):
            if path not in present:
                del self.pending[path]
        for remote in sorted(files, key=lambda f: (f.mtime_full, f.path)):
            if self.stop.is_set():
                return
            if remote.identity in self.seen:
                self.pending.pop(remote.path, None)
                continue
            candidate = self.pending.get(remote.path)
            if candidate is None:
                self.pending[remote.path] = Pending(remote, now, detected_at, now)
                continue
            if candidate.remote.identity != remote.identity:
                # Keep the first detection time, but reset stability after any write.
                candidate.remote = remote
                candidate.stable_since = now
                candidate.observations = 1
                candidate.attempts = 0
                candidate.retry_after = 0
                continue
            candidate.observations += 1
            if (remote.size <= 0 or candidate.observations < 2
                    or now - candidate.stable_since < self.stable_for or now < candidate.retry_after):
                continue
            ready.append(candidate)
        # Register the entire snapshot before any blocking transfers. Otherwise later
        # files in a burst acquire artificial detection timestamps after earlier pulls.
        for candidate in ready:
            if self.stop.is_set():
                return
            remote = candidate.remote
            try:
                saved_hash = self.saved_versions.get(remote.version)
                if saved_hash is not None and self.adb.sha256(remote.path) == saved_hash:
                    # MediaStore can update ctime after a successful save without
                    # changing the image. A content change still gets collected.
                    self.seen.add(remote.identity)
                    self.pending.pop(remote.path, None)
                    self.emit("log", f"仅元数据变化，已排除重复: {remote.path}")
                    continue
                record = self.store.collect(self.adb, remote, candidate.detected_at,
                                            candidate.detected_monotonic)
            except Cancelled:
                raise
            except (AdbError, OSError, ValueError) as exc:
                candidate.attempts += 1
                candidate.retry_after = time.monotonic() + min(30, 2 ** min(candidate.attempts - 1, 5))
                self.emit("log", f"传输失败，将重试: {remote.path}: {exc}")
            else:
                self.seen.add(remote.identity)
                self.saved_versions[remote.version] = record["sha256"]
                self.pending.pop(remote.path, None)
                self.emit("saved", record)

    def tick(self) -> None:
        state = self.adb.state()
        if state != "device":
            raise AdbError(f"设备状态: {state}")
        if not self.initialized:
            self.initialize()
        if self.was_disconnected:
            # Do not rebuild baseline on transient disconnection: retain new files from the gap.
            for candidate in self.pending.values():
                candidate.stable_since = time.monotonic()
                candidate.observations = 0
            try:
                self.store.clock_info = self.adb.clock()
            except (AdbError, ValueError):
                pass
            self.was_disconnected = False
        self.status("监听中")
        self.process(self.adb.scan(self.directories))

    def run(self) -> None:
        try:
            while not self.stop.is_set():
                started = time.monotonic()
                try:
                    self.tick()
                except Cancelled:
                    break
                except (AdbError, OSError, ValueError) as exc:
                    self.was_disconnected = True
                    self.status(f"暂停检测，等待恢复: {exc}")
                self.stop.wait(max(0, self.interval - (time.monotonic() - started)))
        finally:
            self.status("已停止")
