"""Read-only local/source integrity check for all sessions below a capture root."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from screenshot_watcher.adb import Adb
from screenshot_watcher.storage import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', required=True)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    adb = Adb(args.serial)
    root = args.captures.resolve()
    manifests = [root / 'manifest.jsonl'] if (root / 'manifest.jsonl').exists() else sorted(root.glob('session_*/manifest.jsonl'))
    if not manifests:
        parser.error('no manifest.jsonl found')
    failures = []
    count = 0
    attempts_failed = 0
    sessions = []
    for manifest in manifests:
        rows = [json.loads(line) for line in manifest.read_text(encoding='utf-8').splitlines()]
        successes = [r for r in rows if r['transfer_status'] == 'success']
        attempts_failed += len(rows) - len(successes)
        seen = set()
        for record in successes:
            try:
                assert record['device_serial'] == args.serial, 'serial mismatch'
                local = manifest.parent / Path(record['local_path']).name
                assert str(local) not in seen, 'duplicate local path'
                seen.add(str(local))
                assert local.stat().st_size == record['file_size'], 'size mismatch'
                local_hash = digest(local)
                assert local_hash == record['sha256'] == adb.sha256(record['source_path']), 'SHA256 mismatch'
                count += 1
            except Exception as exc:
                failures.append({'source': record['source_path'], 'error': str(exc)})
        assert not list(manifest.parent.glob('*.part')), 'temporary file remains'
        sessions.append({'session': manifest.parent.name, 'success': len(successes),
                         'failed_attempts': len(rows) - len(successes)})
    report = {'verified': count, 'failed_attempts_logged': attempts_failed, 'integrity_errors': failures,
              'sessions': sessions, 'result': 'PASS' if not failures else 'FAIL'}
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.write_text(output, encoding='utf-8')
    print(output, end='')
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
