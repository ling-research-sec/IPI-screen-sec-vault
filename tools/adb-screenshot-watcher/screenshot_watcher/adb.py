"""Serial-bound ADB operations. Never restart/kill the shared ADB server."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class AdbError(RuntimeError):
    pass


class Cancelled(AdbError):
    pass


@dataclass(frozen=True)
class Device:
    serial: str
    state: str
    details: str = ""


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    mtime: int
    ctime: int
    inode: str
    mtime_full: str
    ctime_full: str

    @property
    def identity(self) -> tuple:
        return (self.path, self.size, self.mtime, self.ctime, self.inode,
                self.mtime_full, self.ctime_full)

    @property
    def version(self) -> tuple:
        return (self.path, self.size, self.inode, self.mtime_full)


EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".avif", ".bmp", ".gif"}
PREFERRED = ("/sdcard/Pictures/Screenshots", "/sdcard/DCIM/Screenshots")
STAT_FORMAT = "%s|%Y|%Z|%i|%y|%z"


def validate_directory(value: str) -> str:
    if not value.startswith("/") or "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("截图目录必须是绝对 Android 路径，且不能包含换行或 NUL")
    return str(PurePosixPath(value))


def parse_stat(path: str, raw: str) -> RemoteFile:
    fields = raw.strip().split("|")
    if len(fields) != 6:
        raise AdbError(f"stat 格式异常: {path}: {raw!r}")
    try:
        return RemoteFile(path, int(fields[0]), int(fields[1]), int(fields[2]), *fields[3:])
    except ValueError as exc:
        raise AdbError(f"stat 数字字段异常: {path}") from exc


class Adb:
    def __init__(self, serial: str | None = None, executable: str = "adb",
                 stop: threading.Event | None = None, timeout: float = 15):
        self.serial = serial
        self.executable = executable
        self.stop = stop if stop is not None else threading.Event()
        self.timeout = timeout

    def run(self, args: list[str], *, global_command: bool = False,
            timeout: float | None = None) -> bytes:
        if self.stop.is_set():
            raise Cancelled("已停止")
        if global_command:
            if args != ["devices", "-l"]:
                raise ValueError("只有设备枚举允许不指定 serial")
            command = [self.executable, *args]
        else:
            if not self.serial:
                raise ValueError("ADB 操作需要指定 serial")
            command = [self.executable, "-s", self.serial, *args]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=flags)
        except OSError as exc:
            raise AdbError(f"启动 ADB 失败: {exc}") from exc
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        try:
            while True:
                if self.stop.is_set():
                    raise Cancelled("已停止；中止本工具的 ADB 客户端")
                if time.monotonic() >= deadline:
                    raise AdbError(f"ADB 超时 ({args[0]})")
                try:
                    output, error = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                message = error.decode("utf-8", "replace").strip()
                raise AdbError(message or f"ADB exit={process.returncode}")
            return output
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()

    def shell(self, script: str) -> bytes:
        return self.run(["shell", script])

    def devices(self) -> list[Device]:
        output = self.run(["devices", "-l"], global_command=True).decode("utf-8", "replace")
        devices = []
        for line in output.splitlines():
            fields = line.split(maxsplit=2)
            if len(fields) >= 2 and not line.startswith(("List of", "*")):
                devices.append(Device(fields[0], fields[1], fields[2] if len(fields) > 2 else ""))
        return devices

    def state(self) -> str:
        return self.run(["get-state"]).decode().strip()

    def discover(self, custom: list[str] | None = None) -> tuple[list[str], list[str]]:
        paths = [validate_directory(p) for p in custom] if custom else list(PREFERRED)
        notes = []
        if not custom:
            found = self.shell("; ".join(
                f"if [ -d {shlex.quote(p)} ]; then printf '%s\\n' {shlex.quote(p)}; fi"
                for p in paths)).decode("utf-8").splitlines()
            notes.append("优先目录: " + (", ".join(found) if found else "尚未建立"))
            if not found:
                where = ("_data LIKE '%/Screenshot%/%' OR _data LIKE '%/截屏/%' "
                         "OR _data LIKE '%/截图/%'")
                query = shlex.join(["content", "query", "--uri", "content://media/external/images/media",
                                    "--projection", "_data", "--where", where])
                try:
                    output = self.shell(query).decode("utf-8")
                    if "Error" in output or "Exception" in output:
                        notes.append("MediaStore 查询未获授权或不受支持；可设置自定义目录")
                    for line in output.splitlines():
                        match = re.match(r"Row: \d+ _data=(/.*)", line)
                        if match:
                            parent = validate_directory(str(PurePosixPath(match[1]).parent))
                            if parent not in paths:
                                paths.append(parent)
                except AdbError as exc:
                    notes.append(f"MediaStore: {exc}；可设置自定义目录")
        canonical = []
        for path in paths:
            output = self.shell(f"readlink -f {shlex.quote(path)} 2>/dev/null || true").decode("utf-8").strip()
            normalized = validate_directory(output) if output.startswith("/") else path
            if normalized not in canonical:
                canonical.append(normalized)
        notes.append("监听目录（未建立的目录也会继续检查）: " + ", ".join(canonical))
        return canonical, notes

    def scan(self, directories: list[str]) -> list[RemoteFile]:
        quoted = " ".join(shlex.quote(validate_directory(p)) for p in directories)
        script = f'''for d in {quoted}; do
if [ ! -d "$d" ]; then continue; fi
if [ ! -r "$d" ] || [ ! -x "$d" ]; then echo 'directory unreadable' >&2; exit 1; fi
for f in "$d"/*; do
if [ -f "$f" ]; then
printf '%s\\0' "$f"
stat -c {shlex.quote(STAT_FORMAT)} "$f" || exit 1
fi
done
done'''
        output = self.shell(script)
        files = []
        cursor = 0
        while cursor < len(output):
            try:
                split = output.index(b"\x00", cursor)
                end = output.index(b"\n", split + 1)
                path = output[cursor:split].decode("utf-8")
                raw = output[split + 1:end].decode("utf-8")
            except (ValueError, UnicodeError) as exc:
                raise AdbError("目录扫描输出不完整；本轮未更新基线") from exc
            if PurePosixPath(path).suffix.lower() in EXTENSIONS:
                files.append(parse_stat(path, raw))
            cursor = end + 1
        return files

    def stat(self, path: str) -> RemoteFile:
        return parse_stat(path, self.shell(
            f"stat -c {shlex.quote(STAT_FORMAT)} {shlex.quote(path)}").decode("utf-8"))

    def sha256(self, path: str) -> str:
        raw = self.shell(f"sha256sum {shlex.quote(path)}").decode("utf-8")
        match = re.match(r"\\?([0-9a-fA-F]{64})\s", raw)
        if not match:
            raise AdbError(f"设备 SHA-256 输出异常: {path}")
        return match[1].lower()

    def pull(self, source: str, destination: Path) -> None:
        self.run(["pull", source, str(destination)], timeout=120)

    def clock(self) -> dict:
        before = time.time()
        raw = self.shell("date +%s.%N").decode().strip()
        after = time.time()
        precise = bool(re.fullmatch(r"\d+\.\d{1,9}", raw))
        seconds = float(raw) if precise else float(raw.split(".", 1)[0])
        return {"device_minus_host_seconds": seconds - (before + after) / 2,
                "uncertainty_seconds": (0 if precise else 1) + (after - before) / 2,
                "device_date_precision": "fractional" if precise else "seconds"}
