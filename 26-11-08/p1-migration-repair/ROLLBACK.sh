#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$#" -eq 1 ] || { echo 'Usage: ROLLBACK.sh disposable-core-directory'; exit 2; }
[ -f "$1/progress.py" ] || exit 2
cp "$HERE/original.py" "$1/progress.py"
echo 'RESTORED original progress reader; administrative handoff and evidence unchanged'
