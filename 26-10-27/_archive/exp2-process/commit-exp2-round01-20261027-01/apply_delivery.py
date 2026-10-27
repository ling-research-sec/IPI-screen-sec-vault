#!/usr/bin/env python3
"""Install a prepared delivery into a verified target copy or formal directory."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
REPO = WORK.parents[3]
STAGE = WORK / 'staging'
BASELINE = json.loads((WORK / 'baseline/formal-sha256.json').read_text(encoding='utf-8'))
PLAN = json.loads((WORK / 'delivery-plan.json').read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: apply_delivery.py TARGET_EXPERIMENT_DIRECTORY')
    target = Path(sys.argv[1]).resolve()
    if target == (REPO / '26-10-27/exp2-perplexity').resolve():
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
        if head != BASELINE['git_head']:
            raise RuntimeError('repository HEAD changed since baseline')
        if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=REPO).returncode != 0:
            raise RuntimeError('staging area is not empty')
    actual = {str(p.relative_to(target)): digest(p) for p in target.rglob('*') if p.is_file() and p.name != '.DS_Store'}
    if actual != BASELINE['files']:
        raise RuntimeError('target differs from baseline; refusing to install')
    for rel, value in PLAN['added_files'].items():
        if (target / rel).exists() or digest(STAGE / rel) != value:
            raise RuntimeError(f'new file collision or staging hash mismatch: {rel}')
    if digest(STAGE / '实验说明.md') != PLAN['modified_notes_sha256']:
        raise RuntimeError('modified notes hash mismatch')
    temp = target / '.实验说明.md.delivery-tmp'
    if temp.exists():
        raise RuntimeError('notes temporary file already exists')
    for rel in PLAN['added_files']:
        src, dest = STAGE / rel, target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as out, src.open('rb') as inp:
            shutil.copyfileobj(inp, out)
    shutil.copy2(STAGE / '实验说明.md', temp)
    os.replace(temp, target / '实验说明.md')
    print(f'APPLY: added_files={len(PLAN["added_files"])} modified_notes=1')
    print('APPLY: PASS')


if __name__ == '__main__':
    main()
