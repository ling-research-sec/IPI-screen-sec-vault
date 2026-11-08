from pathlib import Path
import shutil,difflib,json,hashlib
r=Path('tools/gemini-memory-lab').resolve();o=Path('26-11-08/p1-queue-index-repair').resolve();(o/'original').mkdir(exist_ok=True)
for name in ['p1_queue_recovery.py','gui.py','progress.py']:
 p=r/'core'/name;shutil.copy2(p,o/'original'/name)
p=r/'core/p1_queue_recovery.py';s=p.read_text();s+='''

def preflight_queue_records(jobs, config, entries, deferred=None):
    """Read-only gate: absent evidence is unknown, never proof of no submission."""
    errors=[]
    for case in jobs:
        try:
            path=queued_run_path(case,config,entries.get(case.case_id,{}),(deferred or {}).get(case.case_id))
            if path is None:
                continue
            if not path.is_dir() or not ((path/'result.json').is_file() or (path/'_debug/result.json').is_file()):
                errors.append(f'Excel第{case.row}行：{path}')
                continue
            read_run(path)  # Reject corrupt records before a worker touches the phone.
        except (OSError, ValueError, LabError) as exc:
            errors.append(f'Excel第{case.row}行：{exc}')
    if errors:
        raise LabError('队列未启动：'+str(len(errors))+'条旧证据缺失或不可读；未执行、未重发、未改完成状态。'
                       +'请恢复原记录，或明确建立独立新轮补测；缺文件不代表从未发送。\\n'+'\\n'.join(errors))
''';p.write_text(s)
p=r/'core/gui.py';s=p.read_text();needle="            # A prior report records outcomes, never which jobs to skip on a new click."
assert s.count(needle)==1
s=s.replace(needle,"            from .p1_queue_recovery import preflight_queue_records\n            preflight_queue_records(jobs,config,store.read()['cases'],deferred)\n"+needle);p.write_text(s)
p=r/'core/progress.py';s=p.read_text();needle="    result=json.loads((raw/'result.json').read_text())";assert s.count(needle)==1
s=s.replace(needle,"    if not (raw/'result.json').is_file():\n        raise LabError('旧证据记录缺失：'+str(raw/'result.json')+'；保留原提交状态，请恢复文件或明确新轮补测，不自动重发')\n"+needle);p.write_text(s)
diff=''
for name in ['p1_queue_recovery.py','gui.py','progress.py']:
 a=(o/'original'/name).read_text();b=(r/'core'/name).read_text();diff+=''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='original/'+name,tofile='modified/'+name))
(o/'DIFF_FILE.patch').write_text(diff);(o/'MODIFIED_FILE').mkdir(exist_ok=True)
for name in ['p1_queue_recovery.py','gui.py','progress.py']:shutil.copy2(r/'core'/name,o/'MODIFIED_FILE'/name)
(o/'original-hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (o/'original').iterdir()}))
print('PATCHED 3 files')
