#!/usr/bin/env python3
from pathlib import Path
import difflib,hashlib,json,os,shlex,shutil,subprocess
W=Path(__file__).resolve().parent
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
Q=lambda p:shlex.quote(str(p))
diff=''.join(''.join(difflib.unified_diff((W/'baseline'/n).read_text().splitlines(True),(W/'runner'/n).read_text().splitlines(True),fromfile='baseline/'+n,tofile='runner/'+n)) for n in ['pipeline.py','report.mjs'])
(W/'changes.diff').write_text(diff)
target=W/'rollback-verification';shutil.copytree(W/'runner',target,dirs_exist_ok=True)
commands={
 'BASELINE':'set -o pipefail; python3 "$W/baseline/test_pipeline.py" 2>&1 | tail -1',
 'MODIFIED':'set -o pipefail; python3 "$W/runner/test_pipeline.py" 2>&1 | tail -1 && python3 "$W/runner/test_conditions.py" 2>&1 | tail -1',
 'ROLLBACK':'set -o pipefail; "$W/ROLLBACK.sh" "$W/rollback-verification" && python3 "$W/rollback-verification/test_pipeline.py" 2>&1 | tail -1'
}
results={}
for name,command in commands.items():
 result=subprocess.run(['/bin/zsh','-c',command],capture_output=True,text=True,env={**os.environ,'W':str(W)})
 results[name]={'command':command,'environment':{'W':str(W)},'input':'No stdin; isolated offline FakeDevice fixtures; no Android requests','literal_stdout':result.stdout,'literal_stderr':result.stderr,'exit_status':result.returncode}
 assert result.returncode==0,(name,result.stdout,result.stderr)
for name in ['pipeline.py','report.mjs']:
 assert H(target/name)==H(W/'baseline'/name)
 assert H(W/'runner'/name)!=H(W/'baseline'/name)
 original=Path('/Users/y4n9/.codex/skills/android-screen-readability/scripts')/name
 assert H(original)==H(W/'baseline'/name)
root=W.parents[2]
old=json.loads((W/'experiment1-readonly-before.json').read_text())
changed=[p for p,h in old.items() if not (root/p).is_file() or H(root/p)!=h]
assert not changed,changed
records=list((root/'26-10-27/exp2-perplexity/evidence-01/records').glob('exp2-result-*.json'))
paths={'MODIFIED_FILE':str(W/'runner/pipeline.py'),'DIFF_FILE':str(W/'changes.diff'),'VERIFICATION':str(W/'VERIFICATION.txt'),'ROLLBACK':str(W/'ROLLBACK.sh')}
text='Changed fields: Config.conditions; recorded font_px/delta_g; scored round/font/gray; filtered XLSX A9:M with J字号/KΔg/L轮次/M CER; historical 48px 3-round mean comparison; merged titles. Acquisition, scoring and unfinished-state guards reused.\n'
text+='\n'.join(k+'='+v for k,v in paths.items())+'\n\n'
for name,result in results.items():text+=name+'\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n\n'
text+=f'Restored behavior/status: disposable rollback copy matches original pipeline.py and report.mjs byte-for-byte; original offline tests return OK, exit0. Modified runner remains changed.\nExperiment1 read-only: {len(old)} historical files unchanged. Original Skill files unchanged.\nObserved valid real records at this check: {len(records)}/160; this is not a completion assertion.\n'
(W/'VERIFICATION.txt').write_text(text)
for p in map(Path,paths.values()):assert p.is_file() and p.read_bytes()
assert os.access(W/'ROLLBACK.sh',os.X_OK)
(W/'implementation-verification.json').write_text(json.dumps({'results':results,'paths':paths,'baseline_sha256':{n:H(W/'baseline'/n) for n in ['pipeline.py','report.mjs']},'modified_sha256':{n:H(W/'runner'/n) for n in ['pipeline.py','report.mjs']},'restored_status':'PASS','experiment1_unchanged_files':len(old)},ensure_ascii=False,indent=2)+'\n')
print('BASELINE: OK / exit0; MODIFIED: OK + OK / exit0; ROLLBACK: restored + OK / exit0')
print(f'EXPERIMENT1: {len(old)} files unchanged; modified copy retained; four artifacts reopened')
