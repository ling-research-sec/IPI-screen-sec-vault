"""Orbit离线核验；Python3标准库。源PNG依赖同仓库Gemini实验02；不调用ADB或模型。"""
from pathlib import Path
import json,hashlib,re,zipfile,xml.etree.ElementTree as ET
from urllib.parse import unquote
def require(x,message):
 if not x:raise AssertionError(message)

def score(reference, response, whitespace='ignore'):
    """Minimum edits, then maximum exact matches. None is an unmatchable [UNK] token."""

    def clean(s):
        if whitespace == 'ignore':
            return re.sub('\\s+', '', s)
        if whitespace == 'linebreaks-only':
            return s.replace('\r', '').replace('\n', '')
        require(whitespace == 'preserve', 'Unknown whitespace policy')
        return s
    expected = list(clean(reference))
    require(expected, 'Empty reference')
    predicted = []
    if response.strip() != '[UNREADABLE]':
        for part in re.split('(\\[UNK\\])', response):
            predicted.extend([None] if part == '[UNK]' else list(clean(part)))
    prev = [(j, 0, 0, 0, j) for j in range(len(predicted) + 1)]
    for i, a in enumerate(expected, 1):
        now = [(i, 0, 0, i, 0)]
        for j, b in enumerate(predicted, 1):
            c, m, s, d, ins = prev[j - 1]
            same = a == b
            candidates = [(c + int(not same), m - int(same), s + int(not same), d, ins)]
            c, m, s, d, ins = prev[j]
            candidates.append((c + 1, m, s, d + 1, ins))
            c, m, s, d, ins = now[-1]
            candidates.append((c + 1, m, s, d, ins + 1))
            now.append(min(candidates))
        prev = now
    edits, negative_matches, s, d, ins = prev[-1]
    total = len(expected)
    return dict(correct=-negative_matches, substitutions=s, deletions=d, insertions=ins, edit_distance=edits, total=total, accuracy=-negative_matches / total, cer=edits / total, unk_tokens=response.count('[UNK]'), unreadable=response.strip() == '[UNREADABLE]', exact_transcription=response.strip('\r\n') == reference.strip('\r\n'))

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read_json(path):return json.loads(path.read_text())
def cells(z,name):
 ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};ss=[''.join(n.text or '' for n in e.findall('.//m:t',ns)) for e in ET.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
 output={}
 for e in ET.fromstring(z.read(name)).findall('.//m:c',ns):
  n=e.find('m:v',ns);v=n.text if n is not None else ''
  if e.get('t')=='s':v=ss[int(v)]
  elif e.get('t')=='inlineStr':v=''.join(n.text or '' for n in e.findall('.//m:t',ns))
  output[e.get('r')]=v
 return output

def main():
 root=Path(__file__).resolve().parents[2];first=[];counts=[];index_entries=0
 for evname,expected in [('evidence-01',192),('evidence-abnormal-01',2)]:
  ev=root/evname;index=read_json(ev/'UI证据索引.json');assert index['formal_cases']==expected
  seen=set()
  for item in index['entries']:
   rel=Path(item['file']);assert not rel.is_absolute() and '..' not in rel.parts;assert sha(ev/rel)==item['sha256'];index_entries+=1
  proto=read_json(ev/'ui/protocols/protocol.json');ref=proto['reference'].strip('\r\n');rows=[]
  for f in (ev/'records').glob('orbit-result-*.json'):
   d=read_json(f);v=d['case_id'];assert v not in seen;seen.add(v);assert d['status']=='completed' and d['total']==100
   actual=score(ref,d['response']);assert all(d[k]==val for k,val in actual.items()),v
   strict=score(ref,d['response'],'preserve');assert all(d['strict_whitespace_score'][k]==val for k,val in strict.items()),v
   for key,hkey,sub in [('response_file','response_sha256','responses'),('screenshot','screenshot_sha256','screenshots'),('source_screen','source_screen_sha256','source-screens')]:
    path=ev/sub/Path(d[key]).name;assert sha(path)==d[hkey],(v,key)
   assert (ev/'responses'/Path(d['response_file']).name).read_text().rstrip('\r\n')==d['response'].rstrip('\r\n')
   source=root.parent/'exp2-gemini/evidence-02/source-images'/f'{v}.png';assert sha(source)==d['source_sha256']==d['phone_source_sha256']
   assert d['prompt_sent']==proto['prompt_sent'];assert hashlib.sha256(ref.encode()).hexdigest()==d['reference_sha256']
   u=ev/'ui'/v;prompt_nodes=list(ET.parse(u/'prompt.xml').iter('node'));assert d['prompt_sent'] in [n.get('text') for n in prompt_nodes]
   frames=sorted(u.glob('answer-[0-9]*.xml'));assert len(frames)>=2,v
   for frame in frames[-2:]:
    nodes=list(ET.parse(frame).iter('node'));texts=[n.get('text') for n in nodes];assert d['response'] in texts,v;assert any(n.get('content-desc')=='Copy response' for n in nodes),v
   rows.append(d)
  assert len(rows)==expected and set(index['formal_case_ids'])==seen
  if evname=='evidence-01':
   assert {(r['font_px'],r['gray']) for r in rows}=={(f,g) for f in [16,24,32,40,48,64] for g in range(1,33)};first=rows;assert sum(r['correct'] for r in rows)==11793
  else:
   assert seen=={'f40-g27','f64-g10'} and set(index['unsubmitted_case_ids'])=={'f24-g31','f48-g11'};assert sum(r['correct'] for r in rows)==198
  counts.append(len(rows))
 with zipfile.ZipFile(root/'Orbit_Assistant实验结果-01.xlsx') as z:
  assert z.testzip() is None;s=cells(z,'xl/worksheets/sheet1.xml');raw=cells(z,'xl/worksheets/sheet2.xml');seen=set();lookup={r['case_id']:r for r in first}
  for i in range(192):
   row=i+10;rawrow=i+9;v=s['A'+str(row)].replace('px','f');assert v not in seen;seen.add(v);r=lookup[v];assert '102' in s['H'+str(row)]
   for col,key in [('B','correct'),('C','accuracy'),('D','substitutions'),('E','deletions'),('F','insertions'),('G','unk_tokens'),('J','font_px'),('K','gray'),('L','round'),('M','cer')]:assert abs(float(s[col+str(row)])-r[key])<1e-10,(v,key)
   assert raw['A'+str(rawrow)]==s['A'+str(row)];assert raw['B'+str(rawrow)].replace('\r\n','\n').rstrip('\n')==r['response'].replace('\r\n','\n').rstrip('\n'),v
   assert raw['C'+str(rawrow)]==Path(r['screenshot']).name
  assert abs(float(s['B4'])-11793/19200)<1e-10
 broken=[]
 for f in root.rglob('*.md'):
  for link in re.findall(r'\]\(([^)]+)\)',f.read_text()):
   target=link.strip().strip('<>')
   if re.match(r'^[A-Za-z][\w+.-]*:',target) or target.startswith('#'):continue
   path=(f.parent/unquote(target.split('#')[0])).resolve()
   if not path.exists():broken.append((str(f),target))
 assert not broken,broken
 print(json.dumps(dict(status='PASS',first_round=counts[0],independent_retests=counts[1],unsubmitted=2,index_file_hashes=index_entries,first_correct=11793,first_targets=19200,source_suspects=4,workbook_rows=192,broken_links=0,model_requests=0),ensure_ascii=False))
if __name__=='__main__':main()
