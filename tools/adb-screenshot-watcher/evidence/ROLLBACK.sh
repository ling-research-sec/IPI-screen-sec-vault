#!/bin/sh
# Explicit target only. Verify all delivered code hashes before removing any code.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" - "$SCRIPT_DIR/delivery-files.json" "$@" <<'PY'
import argparse
import hashlib
import json
from pathlib import Path
import sys

manifest = Path(sys.argv[1])
parser = argparse.ArgumentParser(description='Remove this delivery only; preserve captures/evidence and subsequent edits')
parser.add_argument('--target', type=Path, required=True)
args = parser.parse_args(sys.argv[2:])
root = args.target.resolve(strict=True)
rows = json.loads(manifest.read_text(encoding='utf-8'))
for row in rows:
    relative = Path(row['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise SystemExit('ROLLBACK STOP: invalid manifest path')
    path = root / relative
    if path.is_symlink() or root not in path.resolve().parents:
        raise SystemExit('ROLLBACK STOP: unexpected link')
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise SystemExit('ROLLBACK STOP: delivery file is missing or changed: ' + str(path))
for row in rows:
    (root / row['path']).unlink()
for parent in sorted({(root / r['path']).parent for r in rows}, key=lambda p: len(p.parts), reverse=True):
    if parent == root:
        continue
    try:
        parent.rmdir()
    except OSError:
        pass
print('ROLLBACK PASS: delivered code removed; captures and evidence preserved')
PY
