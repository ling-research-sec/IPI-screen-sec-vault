from pathlib import Path
import hashlib,json,shutil,difflib,subprocess,sys
repo=Path.cwd();o=repo/'26-11-08/p1-migration-repair';r=repo/'26-11-05/tools/gemini-memory-lab'
f=r/'core/progress.py';before=f.read_text();(o/'original.py').write_text(before)
reg=r/'.state/9f77f5d185a0b2f4924c160c.json';shutil.copy2(reg,o/'device-registry-before.json')
# Preserve a complete evidence fingerprint before administrative changes.
e=r/'evidence';hashes={str(p.relative_to(e)):hashlib.sha256(p.read_bytes()).hexdigest() for p in e.rglob('*') if p.is_file() and p.name!='.DS_Store'}
(o/'evidence-before.json').write_text(json.dumps(hashes))
needle="    raw=path/'_debug' if (path/'_debug/result.json').exists() else path\n"
insert="""    if (path/'input.json').is_file() and not (path/'result.json').exists():
        try:
            protocol=json.loads((path/'input.json').read_text()).get('inputs',{}).get('config',{})
        except (ValueError,OSError):
            protocol={}
        if 'p3' in path.parts and protocol:
            raise LabError('此设备保留 P3 日历流程断点（input/checkpoints 格式），请核对并交接 P3；不会按 P1 result.json 读取或重复发送：'+str(path))
"""
assert before.count(needle)==1
f.write_text(before.replace(needle,insert+needle));shutil.copy2(f,o/'MODIFIED_FILE.py')
(o/'DIFF_FILE.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),f.read_text().splitlines(True),fromfile=str(f)+'.before',tofile=str(f))))
# Old directory contains only empty folders and Finder metadata; preserve it whole.
old=repo/'tools/gemini-memory-lab'
assert not old.is_symlink()
assert not [p for p in old.rglob('*') if p.is_file() and p.name!='.DS_Store']
old.rename(o/'old-path-skeleton');old.symlink_to(Path('../26-11-05/tools/gemini-memory-lab'),target_is_directory=True)
print('PATCH_AND_COMPATIBILITY_OK')
