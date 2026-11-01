"""Small Tkinter interface. Only the main thread touches Tk widgets."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .adb import Adb, validate_directory
from .storage import Store
from .watcher import Watcher


class Window:
    def __init__(self, root: tk.Tk, executable: str, output: Path):
        self.root = root
        self.executable = executable
        self.events: queue.Queue = queue.Queue()
        self.stop = threading.Event()
        self.refresh_stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.refresh_worker: threading.Thread | None = None
        self.closing = False
        self.store = None
        self.status = tk.StringVar(value="正在检测设备")
        self.output = tk.StringVar(value=str(output.expanduser().resolve()))
        self.device = tk.StringVar()
        self.remote = tk.StringVar()
        self.interval = tk.StringVar(value="0.5")
        self.count = tk.StringVar(value="0")
        self.latest = tk.StringVar(value="—")
        self.device_map: dict[str, str] = {}
        root.title("ADB Screenshot Watcher")
        root.geometry("820x610")
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="ADB 设备").grid(row=0, column=0, sticky="w")
        self.selector = ttk.Combobox(frame, textvariable=self.device, state="readonly", width=65)
        self.selector.grid(row=0, column=1, sticky="ew", padx=6)
        self.refresh_button = ttk.Button(frame, text="刷新设备", command=self.refresh)
        self.refresh_button.grid(row=0, column=2)
        ttk.Label(frame, text="连接状态").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Label(frame, textvariable=self.status, wraplength=650).grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Label(frame, text="保存目录").grid(row=2, column=0, sticky="w")
        self.output_entry = ttk.Entry(frame, textvariable=self.output)
        self.output_entry.grid(row=2, column=1, sticky="ew", padx=6)
        self.browse_button = ttk.Button(frame, text="选择…", command=self.browse)
        self.browse_button.grid(row=2, column=2)
        ttk.Label(frame, text="截图目录（可选）").grid(row=3, column=0, sticky="w", pady=6)
        self.remote_entry = ttk.Entry(frame, textvariable=self.remote)
        self.remote_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Label(frame, text="留空自动发现；多个 Android 截图专用目录以分号分隔").grid(
            row=4, column=1, columnspan=2, sticky="w")
        ttk.Label(frame, text="轮询间隔（秒）").grid(row=5, column=0, sticky="w", pady=6)
        self.interval_entry = ttk.Entry(frame, textvariable=self.interval, width=10)
        self.interval_entry.grid(row=5, column=1, sticky="w", padx=6)
        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="w", pady=8)
        self.start_button = ttk.Button(buttons, text="开始监听", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="停止监听", command=self.stop_watch, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Label(buttons, text="本次已保存：").pack(side="left", padx=(15, 0))
        ttk.Label(buttons, textvariable=self.count).pack(side="left")
        ttk.Label(frame, text="最新截图").grid(row=7, column=0, sticky="nw")
        ttk.Label(frame, textvariable=self.latest, wraplength=650).grid(row=7, column=1, columnspan=2, sticky="w")
        self.logs = scrolledtext.ScrolledText(frame, height=18, state="disabled", wrap="word")
        self.logs.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=10)
        frame.rowconfigure(8, weight=1)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.root.after(100, self.drain)

    def emit(self, kind, value):
        self.events.put((kind, value))

    def log(self, text):
        self.logs.configure(state="normal")
        self.logs.insert("end", f"{datetime.now():%H:%M:%S} {text}\n")
        lines = int(self.logs.index("end-1c").split(".")[0])
        if lines > 1000:
            self.logs.delete("1.0", f"{lines - 1000}.0")
        self.logs.see("end")
        self.logs.configure(state="disabled")

    def refresh(self):
        if self.closing or (self.refresh_worker and self.refresh_worker.is_alive()):
            return
        self.refresh_button.configure(state="disabled")
        def work():
            try:
                self.emit("devices", Adb(executable=self.executable, stop=self.refresh_stop).devices())
            except Exception as exc:
                self.emit("device_error", str(exc))
        self.refresh_worker = threading.Thread(target=work, name="adb-device-list")
        self.refresh_worker.start()

    def browse(self):
        value = filedialog.askdirectory(initialdir=self.output.get(), parent=self.root)
        if value:
            self.output.set(value)

    def controls(self, running):
        for widget in (self.output_entry, self.remote_entry, self.interval_entry, self.browse_button):
            widget.configure(state="disabled" if running else "normal")
        self.selector.configure(state="disabled" if running else "readonly")
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        serial = self.device_map.get(self.device.get())
        if not serial:
            messagebox.showinfo("请选择设备", "请选择目标 ADB 设备，再开始监听。", parent=self.root)
            return
        try:
            interval = float(self.interval.get())
            if not .05 <= interval <= 3600:
                raise ValueError("轮询间隔必须在 0.05～3600 秒之间")
            custom = [validate_directory(p.strip()) for p in self.remote.get().split(";") if p.strip()] or None
            store = Store(Path(self.output.get()), serial)
        except (OSError, ValueError) as exc:
            messagebox.showerror("配置错误", str(exc), parent=self.root)
            return
        self.stop = threading.Event()
        adb = Adb(serial, self.executable, self.stop)
        watcher = Watcher(adb, store, custom, interval=interval, stop=self.stop, emit=self.emit)
        self.store = store
        self.count.set("0")
        self.latest.set("—")
        self.status.set("正在连接并建立基线，请等待‘基线完成’")
        self.controls(True)
        def work():
            try:
                watcher.run()
            except Exception as exc:
                self.emit("log", f"后台任务异常: {exc}")
            finally:
                self.emit("finished", None)
        self.worker = threading.Thread(target=work, name="adb-screenshot-watcher")
        self.worker.start()

    def stop_watch(self):
        self.stop.set()
        self.stop_button.configure(state="disabled")
        self.status.set("正在停止；重新开始时会排除停止期间的截图")

    def drain(self):
        for _ in range(200):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "devices":
                old_serial = self.device_map.get(self.device.get())
                self.device_map = {f"{d.serial}  [{d.state}]  {d.details}": d.serial for d in value}
                self.selector["values"] = list(self.device_map)
                selected = next((label for label, serial in self.device_map.items() if serial == old_serial), None)
                if selected:
                    self.device.set(selected)
                elif not self.worker or not self.worker.is_alive():
                    self.device.set(next(iter(self.device_map), ""))
                self.refresh_button.configure(state="normal")
                if not self.worker or not self.worker.is_alive():
                    self.status.set("已检测到设备；选择后开始监听" if value else "未检测到设备")
            elif kind == "device_error":
                self.log(value)
                self.refresh_button.configure(state="normal")
                if not self.worker or not self.worker.is_alive():
                    self.status.set(value)
            elif kind == "status":
                self.status.set(value)
                self.log(value)
            elif kind == "ready":
                self.log(f"基线完成，排除 {value['baseline']} 张已有截图；现在可手动截图。会话: {value['session']}")
            elif kind == "saved":
                self.count.set(str(self.store.count))
                self.latest.set(value["local_path"])
                self.log(f"已保存 #{value['sequence']}，SHA-256 一致；检测至保存 {value['detection_to_saved_seconds']:.3f}s")
            elif kind == "finished":
                self.controls(False)
                self.status.set("已停止；再次开始会建立新基线")
            else:
                self.log(str(value))
        if self.closing:
            active = any(t and t.is_alive() for t in (self.worker, self.refresh_worker))
            if not active:
                self.root.destroy()
                return
        self.root.after(100, self.drain)

    def close(self):
        self.closing = True
        self.stop.set()
        self.refresh_stop.set()
        self.start_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.status.set("正在清理本工具的后台任务…")


def launch(executable="adb", output=Path("captures")):
    root = tk.Tk()
    Window(root, executable, output)
    root.mainloop()
