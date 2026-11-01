"""Opt-in interactive validation against a specified real phone; manual screenshot only."""
import argparse
import json
import time
import tkinter as tk
from pathlib import Path

from screenshot_watcher.gui import Window


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', required=True)
    args = parser.parse_args()
    root = tk.Tk()
    window = Window(root, 'adb', Path('.evidence-captures'))
    started = False
    ready = False
    deadline = time.monotonic() + 240
    def poll():
        nonlocal started, ready
        if time.monotonic() >= deadline:
            print('GUI_LIVE TIMEOUT', flush=True)
            window.close()
            return
        if not started and (not window.refresh_worker or not window.refresh_worker.is_alive()):
            selected = next((label for label, serial in window.device_map.items() if serial == args.serial), None)
            if selected:
                window.device.set(selected)
                window.start()
                started = True
        if started and not ready and window.status.get() == '监听中':
            print('GUI_LIVE READY: ' + str(window.store.directory), flush=True)
            ready = True
        if ready and window.store.count:
            print('GUI_LIVE SAVED: ' + window.latest.get(), flush=True)
            window.close()
            return
        root.after(100, poll)
    root.after(200, poll)
    root.mainloop()
    if window.store and window.store.count:
        print('GUI_LIVE PASS: saved=' + str(window.store.count) + '; all workers stopped', flush=True)
    else:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
