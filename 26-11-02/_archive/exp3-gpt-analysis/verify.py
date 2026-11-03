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
assert scored==192 and overall['anomalies']==0 and overall['missing']==0
assert not any(x['anomaly'] for x in a)
assert json.loads((O/'evidence/anomalies.json').read_text())==[]
assert sha(d['template'])==d['template_sha256']
assert sha(d['workbook_input'])==d['workbook_input_sha256']
prior=json.loads((Path(d['workbook_input']).parent/'evidence/scored_records.json').read_text())
current={x['condition_id']:x for x in a}
replacements={x['condition_id']:x for x in json.loads(Path(d['replacement_manifest']).read_text())}
assert set(replacements)=={'px32-g16','px48-g11'}
assert current['px32-g16']['metrics']['correct']==0 and current['px48-g11']['metrics']['correct']==67
for old in prior['records']:
 if old['file']:
  now=current[old['condition_id']]
  if old['condition_id'] in replacements:
   change=replacements[old['condition_id']]
   assert old==change['old_record'] and now==change['replacement_record']
   assert not Path(old['file']).exists() and sha(change['archived_file'])==old['sha256']==sha(old['original_file'])
   assert now['source_capture_round']==6 and now['experiment_round']==3
   continue
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
inventory=json.loads((O/'evidence/inventory.json').read_text())
assert len(inventory)==192 and {x['file'] for x in inventory}=={str(x) for x in (O/'evidence/screenshots').rglob('*.png')}
assert not (O/'evidence/异常补测清单.md').exists()
for x in inventory:
 assert x['sha256']==current[x['condition_id']]['sha256']
 assert x['source_capture_round']==(6 if x['condition_id'] in replacements else 5)
assert int(s['F4']['value'])==available and int(s['B203']['value'])==correct
assert abs(float(s['C203']['value'])-correct/denominator)<1e-12
assert abs(float(s['D4']['value'])-statistics.stdev(x['metrics']['accuracy'] for x in a if x['metrics'])*100)<1e-9
baseline_sheets=readbook(d['workbook_input'])
allowed_main={'A5','A6','O3','O4','I203','B4','D4','B203','C203','D203','E203','F203','M203','R25','T20'}|{f'{c}{n}' for n in (89,148) for c in 'BCDEFGIM'}
allowed_replies={'A3','A7','B88','C88','B147','C147'}
for old,new,allowed in zip(baseline_sheets,(s,r),(allowed_main,allowed_replies)):
 for addr in set(old)|set(new):
  before=old.get(addr,{});after=new.get(addr,{})
  assert before.get('formula')==after.get('formula'),f'Formula changed: {addr}'
  if before.get('value')!=after.get('value'):assert addr in allowed,f'Unrelated cell changed: {addr}'
N={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(book) as z,zipfile.ZipFile(d['template']) as t:
 assert [x.get('name') for x in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',N)]==['实验结果','完整回复']
 for name in ['xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml']:
  e=ET.fromstring(z.read(name));old=ET.fromstring(t.read(name));assert not e.findall('.//m:c[@t="e"]',N)
  assert [x.attrib for x in e.findall('m:cols/m:col',N)]==[x.attrib for x in old.findall('m:cols/m:col',N)]
  assert [x.attrib for x in e.findall('m:mergeCells/m:mergeCell',N)]==[x.attrib for x in old.findall('m:mergeCells/m:mergeCell',N)]
with zipfile.ZipFile(book) as z,zipfile.ZipFile(d['workbook_input']) as t:
 for name in ['xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml']:
  new=ET.fromstring(z.read(name));old=ET.fromstring(t.read(name))
  for tag in ['cols','mergeCells','sheetViews','autoFilter','conditionalFormatting','dataValidations','drawing','sheetProtection','pageMargins','pageSetup','printOptions']:
   assert [ET.tostring(x) for x in new.findall('m:'+tag,N)]==[ET.tostring(x) for x in old.findall('m:'+tag,N)],f'Native feature changed: {name} {tag}'
  def tables(package,tree):
   relfile=name.replace('worksheets/','worksheets/_rels/')+'.rels'
   rels=ET.fromstring(package.read(relfile)) if relfile in package.namelist() else []
   targets={x.get('Id'):x.get('Target').lstrip('/') for x in rels}
   ans=[]
   for part in tree.findall('m:tableParts/m:tablePart',N):
    target=targets[part.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
    if not target.startswith('xl/'):target='xl/'+target.removeprefix('../')
    ans.append((target,ET.tostring(ET.fromstring(package.read(target)))))
   return ans
  assert tables(z,new)==tables(t,old),f'Table structure or binding changed: {name}'
for sheet in (s,r):
 assert not any(isinstance(c['value'],str) and any(word in c['value'] for word in ['待补测','待重测','缺图，未评分']) for c in sheet.values())
report=dict(registered_conditions=192,source_capture_rounds=[5,6],experiment_round=3,selected_images=available,visual_checked=available,source_hash_matches=available,unchanged_conditions=190,replaced_conditions=list(replacements),archived_anomalies=2,scored=scored,anomalies=overall['anomalies'],missing=overall['missing'],blank_not_zero=192-scored,correct=correct,denominator=denominator,accuracy=correct/denominator,independent_alignment_matches=scored,raw_reply_file_links=available,matrix_checks=192,formula_errors=0,unrelated_cells_unchanged=True,all_formulas_preserved=True,native_features_preserved=True,template_unchanged=True,sheets_and_layout_preserved=True,workbook_sha256=sha(book))
(O/'evidence/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('REOPEN VERIFY PASS '+json.dumps(report,ensure_ascii=False))
