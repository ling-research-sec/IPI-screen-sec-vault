"""Play one bundled prompt on the Mac, never on the connected phone."""
from pathlib import Path
import subprocess
from catalog import Problem
from android import Stopped

PROMPT=Path(__file__).resolve().parent/'assets'/'prompt.mp3'

def play_after_success(cancel, status):
    status('共享已就绪，等待 1 秒')
    if cancel.wait(1.0):raise Stopped('本轮已停止。')
    status('电脑正在播放提示词')
    if cancel.is_set():raise Stopped('本轮已停止。')
    with subprocess.Popen(['/usr/bin/afplay',str(PROMPT)],stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as player:
        while player.poll() is None:
            if cancel.wait(.05):
                if player.poll() is None:player.terminate()
                try:player.wait(timeout=2)
                except subprocess.TimeoutExpired:player.kill()
                raise Stopped('已停止播放。')
        if player.returncode:raise Problem('电脑播放提示词失败；本轮未推进。')
    if cancel.is_set():raise Stopped('本轮已停止。')
