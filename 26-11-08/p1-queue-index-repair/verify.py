from pathlib import Path
import tempfile,shutil,subprocess,sys,json
r=Path('tools/gemini-memory-lab').resolve();o=Path('26-11-08/p1-queue-index-repair').resolve()
probe="""from core import p1_queue_recovery as q
from types import SimpleNamespace
from core.state import LabError
if not hasattr(q,'preflight_queue_records'):print('MISSING_GATE')
else:
 try:q.preflight_queue_records([SimpleNamespace(case_id='a',row=33)],{}, {'a':{'run_dir':'/nonexistent-P1-test'}})
 except LabError:print('BLOCKED_BEFORE_EXECUTION')
"""
for mode in ['BASELINE','MODIFIED','ROLLBACK']:
 with tempfile.TemporaryDirectory() as t:
  shutil.copytree(r/'core',Path(t)/'core',ignore=shutil.ignore_patterns('__pycache__'))
  if mode!='MODIFIED':
   for p in (o/'original').iterdir():shutil.copy2(p,Path(t)/'core'/p.name)
  result=subprocess.run([sys.executable,'-c',probe],cwd=t,capture_output=True,text=True)
  assert result.returncode==0,result.stderr
  assert result.stdout.strip()==('BLOCKED_BEFORE_EXECUTION' if mode=='MODIFIED' else 'MISSING_GATE')
  print(mode,'input=missing indexed case33',result.stdout.strip(),'exit=0')
sys.path.insert(0,str(r))
from core.case_loader import load_cases,FORMAL_WORKBOOK
from core.p1_queue_recovery import preflight_queue_records
from core.state import LabError
cs=load_cases(FORMAL_WORKBOOK);entries=json.loads((r/'.state/progress/976fe33e949195be98aa6c70.json').read_text())['cases']
jobs=[c for c in cs if 33<=c.row<=47 and c.row!=36]
try:preflight_queue_records(jobs,{'evidence_root':str(r/'evidence'),'p1_round':6},entries)
except LabError as e:
 print('LIVE_READONLY_GATE',str(e).splitlines()[0]);assert '14条' in str(e)
else:raise AssertionError('missing gate')
ids=[1,2,9,33,37,39,40,41,42,43,56,58,59,60,62,64,65,66,67,68,78,82]
manifest={'status':'prepared_not_started','policy':'recover original post conversation first; no automatic resubmission','source_round':4,'target_round':None,'cases':[{'case':c.case_index,'row':c.row,'case_id':c.case_id,'scenario':c.scenario} for c in cs if c.case_index in ids]}
assert len(manifest['cases'])==22
(o/'22条补测清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print('SUPPLEMENT_MANIFEST=22 PREPARED_NOT_STARTED')
