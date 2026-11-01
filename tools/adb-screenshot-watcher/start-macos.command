#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec "${PYTHON:-python3}" -m screenshot_watcher --adb "${ADB:-adb}" gui "$@"
