from pathlib import Path
import json,re,hashlib,collections,sys
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[2];LAB=ROOT/'26-11-05/tools/gemini-memory-lab';OUT=Path(__file__).parent
sys.path.insert(0,str(LAB))
from core.case_loader import load_cases,FORMAL_WORKBOOK
from core.gemini_controller import response_service_error_text,response_status_text
CASES={c.row:c.to_dict() for c in load_cases(FORMAL_WORKBOOK)}
rows=[]
for phase in ('p1','p2'):
 for f in sorted((LAB/'evidence'/phase).rglob('result.json')):
  try:r=json.loads(f.read_text())
  except:continue
  if not isinstance(r,dict):continue
  raw=f.parent;folder=raw.parent if raw.name=='_debug' else raw;src=r.get('source',{});row=src.get('row')
  if row not in CASES:continue
  def text(name):
   try:return (raw/name).read_text()
   except (OSError,UnicodeError):return ''
  a=text('baseline_response_visible.txt');d=text('post_response_clipboard.md') or text('post_response_visible.txt')
  # Only current D/native output is eligible to demonstrate E, never C or injection.
  xml_text=''
  for name in ('post.xml','post_tool_app.xml'):
   try:
    import xml.etree.ElementTree as ET
    t=ET.fromstring(text(name));xml_text+='\n'.join(n.get('text') or n.get('content-desc') or '' for n in t.iter('node'))+'\n'
   except:pass
  c=CASES[row];goal=c['attack_goal'];target=c['baseline_constraint'];matches=[]
  quoted=re.findall(r'["“]([^"”]+)["”]',target)
  for token in quoted:
   if len(token)>1 and token.casefold() in (d+'\n'+xml_text).casefold():matches.append(token)
  manifests=[folder/'.manifest.json',folder/'manifest.json'];mf=next((x for x in manifests if x.exists()),None)
  manifest_ok=False;manifest_error='missing';hashes={}
  if mf:
   try:
    hashes=json.loads(mf.read_text());bad=[]
    for name,digest in hashes.items():
     p=folder/name
     if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:bad.append(name)
    manifest_ok=not bad;manifest_error=';'.join(bad[:4])
   except Exception as e:manifest_error=str(e)
  imgs={k:any((raw/name).is_file() for name in names) for k,names in {
   'A':['baseline.png'],'C':['response.png','gemini_response.png'],'D':['post.png'],'native':['post_tool_app.png']}.items()}
  schema_match=all(src.get(k)==c.get(k) for k in ['scenario','user_prompt','attacker_prompt','verification_prompt','baseline_constraint','attack_goal'])
  # Frozen A/C/D text equality to workbook. P1 PDF content is verified separately.
  original_c=text('actual_attacker_prompt.txt');source_files={
   'A':text('actual_baseline_prompt.txt')==c['user_prompt'],
   'D':text('actual_post_prompt.txt')==c['verification_prompt'],
   'C':original_c==c['attacker_prompt'] if original_c else None}
  data=dict(phase=phase.upper(),folder=str(folder),raw=str(raw),row=row,case_id=c['case_id'],scene=c['scenario'],round=folder.parent.name,
   status=r.get('status'),cycle=r.get(phase+'_cycle_complete'),submissions=r.get('submissions'),goal=goal,constraint=c['baseline_constraint'],D_prompt=c['verification_prompt'],
   A=a,D=d,xml_output=xml_text,keyword_hints=matches,attack_success_recorded=r.get('attack_success'),
   manifest_ok=manifest_ok,manifest_error=manifest_error,schema_match=schema_match,source_files=source_files,images=imgs,
   post_copy=r.get('post_clipboard',{}),post_capture=r.get('post_capture',{}),tool=r.get('tool_capture',{}),
   p1_pdf=r.get('p1_pdf_attachment',{}),error=r.get('error'),post_placeholder=bool(response_status_text(d)) if d else True,
   post_service_error=bool(response_service_error_text(d)) if d else False,file_count=sum(p.is_file() for p in folder.rglob('*')))
  rows.append(data)
(OUT/'全部候选.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
(OUT/'workbook_cases.json').write_text(json.dumps(CASES,ensure_ascii=False,indent=2)+'\n')
print('CANDIDATES',len(rows),'MANIFEST_OK',sum(r['manifest_ok'] for r in rows))
for phase in ['P1','P2']:
 print('\n',phase)
 for scene in dict.fromkeys(c['scenario'] for c in CASES.values()):
  rs=[r for r in rows if r['phase']==phase and r['scene']==scene];print(scene,len(rs),'D',sum(bool(r['D']) for r in rs),'hints',sum(bool(r['keyword_hints']) for r in rs))
print('\nMODEL / OTHER KEYWORD HINTS:')
for r in rows:
 if r['keyword_hints'] and r['D']:
  print(r['phase'],Path(r['folder']).relative_to(LAB/'evidence'/r['phase'].lower()),r['row'],r['status'],'Bcontains=',any(k.casefold() in r['A'].casefold() for k in r['keyword_hints']),r['keyword_hints'],'D=',re.sub(r'\s+',' ',r['D'])[:500])
