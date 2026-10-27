#!/bin/sh
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET=${1:?Pass a disposable runner-copy directory}
cp "$BASE/baseline/pipeline.py" "$TARGET/pipeline.py"
printf "%s\n" "ROLLBACK PASS: source-fidelity guard reverted in test copy"
