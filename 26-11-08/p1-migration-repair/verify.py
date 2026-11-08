from pathlib import Path
import sys,tempfile,subprocess,shutil,json,hashlib
r=Path('26-11-05/tools/gemini-memory-lab').resolve();o=Path('26-11-08/p1-migration-repair').resolve()
probe="""from core.progress import read_run
from pathlib import Path
import tempfile,json
with tempfile.TemporaryDirectory() as t:
 p=Path(t)/'p3/第3轮/case04/_debug/attempt-002';p.mkdir(parents=True)
 (p/'input.json').write_text(json.dumps({'inputs':{'config':{'serial':'TEST'}}}))
 try:read_run(p)
 except Exception as e:print(type(e).__name__)
"""
for mode in ['BASELINE','MODIFIED','ROLLBACK']:
 with tempfile.TemporaryDirectory() as t:
  shutil.copytree(r/'core',Path(t)/'core',ignore=shutil.ignore_patterns('__pycache__'))
  if mode!='MODIFIED':shutil.copy2(o/'original.py',Path(t)/'core/progress.py')
  result=subprocess.run([sys.executable,'-c',probe],cwd=t,capture_output=True,text=True)
  expected='LabError' if mode=='MODIFIED' else 'FileNotFoundError'
  assert result.returncode==0 and result.stdout.strip()==expected,(mode,result.stderr)
  print(mode,'input=P3 input/checkpoints without result.json','output='+result.stdout.strip(),'exit=0')
print('OLD_PATH_TARGET',Path('tools/gemini-memory-lab').resolve()==r)
before=json.loads((o/'evidence-before.json').read_text());e=r/'evidence'
assert all((e/p).is_file() and hashlib.sha256((e/p).read_bytes()).hexdigest()==h for p,h in before.items())
print('EVIDENCE_UNCHANGED',len(before))
