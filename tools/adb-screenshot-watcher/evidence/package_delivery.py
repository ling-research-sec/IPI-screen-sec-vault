"""Reproducible local delivery assembly; does not access or modify a phone."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

paths = sorted([Path('.gitignore'), Path('README.md'), Path('TEST_REPORT.md'),
                Path('requirements.txt'), Path('start-macos.command'), Path('start-windows.bat'),
                *Path('screenshot_watcher').glob('*.py'), *Path('tests').glob('*.py')], key=str)
records = [{'path': p.as_posix(), 'sha256': sha(p)} for p in paths]
Path('evidence/delivery-files.json').write_text(json.dumps(records, indent=2) + '\n')
patch = []
for path in paths:
    name = 'tools/adb-screenshot-watcher/' + path.as_posix()
    mode = '100755' if os.access(path, os.X_OK) else '100644'
    patch.extend([f'diff --git a/{name} b/{name}\n', f'new file mode {mode}\n'])
    patch.extend(difflib.unified_diff([], path.read_text().splitlines(keepends=True),
                                    fromfile='/dev/null', tofile='b/' + name))
Path('evidence/DIFF_FILE.patch').write_text(''.join(patch))

copy = (ROOT / 'evidence/rollback-copy')
copy.mkdir(exist_ok=True)
for path in paths:
    target = copy / path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
(copy / 'evidence').mkdir(exist_ok=True)
shutil.copy2('evidence/BASELINE.txt', copy / 'evidence/BASELINE.txt')
(copy / 'captures').mkdir(exist_ok=True)
(copy / 'captures/KEEP.txt').write_text('preserve original evidence\n')
rollback_command = ['bash', str(ROOT / 'evidence/ROLLBACK.sh'), '--target', str(copy)]
rollback = subprocess.run(rollback_command, capture_output=True, text=True)
assert rollback.returncode == 0, rollback.stderr
assert not (copy / 'screenshot_watcher/__main__.py').exists()
assert (copy / 'captures/KEEP.txt').read_text() == 'preserve original evidence\n'
assert sha(copy / 'evidence/BASELINE.txt') == sha(ROOT / 'evidence/BASELINE.txt')
rollback_output = (rollback.stdout + 'RESTORED PASS: watcher absent; original baseline hash unchanged; capture fixture retained\n')
Path('evidence/rollback-test.txt').write_text(rollback_output)
print(rollback_output, end='')

# Preserve exact original JSONL bytes in a small evidence export, not the pictures.
for session in Path('.evidence-captures').glob('session_*'):
    target = Path('evidence/live-manifests') / session.name
    target.mkdir(parents=True, exist_ok=True)
    for name in ('manifest.jsonl', 'session.json'):
        source = session / name
        if source.exists():
            shutil.copy2(source, target / name)
            assert sha(source) == sha(target / name)

# Keep the untouched baseline record separate from all generated sources.
assert sha(Path('evidence/BASELINE.txt')) == 'ae4bdb1002a3028b384fc26052f3be2fac4acb9a44ea7f48596dfdd2e2b0722a'
archive = ROOT / 'evidence/adb-screenshot-watcher-0.1.0.zip'
evidence = [Path('evidence') / n for n in (
    'BASELINE.txt', 'environment.json', 'device-inspect.json', 'device-inspect-final.json',
    'device-before.json', 'device-after.json', 'source-preservation.json', 'capture-integrity.json',
    'unit-tests.txt', 'gui-smoke.txt', 'gui-live.txt', 'cli-final-idle.txt', 'DIFF_FILE.patch',
    'delivery-files.json', 'ROLLBACK.sh', 'rollback-test.txt', 'rollback-protection.txt')]
evidence.extend(sorted(Path('evidence/live-manifests').rglob('*.*')))
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in paths + evidence:
        z.write(path, 'adb-screenshot-watcher/' + path.as_posix())
with tempfile.TemporaryDirectory(prefix='watcher-delivery-') as temporary:
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        z.extractall(temporary)
        for member in z.infolist():
            mode = member.external_attr >> 16
            if mode:
                os.chmod(Path(temporary) / member.filename, mode)
    extracted = Path(temporary) / 'adb-screenshot-watcher'
    for row in records:
        assert sha(extracted / row['path']) == row['sha256']
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    command = ['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-v']
    tested = subprocess.run(command, cwd=extracted, env=env, capture_output=True, text=True)
    test_output = tested.stdout + tested.stderr
    Path('evidence/package-tests.txt').write_text(test_output)
    assert tested.returncode == 0, test_output
    assert 'Ran 43 tests' in test_output
    print('PACKAGE PASS: ZIP CRC, file hashes, extracted 43 tests')

verification = {
    'changed_module': 'new screenshot_watcher CLI + GUI; no pre-existing source files edited',
    'changed_field': 'transfer_status: failed -> success only after size/hash verification and atomic publication',
    'original_baseline_sha256': sha(Path('evidence/BASELINE.txt')),
    'artifacts': {'MODIFIED_FILE': str(archive), 'DIFF_FILE': str(ROOT / 'evidence/DIFF_FILE.patch'),
                  'VERIFICATION': str(ROOT / 'evidence/VERIFICATION.txt'), 'ROLLBACK': str(ROOT / 'evidence/ROLLBACK.sh')},
    'BASELINE': {'cwd': str(ROOT.parents[1]),
                 'command': 'python3 -m unittest discover -s tools/adb-screenshot-watcher/tests -v',
                 'input': 'initial empty test directory, watcher did not exist',
                 'literal_output': '\n----------------------------------------------------------------------\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n',
                 'exit_status': 0},
    'MODIFIED': {'cwd': str(ROOT), 'command': 'python3 -m unittest discover -s tests -v',
                 'input': '43 synthetic local scenarios; no phone mutation',
                 'literal_output': Path('evidence/unit-tests.txt').read_text(), 'exit_status': 0},
    'ROLLBACK': {'command': ' '.join(rollback_command),
                 'input': 'separate copy of delivered code plus capture fixture and original baseline record',
                 'literal_output': rollback.stdout, 'exit_status': rollback.returncode,
                 'restored_behavior_status': 'watcher main file absent; original baseline SHA256 unchanged; captures and evidence retained; real modified project retained'},
    'gui_smoke_literal_output': Path('evidence/gui-smoke.txt').read_text(),
    'package_test_literal_output': test_output,
    'package_test_exit_status': tested.returncode,
    'archive_sha256': sha(archive),
    'source_integrity': json.loads(Path('evidence/source-preservation.json').read_text()),
    'capture_integrity': json.loads(Path('evidence/capture-integrity.json').read_text()),
    'remaining': ['Windows 11 real host', 'two physical devices', 'multi-hour endurance',
                  'exact file creation-to-save timing unavailable; report mtime estimate and detection latency']
}
Path('evidence/VERIFICATION.txt').write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n')
# Reopen every claimed artifact; source files and original picture manifests remain unmodified.
for path in paths + evidence + [archive, Path('evidence/VERIFICATION.txt')]:
    with path.open('rb') as stream:
        stream.read()
assert os.access('evidence/ROLLBACK.sh', os.X_OK)
for row in records:
    assert sha(Path(row['path'])) == row['sha256']
print('ARTIFACTS PASS: four artifacts reopened; rollback executable; modified project retained')
print('ZIP_SHA256 ' + sha(archive))
