#!/usr/bin/env python3
"""只读离线核验。无ADB、网络或模型请求；需要Python3和Pillow。"""
from pathlib import Path
import sys,json,zipfile,tempfile,hashlib,collections,importlib
ROOT=Path(__file__).resolve().parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 params=json.loads((ROOT/'evidence-01/records/实验参数-01.json').read_text());origin=json.loads((ROOT/'evidence-01/records/采样来源-01.json').read_text());ui=ROOT/'evidence-01/records/UI证据-01.zip'
 assert sha(ui.read_bytes())==params['ui_archive_sha256']==origin['ui_archive_sha256']
 with zipfile.ZipFile(ui) as z,tempfile.TemporaryDirectory(prefix='gemini-exp01-verify-') as tmp:
  assert z.testzip() is None;manifest=json.loads(z.read('manifest.json'))
  for member,h in manifest.items():assert sha(z.read(member))==h,member
  runtime=Path(tmp)/'runtime';runtime.mkdir()
  for name in ['pipeline.py','gemini_adapter.py','gemini_auto_adapter.py']:(runtime/name).write_bytes(z.read('runtime/'+name))
  sys.path.insert(0,str(runtime));p=importlib.import_module('pipeline');auto=importlib.import_module('gemini_auto_adapter')
  raw=dict(params['config_template']);raw.update(experiment_dir=str(ROOT),reference_file=str(ROOT/'evidence-01/records/参考字符.txt'),prompt_file=str(ROOT/'evidence-01/records/Prompt.txt'),image_pattern=str(ROOT/'evidence-01/source-images/{value}.png'));cfg=Path(tmp)/'config.json';p.save_json(cfg,raw);c=p.Config(cfg)
  assert len(c.values)==192 and c.rounds==[1];assert len(set(c.values))==192;assert set((c.conditions[v]['font_px'],c.conditions[v]['delta_g']) for v in c.values)=={(f,g) for f in [16,24,32,40,48,64] for g in range(1,33)}
  assert p.file_hash(c.reference_path)==params['reference_sha256'] and p.file_hash(c.prompt_path)==params['prompt_sha256']
  counts=collections.Counter();types=collections.Counter();correct=0
  source={x['case_id']:x for x in origin['selections']};assert len(source)==192
  for v in c.values:
   assert p.validate_existing(c,1,v);r=p.read_json(c.record(1,v));score=p.score(c.reference,r['response'],c.whitespace);assert all(r[k]==x for k,x in score.items());assert r['background_gray']==0 and r['text_gray']==r['delta_g'];assert r['manual_attachment_actions']==0
   old_bytes=z.read(source[v]['original_record_member']);assert sha(old_bytes)==source[v]['original_record_sha256'];old=json.loads(old_bytes)
   for k in ['response','response_ui_full','prompt_sent','started_utc','completed_utc','source_sha256','reference_sha256','correct','substitutions','deletions','insertions','accuracy','cer','unk_tokens','unreadable','exact_transcription']:assert r[k]==old[k],(v,k)
   for member in r['reply_stability_xml_members']:
    body,done,meta=auto.response(list(p.ET.fromstring(z.read(member)).iter('node')));assert body==r['response']
   assert done
   actions=[json.loads(x) for x in z.read('round01/g'+v+'/auto-node-actions.jsonl').decode().splitlines()];assert len(actions)==2 and actions[0]['node_class']=='android.widget.EditText' and actions[1]['label']=='Send'
   counts[r['font_px']]+=1;types[source[v]['kind']]+=1;correct+=r['correct']
  assert all(counts[f]==32 for f in [16,24,32,40,48,64]);assert types=={'original_valid':186,'authorized_retest_fill':6};assert correct==17820
  assert p.read_json(c.record(1,'f40-g31'))['correct']==0;assert p.read_json(c.record(1,'f64-g04'))['insertions']==203
  report=p.verify_reports(c)
  sheets,n=p.read_xlsx(ROOT/'实验结果-01.xlsx');marked={sheets[0][f'A{i}'][0] for i in range(10,n+10) if '补测补齐' in sheets[0][f'I{i}'][0]};assert marked=={v for v,x in source.items() if x['kind']=='authorized_retest_fill'}
  print(json.dumps(dict(status='PASS',records=192,rounds=1,font_counts=dict(counts),original_valid=186,retest_fill=6,correct=correct,targets=19200,raw_scores_times_and_text_unchanged=True,full_ui_prompt_and_source_rgb_checked=True,true_ocr_errors_and_zero_retained=True,workbook=report,new_model_requests=0),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
