"""离线核验192条：Python3 + Pillow，无手机/网络请求。"""
from pathlib import Path
import sys,json,zipfile,tempfile,hashlib,collections
ROOT=Path(__file__).resolve().parents[2]
def main():
 rec=ROOT/'evidence-03/records';params=json.loads((rec/'实验参数-03.json').read_text());sources=json.loads((rec/'采样来源-03.json').read_text());assert len(sources)==192 and len({x['case_id'] for x in sources})==192
 with zipfile.ZipFile(rec/'UI证据-03.zip') as z,tempfile.TemporaryDirectory(prefix='gemini03-verify-') as td:
  assert z.testzip() is None
  for member,h in json.loads(z.read('manifest.json')).items():assert hashlib.sha256(z.read(member)).hexdigest()==h,member
  tmp=Path(td);runtime=tmp/'runtime';runtime.mkdir()
  for name in ['pipeline.py','gemini_adapter.py','gemini_auto_adapter.py']:(runtime/name).write_bytes(z.read('runtime/'+name))
  sys.path.insert(0,str(runtime));import pipeline as p
  read=p.read_xlsx;p.read_xlsx=lambda f:read(Path(f).with_name('Gemini实验结果-03.xlsx') if Path(f).name=='实验结果-03.xlsx' else f)
  raw=params['config_template'];raw.update(experiment_dir=str(ROOT),reference_file=str(rec/'参考字符.txt'),prompt_file=str(rec/'Prompt.txt'),image_pattern=str(ROOT/'evidence-03/source-images/{value}.png'));p.save_json(tmp/'config.json',raw);c=p.Config(tmp/'config.json');c.work=tmp/'no-live-work'
  assert c.rounds==[3] and len(c.values)==192 and len(set(c.values))==192
  assert {(c.conditions[v]['font_px'],c.conditions[v]['delta_g']) for v in c.values}=={(f,g) for f in [16,24,32,40,48,64] for g in range(1,33)}
  assert len(list(rec.glob('exp3-result-*.json')))==192
  total=0;counts=collections.Counter()
  for s in sources:
   v=s['case_id'];assert p.validate_existing(c,3,v);r=p.read_json(c.record(3,v));assert r['round']==3;assert all(r[k]==x for k,x in p.score(c.reference,r['response'],c.whitespace).items());assert r['background_gray']==0 and r['text_gray']==r['delta_g']
   original=z.read(s['original_record_member']);assert p.digest(original)==s['original_record_sha256'];old=json.loads(original)
   for k in ['response','response_ui_full','prompt_sent','started_utc','completed_utc','correct','substitutions','deletions','insertions','accuracy','cer','source_sha256','reference_sha256']:assert r[k]==old[k],(v,k)
   actions=[json.loads(x) for x in z.read('round03/g'+v+'/auto-node-actions.jsonl').decode().splitlines()];assert sum(a.get('label')=='Send' for a in actions)==1
   total+=r['correct'];counts[s['kind']]+=1
  assert counts=={'original_valid':180,'authorized_retest_fill':12};assert total==17900
  report=p.verify_reports(c);assert report['rows']==192
  print(json.dumps(dict(status='PASS',round=3,records=192,first_valid=180,authorized_retest_fill=12,correct=total,targets=19200,mean_accuracy=total/19200,raw_text_times_and_scores_unchanged=True,source_rgb_prompt_full_reply_verified=True,workbook=report),ensure_ascii=False))
if __name__=='__main__':main()
