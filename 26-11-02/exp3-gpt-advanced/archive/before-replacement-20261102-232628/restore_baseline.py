from pathlib import Path
import hashlib, json, shutil, sys

A = Path(__file__).resolve().parent
LIVE = A.parents[1]
assert len(sys.argv) == 2, 'Usage: ROLLBACK.sh EMPTY_TARGET_DIRECTORY'
target = Path(sys.argv[1]).resolve()
assert target != LIVE and LIVE not in target.parents, 'Use an independent destination outside the live experiment.'
assert not target.exists() or not any(target.iterdir()), 'Destination must be new or empty.'
target.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
for name in ['GPT_Advanced_实验结果03.xlsx', '实验说明.md']:
    shutil.copy2(A / name, target / name)
shutil.copytree(A / 'evidence', target / 'evidence', dirs_exist_ok=True)
rows = json.loads((A / 'evidence/scored_records.json').read_text())['records']
changes = {x['condition_id']: x for x in json.loads((A / 'replacement_manifest.json').read_text())}
for row in rows:
    source = Path(changes[row['condition_id']]['archived_file']) if row['condition_id'] in changes else Path(row['file'])
    assert sha(source) == row['sha256']
    dest = target / 'evidence/screenshots' / str(row['font_px']) / Path(row['file']).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    assert sha(dest) == row['sha256']
assert len(list((target / 'evidence/screenshots').rglob('*.png'))) == 192
expected = json.loads((A / 'BASELINE_HASHES.json').read_text())['GPT_Advanced_实验结果03.xlsx']
assert sha(target / 'GPT_Advanced_实验结果03.xlsx') == expected
sys.path.insert(0, '/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault/26-11-01/exp1-gpt-advanced/archive/_work')
from assess import readbook
s, r = readbook(target / 'GPT_Advanced_实验结果03.xlsx')
assert int(s['F4']['value']) == 192 and int(s['B203']['value']) == 6354
assert sum(s.get(f'B{i}', {}).get('value') not in (None, '') for i in range(10, 202)) == 190
print('ROLLBACK PASS images=192 scored=190 correct=6354 original_hash_restored=True')
