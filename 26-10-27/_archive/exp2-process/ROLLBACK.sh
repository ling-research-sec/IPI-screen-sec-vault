#!/bin/sh
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET=${1:?Usage: ROLLBACK.sh /absolute/path/to/disposable-runner-copy}
[ -d "$TARGET" ]
cp "$BASE/baseline/pipeline.py" "$TARGET/pipeline.py"
cp "$BASE/baseline/report.mjs" "$TARGET/report.mjs"
printf '%s\n' 'ROLLBACK PASS: original pipeline.py and report.mjs restored'
