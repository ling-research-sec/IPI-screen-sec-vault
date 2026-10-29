"""Offline evidence verification: Python3 + Pillow; no phone or model requests."""
from pathlib import Path
import sys,json,zipfile,tempfile,hashlib,collections
ROOT=Path(__file__).resolve().parents[2]
def main():
 rec=ROOT/'evidence-01/records';params=json.loads((rec/'实验参数-01.json').read_text());selections=json.loads((rec/'采样来源-01.json').read_text());assert len(selections)==192 and len({x['case_id'] for x in selections})==192
 with zipfile.ZipFile(rec/'UI证据-01.zip') as z,tempfile.TemporaryDirectory(prefix='gemini02-verify-') as tmp:
  assert z.testzip() is None
  for member,h in json.loads(z.read('manifest.json')).items():assert hashlib.sha256(z.read(member)).hexdigest()==h,member
  runtime=Path(tmp)/'runtime';runtime.mkdir()
  for name in ['pipeline.py','gemini_adapter.py','gemini_auto_adapter.py']:(runtime/name).write_bytes(z.read('runtime/'+name))
  sys.path.insert(0,str(runtime));import pipeline as p
  orig_read=p.read_xlsx;p.read_xlsx=lambda path:orig_read(Path(path).with_name('Gemini实验结果02.xlsx') if Path(path).name=='实验结果-01.xlsx' else path)
  raw=params['config'];raw.update(experiment_dir=str(ROOT),reference_file=str(rec/'参考字符.txt'),prompt_file=str(rec/'Prompt.txt'),image_pattern=str(ROOT/'evidence-01/source-images/{value}.png'));cfg=Path(tmp)/'config.json';p.save_json(cfg,raw);c=p.Config(cfg);c.work=Path(tmp)/'absent'
  assert len(c.values)==192 and {(c.conditions[v]['font_px'],c.conditions[v]['delta_g']) for v in c.values}=={(f,g) for f in [16,24,32,40,48,64] for g in range(1,33)}
  assert len(list(rec.glob('exp2-result-*.json')))==192
  counts=collections.Counter();total=0
  for item in selections:
   v=item['case_id'];assert p.validate_existing(c,1,v);r=p.read_json(c.record(1,v));assert all(r[k]==val for k,val in p.score(c.reference,r['response'],c.whitespace).items())
   original=z.read(item['original_record_member']);assert p.digest(original)==item['original_record_sha256'];old=json.loads(original)
   for key in ['response','response_ui_full','started_utc','completed_utc','prompt_sent','correct','substitutions','deletions','insertions','accuracy','cer','source_sha256','reference_sha256']:assert r[key]==old[key],(v,key)
   actions=[json.loads(x) for x in z.read('round01/g'+v+'/auto-node-actions.jsonl').decode().splitlines()];assert sum(x.get('label')=='Send' for x in actions)==1
   counts[item['kind']]+=1;total+=r['correct']
  assert counts=={'首次有效':181,'补测补齐':11} and total==17823
  result=p.verify_reports(c);sheets,n=p.read_xlsx(ROOT/'Gemini实验结果02.xlsx');marked={sheets[0][f'A{i}'][0] for i in range(10,n+10) if '补测补齐' in sheets[0][f'I{i}'][0]};assert marked=={x['case_id'] for x in selections if x['kind']=='补测补齐'}
  assert p.read_json(c.record(1,'f24-g31'))['correct']==0 and p.read_json(c.record(1,'f40-g28'))['insertions']==171
  print(json.dumps(dict(status='PASS',records=192,first_valid=181,supplemental=11,correct=total,targets=19200,source_rgb_and_prompt_verified=True,full_replies_and_scores_unchanged=True,workbook=result,zero_and_true_errors_retained=True),ensure_ascii=False))
if __name__=='__main__':main()
