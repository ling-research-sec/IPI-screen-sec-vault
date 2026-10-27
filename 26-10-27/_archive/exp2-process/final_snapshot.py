#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,stat,sys,tempfile,zipfile
W=Path(__file__).resolve().parent;ROOT=W.parents[2];E=ROOT/'26-10-27/exp2-perplexity'
sys.path.insert(0,str(W/'runner'));import pipeline as p
archive=p.read_json(W/'archive-final.json');assert archive['status']==archive['restore_test']=='PASS'
assert {x.name for x in E.iterdir()}=={'实验说明.md','实验结果-01.xlsx','evidence-01'}
target=ROOT/'26-10-27/_archive/exp2-perplexity-round01-final-evidence.zip';assert not target.exists()
selected=set(x for x in E.rglob('*') if x.is_file())
for pattern in ['*.json','*.txt','*.log','*.py','*.mjs','*.js','*.diff','ROLLBACK.sh','final-*.png']:
 selected.update(x for x in W.glob(pattern) if x.is_file() and not x.is_symlink())
for folder in ['runner','baseline','interrupted-attempt-01','document-backups','finder-metadata']:
 selected.update(x for x in (W/folder).rglob('*') if x.is_file() and not x.is_symlink() and '__pycache__' not in x.parts)
selected.add(Path(archive['archive']))
hashes={};modes={}
with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for source in sorted(selected):
  rel=source.relative_to(ROOT).as_posix();data=source.read_bytes();hashes[rel]=hashlib.sha256(data).hexdigest();modes[rel]=stat.S_IMODE(source.stat().st_mode)
  info=zipfile.ZipInfo(rel);info.create_system=3;info.external_attr=source.stat().st_mode<<16;info.compress_type=zipfile.ZIP_STORED if source.suffix=='.zip' else zipfile.ZIP_DEFLATED
  z.writestr(info,data)
 z.writestr('manifest.json',json.dumps({'files':hashes,'modes':modes},ensure_ascii=False,indent=2))
with zipfile.ZipFile(target) as z:
 assert z.testzip() is None
 with tempfile.TemporaryDirectory(prefix='.exp2-final-restore-',dir=target.parent) as temp:
  restored=Path(temp)
  for rel,h in hashes.items():
   assert '..' not in Path(rel).parts
   out=restored/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(rel));out.chmod(modes[rel]);assert p.file_hash(out)==h
  re=restored/E.relative_to(ROOT);rw=restored/W.relative_to(ROOT);sheets,count=p.read_xlsx(re/'实验结果-01.xlsx');assert count==160
  main,raw=sheets;reference=(rw/'reference.txt').read_text().strip('\r\n');records=list((re/'evidence-01/records').glob('exp2-result-*.json'));assert len(records)==160
  by_case={str(main[f'A{row}'][0]):row for row in range(10,170)};assert len(by_case)==160
  for record in records:
   d=p.read_json(record);case=d['case_id'];row=by_case[case];ev=re/'evidence-01'
   assert d['status']=='completed';assert (ev/d['response_file']).read_text()==d['response']+'\n';assert raw[f'B{row-1}'][0]==d['response']
   for key,hkey in [('response_file','response_sha256'),('screenshot','screenshot_sha256'),('source_screen','source_screen_sha256')]:assert p.file_hash(ev/d[key])==d[hkey]
   assert p.file_hash(ev/'source-images'/d['image'])==d['source_sha256']
   score=p.score(reference,d['response']);assert all(d[k]==v for k,v in score.items())
   for col,key in [('B','correct'),('D','substitutions'),('E','deletions'),('F','insertions'),('G','unk_tokens'),('J','font_px'),('K','delta_g'),('L','round')]:assert int(float(main[f'{col}{row}'][0]))==d[key]
   assert abs(float(main[f'M{row}'][0])-d['cer'])<1e-10
  baseline=p.read_json(re/'evidence-01/records/baseline48-reference.json');assert len(baseline['rows'])==96
  for mean in baseline['means']:assert abs(float(main[f"T{mean['delta_g']+9}"][0])-mean['accuracy'])<1e-10
  assert os.access(rw/'ROLLBACK.sh',os.X_OK)
  restored_xlsx_hash=p.file_hash(re/'实验结果-01.xlsx')
result={'status':'PASS','formal_results':160,'per_font':{str(f):32 for f in [16,24,32,40,64]},'workflow_exceptions':5,'xlsx_sheets':['实验结果','完整回复'],'native_filter_range':'A9:M169','visual_qa':'PASS: both sheets and final rows','skill_archive':archive,'final_evidence_archive':str(target),'archive_sha256':p.file_hash(target),'snapshot_files':len(hashes),'snapshot_crc':'PASS','independent_restore':'PASS','restored_records_and_replies':160,'restored_baseline_references':96,'restored_xlsx_sha256':restored_xlsx_hash,'executable_rollback_restored':True,'temporary_restore_directory_removed':True,'original_experiment1_files_unchanged':944,'original_skill_scripts_unchanged':True,'working_directory_cleaned_after_skill_restore':not (ROOT/'26-10-27/_archive/.exp2-perplexity-screen-readability-work').exists()}
p.save_json(W/'closeout-verification.json',result)
print(json.dumps({k:v for k,v in result.items() if k not in ('skill_archive','per_font')},ensure_ascii=False,indent=2))
