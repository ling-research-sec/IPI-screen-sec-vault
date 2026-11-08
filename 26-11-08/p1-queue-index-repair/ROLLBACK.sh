#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$#" -eq 1 ] || { echo 'Usage: ROLLBACK.sh disposable-core-directory'; exit 2; }
[ -f "$1/gui.py" ] || exit 2
for name in progress.py gui.py p1_queue_recovery.py; do cp "$HERE/original/$name" "$1/$name"; done
echo 'RESTORED original code; evidence and indices untouched'
