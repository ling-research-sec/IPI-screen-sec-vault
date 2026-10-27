#!/usr/bin/env python3
"""Read-only evidence audit plus original Skill verify/archive with display-only ID aliases."""
from pathlib import Path
import argparse,json,sys,zipfile,xml.etree.ElementTree as ET
from PIL import Image,ImageChops
W=Path(__file__).resolve().parent
sys.path.insert(0,str(W/'runner'));import pipeline as p
parser=argparse.ArgumentParser();parser.add_argument('action',choices=['verify','archive']);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
c=p.Config(W/'config-full.json')
original=p.read_xlsx
def read_display_aliases(file):
 sheets,count=original(file)
 assert count==160
 for sheet,start in [(sheets[0],10),(sheets[1],9)]:
  for index in range(start,start+count):
   value,formula=sheet[f'A{index}'];assert value.startswith('px') and formula is None
   sheet[f'A{index}']=('f'+value[2:],formula)
 return sheets,count
p.read_xlsx=read_display_aliases
verified=p.verify_reports(c)
if args.action=='archive':
 assert args.execute,'--execute required'
 assert c.work.is_dir() and len(list(c.work.glob('round*/g*/state.json')))==320,'Expected completed owned work; do not archive twice'
 print(json.dumps(p.archive(c),ensure_ascii=False,indent=2));sys.exit(0)
assert not args.execute,'Read-only verification does not take --execute'
assert c.reference==(c.root.parent.parent/'26-10-26/Random-characters.txt').read_text().strip('\r\n')
summary={'status':'PASS','skill_verify':verified,'rounds':[],'checks':['original/source-copy/phone hashes','raw reply, XML and PNG hashes','exact RGB source ROI','two consecutive exact frames','brightness255 manual before/after','deterministic score','reference/Prompt','two workbook tabs, 160 unique px aliases, conditions and formula totals','historical48px rows and protected01/exp1 hashes']}
archives={}
def ui_bytes(record,member):
 active=c.work/member
 if active.is_file():return active.read_bytes()
 archive=(c.root/record['ui_archive']).resolve()
 assert archive.parent==c.archive_root.resolve()
 if archive not in archives:
  z=zipfile.ZipFile(archive);archives[archive]=(z,json.loads(z.read('manifest.json'))['files'])
 z,hashes=archives[archive];data=z.read(member);assert p.digest(data)==hashes[member]
 return data
for n in [2,3]:
 records=[];counts={str(f):0 for f in [16,24,32,40,64]};source_exact=0
 for v in c.values:
  assert p.validate_existing(c,n,v);d=p.read_json(c.record(n,v));assert d['round']==n and d['repeat']==n
  assert d['phone_source_sha256']==d['source_sha256']==p.file_hash(c.evidence(n)/'source-images'/d['image'])
  assert d['screen_brightness_mode']==0 and d['screen_brightness']==255 and d['brightness_after']=={'mode':0,'value':255}
  assert all(d[k]==val for k,val in p.score(c.reference,d['response'],c.whitespace).items())
  for key,rel in [('response_sha256',d['response_file']),('screenshot_sha256',d['screenshot']),('source_screen_sha256',d['source_screen'])]:assert p.file_hash(c.evidence(n)/rel)==d[key]
  fidelity=d['source_fidelity'];assert fidelity['status']=='PASS' and fidelity['consecutive_exact']>=2
  assert all(x['exact'] for x in fidelity['observations'][-2:])
  expected=Image.open(c.image(v)).convert('RGB').crop(tuple(fidelity['roi']));actual=Image.open(c.evidence(n)/d['source_screen']).convert('RGB').crop(tuple(fidelity['roi']))
  assert ImageChops.difference(expected,actual).getbbox() is None
  assert p.digest(expected.tobytes())==fidelity['expected_roi_sha256']==fidelity['observed_roi_sha256']
  assert fidelity['observations'][-1]['source_screen_sha256']==d['source_screen_sha256'];source_exact+=1
  state_member=f'round{n:02d}/g{v}/state.json';assert json.loads(ui_bytes(d,state_member))['phase']=='completed'
  answer=list(ET.fromstring(ui_bytes(d,d['answer_xml_archive_member'])).iter('node'))
  assert '\n'.join(x.get('text') for x in answer if x.get('class')=='android.widget.TextView' and x.get('text'))==d['response']
  assert any(x.get('content-desc')==c.ui['copy_desc'] for x in answer)
  assert not any(any(t in x.get('content-desc','') for t in c.ui['thinking_contains']) for x in answer)
  prompt=list(ET.fromstring(ui_bytes(d,d['prompt_xml_archive_member'])).iter('node'))
  edits=[x for x in prompt if x.get('class')=='android.widget.EditText'];assert len(edits)==1 and edits[0].get('text')==c.prompt
  protocol=json.loads(ui_bytes(d,d['protocol_archive_member']));assert protocol['reference']==c.reference and protocol['prompt_sent']==c.prompt
  counts[str(d['font_px'])]+=1;records.append(d)
 assert len(records)==160 and all(x==32 for x in counts.values())
 correct=sum(r['correct'] for r in records)
 summary['rounds'].append(dict(round=n,valid=160,per_font=counts,source_rgb_exact=source_exact,total_correct=correct,total_characters=16000,mean_accuracy=correct/16000,substitutions=sum(x['substitutions'] for x in records),deletions=sum(x['deletions'] for x in records),insertions=sum(x['insertions'] for x in records),per_font_mean={str(f):sum(x['correct'] for x in records if x['font_px']==f)/3200 for f in [16,24,32,40,64]},started_utc=min(x['started_utc'] for x in records),completed_utc=max(x['completed_utc'] for x in records)))
for rel,h in p.read_json(W/'protected-input-hashes.json').items():assert p.file_hash(c.root.parent.parent/rel)==h
summary['workflow_exclusions']={str(n):[str(x.relative_to(c.root)) for x in sorted((c.evidence(n)/'excluded').glob('attempt-*'))] for n in [2,3]}
summary['ui_storage']='archive members SHA256 verified' if archives else 'owned live work'
for z,hashes in archives.values():z.close()
p.save_json(W/'final-evidence-verification.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
