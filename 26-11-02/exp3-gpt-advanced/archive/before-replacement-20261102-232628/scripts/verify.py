from pathlib import Path
import json,hashlib,sys,re,statistics,zipfile
from xml.etree import ElementTree as ET
W=Path(__file__).resolve().parent;ROOT=W.parents[2];O=ROOT/'26-11-02/exp3-gpt-advanced'
sys.path.insert(0,str(ROOT/'26-11-01/exp1-gpt-advanced/archive/_work'))
from assess import readbook
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def align(a,b):
 a=re.sub(r'\s+','',a);b=re.sub(r'\s+','',b);prev=[(j,0) for j in range(len(b)+1)]
 for i,x in enumerate(a,1):
  now=[(i,0)]
  for j,y in enumerate(b,1):now.append(min((prev[j-1][0]+(x!=y),prev[j-1][1]-(x==y)),(prev[j][0]+1,prev[j][1]),(now[j-1][0]+1,now[j-1][1])))
  prev=now
 return prev[-1][0],-prev[-1][1]
d=json.loads((O/'evidence/scored_records.json').read_text());a=d['records'];book=O/'GPT_Advanced_实验结果03.xlsx';s,r=readbook(book)
overall=d['overall'];available=overall['available'];scored=overall['scored'];correct=overall['correct'];denominator=overall['denominator']
assert len(a)==192 and len({x['condition_id'] for x in a})==192
assert len(list((O/'evidence/screenshots').rglob('*.png')))==available==192
assert scored==190 and overall['anomalies']==2 and overall['missing']==0
assert {x['condition_id'] for x in a if x['anomaly']}=={'px32-g16','px48-g11'}
assert sha(d['template'])==d['template_sha256']
assert sha(d['workbook_input'])==d['workbook_input_sha256']
prior=json.loads((Path(d['workbook_input']).parent/'evidence/scored_records.json').read_text())
current={x['condition_id']:x for x in a}
for old in prior['records']:
 if old['file']:
  now=current[old['condition_id']]
  for key in ['sha256','raw_response','transcription','metrics','result_class','user_prompt']:
   assert now[key]==old[key],f'Previous reviewed data changed: {old["condition_id"]} {key}'
for i,x in enumerate(a):
 n=i+10;val=lambda c:s.get(f'{c}{n}',{}).get('value')
 assert val('A')==x['condition_id'] and int(val('J'))==x['font_px'] and int(val('K'))==x['gray'] and int(val('L'))==3
 assert val('H')=='手动255' and val('I')==x['result_note']
 assert r[f'A{n-1}']['value']==x['condition_id']
 if x['file']:
  match=re.match(r'g(\d+)_(\d+)_f(\d+)-g(\d+)_',Path(x['file']).name)
  assert match and tuple(map(int,match.groups()))==(x['gray'],i+1,x['font_px'],x['gray'])
  assert sha(x['file'])==x['sha256']==sha(x['original_file']) and x['visual_checked']
  assert r[f'C{n-1}']['value']==Path(x['file']).name
  assert (r.get(f'B{n-1}',{}).get('value') or '')==(x['raw_response'] or '')
 else:
  assert r.get(f'C{n-1}',{}).get('value') in (None,'')
  assert r.get(f'B{n-1}',{}).get('value') in (None,'')
 m=x['metrics'];matrix=s[f'{"PQRSTU"[i//32]}{10+i%32}']['value']
 if m:
  for col,key in [('B','correct'),('D','substitutions'),('E','deletions'),('F','insertions'),('G','unk_tokens')]:assert int(val(col))==m[key]
  assert abs(float(val('C'))-m['accuracy'])<1e-12 and abs(float(val('M'))-m['cer'])<1e-12
  assert abs(float(matrix)-m['accuracy'])<1e-12
  edits,matches=align(d['reference'],x['transcription']);assert (edits,matches)==(m['edit_distance'],m['correct'])
 else:
  for col in 'BCDEFGM':assert val(col) in (None,'')
  assert matrix in (None,'')
assert len({x['sha256'] for x in a})==192
assert int(s['F4']['value'])==available and int(s['B203']['value'])==correct
assert abs(float(s['C203']['value'])-correct/denominator)<1e-12
assert abs(float(s['D4']['value'])-statistics.stdev(x['metrics']['accuracy'] for x in a if x['metrics'])*100)<1e-9
N={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(book) as z,zipfile.ZipFile(d['template']) as t:
 assert [x.get('name') for x in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',N)]==['实验结果','完整回复']
 for name in ['xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml']:
  e=ET.fromstring(z.read(name));old=ET.fromstring(t.read(name));assert not e.findall('.//m:c[@t="e"]',N)
  assert [x.attrib for x in e.findall('m:cols/m:col',N)]==[x.attrib for x in old.findall('m:cols/m:col',N)]
  assert [x.attrib for x in e.findall('m:mergeCells/m:mergeCell',N)]==[x.attrib for x in old.findall('m:mergeCells/m:mergeCell',N)]
report=dict(registered_conditions=192,source_capture_round=5,experiment_round=3,selected_images=available,visual_checked=available,source_hash_matches=available,previous_171_unchanged=True,scored=scored,anomalies=overall['anomalies'],missing=overall['missing'],blank_not_zero=192-scored,correct=correct,denominator=denominator,accuracy=correct/denominator,independent_alignment_matches=scored,raw_reply_file_links=available,matrix_checks=192,formula_errors=0,template_unchanged=True,sheets_and_layout_preserved=True,cutoff_condition='64px-g32',workbook_sha256=sha(book))
(O/'evidence/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('REOPEN VERIFY PASS '+json.dumps(report,ensure_ascii=False))
