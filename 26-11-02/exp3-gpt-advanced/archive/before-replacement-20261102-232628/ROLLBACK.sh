#!/bin/sh
set -eu
test "$#" -eq 1 || { echo 'Usage: ROLLBACK.sh EMPTY_TARGET_DIRECTORY' >&2; exit 2; }
exec python3 "$(dirname "$0")/restore_baseline.py" "$1"
