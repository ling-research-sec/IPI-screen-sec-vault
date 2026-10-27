#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then
  echo 'usage: ROLLBACK.sh TARGET_EXPERIMENT_DIRECTORY' >&2
  exit 2
fi
WORK=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 - "$WORK" "$1" <<'PY'
import hashlib, json, os, shutil, sys
from pathlib import Path

work, target = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
before = json.loads((work / 'baseline/formal-sha256.json').read_text(encoding='utf-8'))
plan = json.loads((work / 'delivery-plan.json').read_text(encoding='utf-8'))
H = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
if not (target / 'evidence-01').is_dir():
    raise SystemExit('ROLLBACK: invalid target')
for rel, expected in before['files'].items():
    path = target / rel
    if rel == '实验说明.md':
        if not path.is_file() or H(path) not in (expected, plan['modified_notes_sha256']):
            raise SystemExit('ROLLBACK: notes changed independently; no files removed')
    elif not path.is_file() or H(path) != expected:
        raise SystemExit(f'ROLLBACK: baseline file changed independently: {rel}; no files removed')
for rel, expected in plan['added_files'].items():
    path = target / rel
    if path.exists() and (not path.is_file() or path.is_symlink() or H(path) != expected):
        raise SystemExit(f'ROLLBACK: added file changed independently: {rel}; no files removed')
if H(work / 'baseline/实验说明.md') != before['files']['实验说明.md']:
    raise SystemExit('ROLLBACK: notes backup mismatch; no files removed')
tmp = target / '.实验说明.md.rollback-tmp'
if tmp.exists():
    raise SystemExit('ROLLBACK: temporary file already exists; no files removed')
removed = 0
for rel in plan['added_files']:
    path = target / rel
    if path.exists():
        path.unlink()
        removed += 1
roots = [target / 'evidence-01/ui',
         target / 'evidence-01/excluded/attempt-01-f16-g01-interrupted',
         target / 'evidence-01/excluded/fidelity-pre-send-f16-g01']
roots += [target / 'evidence-01/excluded/fidelity-superseded-20261027' / case / 'ui' for case in plan['retested_cases']]
for root in roots:
    if root.exists():
        for d in sorted((p for p in root.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try: d.rmdir()
            except OSError: pass
        try: root.rmdir()
        except OSError: pass
note = target / '实验说明.md'
restored = H(note) != before['files']['实验说明.md']
if restored:
    shutil.copy2(work / 'baseline/实验说明.md', tmp)
    os.replace(tmp, note)
for rel, expected in before['files'].items():
    if not (target / rel).is_file() or H(target / rel) != expected:
        raise SystemExit(f'ROLLBACK: restored verification failed: {rel}')
print(f'ROLLBACK: removed={removed} restored_notes={"YES" if restored else "ALREADY_BASELINE"} baseline_files={len(before["files"])}')
print('ROLLBACK: PASS')
PY
