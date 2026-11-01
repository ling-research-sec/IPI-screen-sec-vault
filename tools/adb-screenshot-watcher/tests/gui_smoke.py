"""Real Tk smoke test; no phone and no display automation are required beyond Tk."""
import json
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from screenshot_watcher.gui import Window
from test_watcher import FakeAdb


def main():
    with tempfile.TemporaryDirectory() as temporary:
        adb = FakeAdb()
        adb.devices = lambda: []
        with patch('screenshot_watcher.gui.Adb', return_value=adb):
            root = tk.Tk()
            window = Window(root, 'adb', Path(temporary))
            deadline = time.monotonic() + 3
            while window.refresh_worker.is_alive() and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            window.drain()
            window.device_map = {'TARGET [device]': 'TARGET'}
            window.device.set('TARGET [device]')
            window.start()
            deadline = time.monotonic() + 4
            while not (window.store.directory / 'session.json').exists() and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            assert (window.store.directory / 'session.json').exists(), 'baseline not established'
            adb.add('gui.png', b'GUI original bytes')
            deadline = time.monotonic() + 5
            while window.store.count < 1 and time.monotonic() < deadline:
                root.update()
                time.sleep(.02)
            window.drain()
            assert window.count.get() == '1', 'count not updated'
            assert Path(window.latest.get()).read_bytes() == b'GUI original bytes'
            window.stop_watch()
            deadline = time.monotonic() + 3
            while window.worker.is_alive() and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            window.drain()
            assert not window.worker.is_alive(), 'worker leaked'
            assert str(window.start_button['state']) == 'normal'
            window.close()
            root.mainloop()
            assert not window.refresh_worker.is_alive(), 'device refresh leaked'
    print('GUI_SMOKE PASS: refresh/start/count/latest/stop/close; no worker leak')


if __name__ == '__main__':
    main()
