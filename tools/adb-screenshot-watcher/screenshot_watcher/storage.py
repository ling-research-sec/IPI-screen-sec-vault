"""Original-byte storage with atomic publication and durable JSONL records."""
from __future__ import annotations

import hashlib
import ctypes
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .adb import AdbError, RemoteFile


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_rename(source: Path, target: Path) -> None:
    """Publish without replacing an existing path (including a competing writer)."""
    if sys.platform == "darwin":
        # Apple sys/stdio.h: RENAME_EXCL = 0x00000004, available since macOS 10.12.
        rename = ctypes.CDLL(None, use_errno=True).renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        if rename(os.fsencode(source), os.fsencode(target), 4) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(target))
    elif os.name == "nt":
        os.rename(source, target)
    else:
        # Useful for running the offline tests on other POSIX hosts as well.
        os.link(source, target)
        source.unlink()


def mtime_epoch(remote: RemoteFile) -> float:
    match = re.fullmatch(r"(.{19})\.(\d+) ([+-]\d{4})", remote.mtime_full)
    if not match:
        return float(remote.mtime)
    wall_time = datetime.strptime(match[1] + " " + match[3], "%Y-%m-%d %H:%M:%S %z")
    return wall_time.timestamp() + float("0." + match[2])


class Store:
    def __init__(self, root: Path, serial: str):
        root = root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        base = "session_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        self.directory = root / base
        suffix = 0
        while True:
            try:
                self.directory.mkdir()
                break
            except FileExistsError:
                suffix += 1
                self.directory = root / f"{base}_{suffix:02d}"
        self.serial = serial
        self.sequence = 0
        self.count = 0
        self.manifest = self.directory / "manifest.jsonl"
        self.manifest.touch(exist_ok=False)
        self.clock_info: dict = {}

    def append(self, record: dict) -> None:
        data = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        with self.manifest.open("ab", buffering=0) as stream:
            original_size = stream.tell()
            try:
                view = memoryview(data)
                while view:
                    count = stream.write(view)
                    if not count:
                        raise OSError("manifest 写入未完成")
                    view = view[count:]
                os.fsync(stream.fileno())
            except OSError:
                # A failed success-record must not survive while its image is rolled back.
                os.ftruncate(stream.fileno(), original_size)
                raise

    def metadata(self, value: dict) -> None:
        temporary = self.directory / ".session.json.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.directory / "session.json")

    def record(self, sequence: int, remote: RemoteFile, detected_at: str) -> dict:
        return {"sequence": sequence, "device_serial": self.serial, "detected_at": detected_at,
                "source_path": remote.path, "local_path": None, "file_size": remote.size,
                "sha256": None, "transfer_status": "failed", "error_message": None,
                "source_mtime": remote.mtime_full, "source_ctime": remote.ctime_full,
                "source_inode": remote.inode}

    def collect(self, adb, remote: RemoteFile, detected_at: str, detected_monotonic: float) -> dict:
        self.sequence += 1
        record = self.record(self.sequence, remote, detected_at)
        fd, name = tempfile.mkstemp(prefix=".transfer_", suffix=".part", dir=self.directory)
        os.close(fd)
        temporary = Path(name)
        published = None
        try:
            if adb.stat(remote.path).identity != remote.identity:
                raise AdbError("源文件元数据已变化，等待下一次稳定观察")
            before_hash = adb.sha256(remote.path)
            adb.pull(remote.path, temporary)
            local_hash = digest(temporary)
            after = adb.stat(remote.path)
            after_hash = adb.sha256(remote.path)
            if after.identity != remote.identity:
                raise AdbError("传输期间源文件变化，等待重试")
            if temporary.stat().st_size != remote.size or local_hash != before_hash or local_hash != after_hash:
                raise AdbError("大小或 SHA-256 不一致，临时文件已弃用")
            # Windows FlushFileBuffers (used by fsync) needs a writable handle.
            # Opening the local temporary file read/write does not rewrite its bytes.
            with temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            extension = PurePosixPath(remote.path).suffix
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            final = self.directory / f"{self.sequence:04d}_{stamp}{extension}"
            atomic_rename(temporary, final)
            published = final
            saved_epoch = time.time()
            record.update(local_path=str(final), sha256=local_hash, source_sha256=after_hash,
                          transfer_status="success", saved_at=utc_now(),
                          detection_to_saved_seconds=round(time.monotonic() - detected_monotonic, 6))
            if self.clock_info:
                # stat mtime is write time, not necessarily the screenshot's creation time.
                estimate = saved_epoch - (mtime_epoch(remote) - self.clock_info["device_minus_host_seconds"])
                record["source_mtime_to_saved_seconds_estimate"] = round(estimate, 6)
                record["clock_uncertainty_seconds"] = self.clock_info["uncertainty_seconds"]
            self.append(record)
            self.count += 1
            return record
        except Exception as exc:
            # Roll back only this uncommitted local publication, never touch device files.
            if published is not None:
                published.unlink(missing_ok=True)
            record.update(local_path=None, sha256=None, transfer_status="failed", error_message=str(exc))
            self.append(record)
            raise
        finally:
            temporary.unlink(missing_ok=True)
