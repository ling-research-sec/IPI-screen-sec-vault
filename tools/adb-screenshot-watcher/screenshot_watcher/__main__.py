"""CLI entry point; GUI is imported only when requested."""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

from .adb import Adb, AdbError, validate_directory
from .storage import Store, utc_now
from .watcher import Watcher


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="原始 Android 截图自动收集（不会主动截图）")
    root.add_argument("--adb", default="adb", help="ADB 可执行文件路径")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("devices", help="列出全部设备及状态")
    inspect = commands.add_parser("inspect", help="只读检查截图目录和设备能力")
    watch = commands.add_parser("watch", help="命令行监听；Ctrl+C 停止")
    for sub in (inspect, watch):
        sub.add_argument("--serial", required=True, help="固定目标 serial，断线也不切换设备")
        sub.add_argument("--remote-dir", action="append", type=validate_directory,
                         help="自定义截图专用目录，可多次传入；替代自动发现")
    watch.add_argument("--output", type=Path, default=Path("captures"))
    watch.add_argument("--interval", type=float, default=.5, help="轮询周期下限，秒")
    watch.add_argument("--stable-for", type=float, default=.5, help="至少两轮未变化且稳定的秒数")
    gui = commands.add_parser("gui", help="Tkinter 桌面界面")
    gui.add_argument("--output", type=Path, default=Path("captures"))
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    stop = threading.Event()
    try:
        if args.command == "devices":
            devices = Adb(executable=args.adb, stop=stop).devices()
            for device in devices:
                print(f"{device.serial}\t{device.state}\t{device.details}")
            if not devices:
                print("未检测到 ADB 设备")
            return 0
        if args.command == "gui":
            from .gui import launch
            launch(args.adb, args.output)
            return 0
        adb = Adb(args.serial, args.adb, stop)
        if args.command == "inspect":
            directories, notes = adb.discover(args.remote_dir)
            files = adb.scan(directories)
            # Inspect hashes one existing image, without copying or modifying it.
            sample = files[0] if files else None
            print(json.dumps({"serial": args.serial, "state": adb.state(), "directories": directories,
                              "notes": notes, "existing_file_count": len(files),
                              "sample": sample.__dict__ if sample else None,
                              "sample_sha256": adb.sha256(sample.path) if sample else None,
                              "clock": adb.clock()}, ensure_ascii=False, indent=2))
            return 0
        # Validate all numeric arguments before creating a session directory.
        if not .05 <= args.interval <= 3600 or not .05 <= args.stable_for <= 3600:
            raise ValueError("interval 和 stable-for 必须在 0.05～3600 秒之间")
        store = Store(args.output, args.serial)
        def emit(kind, value):
            print(json.dumps({"at": utc_now(), "event": kind, "value": value},
                             ensure_ascii=False), flush=True)
        def terminate(signum, frame):
            stop.set()
        previous = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, terminate)
        try:
            Watcher(adb, store, args.remote_dir, args.interval, args.stable_for, stop, emit).run()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        return 0
    except (AdbError, OSError, ValueError, ImportError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
