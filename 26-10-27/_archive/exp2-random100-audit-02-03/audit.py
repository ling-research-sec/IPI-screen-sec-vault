from pathlib import Path
import sys,json,re,random,zipfile,hashlib,math,xml.etree.ElementTree as ET
import numpy as np
from PIL import Image,ImageDraw,ImageFont
W=Path(__file__).resolve().parent;ROOT=W.parents[2];E=ROOT/'26-10-27/exp2-perplexity';RUN=W.parent/'exp2-rounds02-03'
sys.path.insert(0,str(RUN/'runner'));import pipeline as p
selection=p.read_json(W/'sample-manifest.json');ids=selection['draw_order'];assert random.Random(int(selection['seed_hex'],16)).sample(selection['population_ids'],100)==ids and len(set(ids))==100
c=p.Config(RUN/'config-full.json');sheets={};rowmaps={};image_maps={}
for n in [2,3]:
 sheets[n],count=p.read_xlsx(E/f'实验结果-{n:02d}.xlsx');assert count==160
 main,raw=sheets[n];rowmaps[n]=({main[f'A{i}'][0].replace('px','f',1):i for i in range(10,170)},{raw[f'A{i}'][0].replace('px','f',1):i for i in range(9,169)})
 image_maps[n]={m['case_id']:m for m in p.read_json(E/f'evidence-{n:02d}/records/image-manifest.json')}
for folder in ['reply-crops','boards','extracted-ui']:(W/folder).mkdir(exist_ok=True)
archives={}
def ui(record,member):
 path=(E/record['ui_archive']).resolve()
 if path not in archives:
  z=zipfile.ZipFile(path);archives[path]=(z,p.read_json(RUN/'final-archive-result.json'),json.loads(z.read('manifest.json')))
 z,meta,manifest=archives[path];data=z.read(member);assert p.digest(data)==manifest['files'][member]
 return data
font=ImageFont.truetype('/System/Library/Fonts/Menlo.ttc',21);small=ImageFont.truetype('/System/Library/Fonts/Menlo.ttc',17);head=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',22)
def fit(board,img,box):
 scale=min((box[2]-box[0])/img.width,(box[3]-box[1])/img.height)
 im=img.resize((max(1,round(img.width*scale)),max(1,round(img.height*scale))),Image.Resampling.NEAREST)
 board.paste(im,(box[0]+((box[2]-box[0])-im.width)//2,box[1]))
results=[];jobs=[];cards=[]
targets=['03/f24-g10','03/f24-g29','03/f40-g17','03/f64-g05'];extra=[x for x in targets if x not in ids]
for index,key in enumerate(ids+extra,1):
 ns,case=key.split('/');n=int(ns);ev=E/f'evidence-{n:02d}';slug=f'r{ns}-{case}';r=p.read_json(ev/f'records/exp2-result-{case}.json');m=image_maps[n][case]
 txt=(ev/r['response_file']).read_text().removesuffix('\n');checks={}
 checks['ids_conditions_round']=r['case_id']==r['parameter_value']==m['case_id']==case and r['font_px']==m['font_px'] and r['delta_g']==m['delta_g'] and r['round']==r['repeat']==n
 checks['original_png_hash']=p.file_hash(ev/'source-images'/r['image'])==r['source_sha256']==r['phone_source_sha256']==m['png_sha256']==p.file_hash(c.image(case))
 for keyname,hkey in [('response_file','response_sha256'),('screenshot','screenshot_sha256'),('source_screen','source_screen_sha256')]:checks[hkey]=p.file_hash(ev/r[keyname])==r[hkey]
 checks['record_raw_reply']=txt==r['response'];checks['reference']=m['expected_text']==c.reference and r['reference_sha256']==p.digest(c.reference.encode())
 answer=ui(r,r['answer_xml_archive_member']);prompt=ui(r,r['prompt_xml_archive_member']);protocol=json.loads(ui(r,r['protocol_archive_member']));state=json.loads(ui(r,f'round{n:02d}/g{case}/state.json'));query=ui(r,f'round{n:02d}/g{case}/source-query.txt').decode()
 am=ET.fromstring(answer);pn=ET.fromstring(prompt);nodes=[x for x in am.iter('node') if x.get('class')=='android.widget.TextView' and x.get('text')]
 checks['xml_reply']='\n'.join(x.get('text') for x in nodes)==txt
 checks['completion']=any(x.get('content-desc')==c.ui['copy_desc'] for x in am.iter('node')) and not any(any(t in x.get('content-desc','') for t in c.ui['thinking_contains']) for x in am.iter('node'))
 edits=[x for x in pn.iter('node') if x.get('class')=='android.widget.EditText'];checks['prompt']=len(edits)==1 and edits[0].get('text')==r['prompt_sent']==protocol['prompt_sent']==c.prompt and protocol['reference']==c.reference
 phone=protocol['config']['phone_image_pattern'].format(value=case,id=case);relative=str(Path(phone).parent).removeprefix('/sdcard/')+'/'
 checks['source_query']=f'_display_name={case}.png' in query and f'relative_path={relative}' in query
 checks['state']=state['phase']=='completed' and state['submitted'] is True and state['value']==case and state['round']==n and state['identity']['source_sha256']==r['source_sha256']
 main,raw=sheets[n];mi,ri=rowmaps[n][0][case],rowmaps[n][1][case]
 checks['xlsx_reply']=raw[f'B{ri}'][0]==txt and raw[f'B{ri}'][1] is None and raw[f'C{ri}'][0]==Path(r['screenshot']).name
 checks['xlsx_conditions']=int(float(main[f'J{mi}'][0]))==r['font_px'] and int(float(main[f'K{mi}'][0]))==r['delta_g'] and int(float(main[f'L{mi}'][0]))==n
 score=p.score(c.reference,txt,c.whitespace);checks['score']=all(r[k]==v for k,v in score.items()) and all(int(float(main[f'{col}{mi}'][0]))==r[field] for col,field in [('B','correct'),('D','substitutions'),('E','deletions'),('F','insertions'),('G','unk_tokens')]) and abs(float(main[f'M{mi}'][0])-r['cer'])<1e-12 and abs(float(main[f'C{mi}'][0])-r['accuracy'])<1e-12
 source=Image.open(ev/'source-images'/r['image']).convert('RGB');screen=Image.open(ev/r['source_screen']).convert('RGB');reply=Image.open(ev/r['screenshot']).convert('RGB');checks['dimensions']=source.size==screen.size==reply.size==(1080,2400)
 roi=(65,650,1030,1120);a=np.asarray(source.crop(roi)).astype(np.int16);b=np.asarray(screen.crop(roi)).astype(np.int16);delta=b-a;pixels=dict(region=roi,exact=bool(np.array_equal(a,b)),changed_pixels=int(np.count_nonzero(np.any(delta!=0,axis=2))),max_abs_difference=int(np.abs(delta).max()))
 checks['source_pixels']=pixels['exact'];fidelity=r['source_fidelity'];checks['source_gate']=fidelity['status']=='PASS' and fidelity['consecutive_exact']>=2 and all(x['exact'] for x in fidelity['observations'][-2:])
 bounds=[list(map(int,re.findall(r'\d+',x.get('bounds')))) for x in nodes];assert bounds
 box=(max(0,min(x[0] for x in bounds)-10),max(0,min(x[1] for x in bounds)-10),min(1080,max(x[2] for x in bounds)+10),min(2400,max(x[3] for x in bounds)+10))
 crop=reply.crop(box);crop_path=W/'reply-crops'/f'{slug}.png';crop.save(crop_path);jobs.append({'case_id':slug,'image':str(crop_path),'bounds':box})
 (W/'extracted-ui'/f'{slug}-answer.xml').write_bytes(answer)
 lines=[part for line in txt.splitlines() for part in [line[j:j+35] for j in range(0,max(1,len(line)),35)]]
 h=max(240,66+len(lines)*24,66+round(crop.height*min(1,500/crop.width)));card=Image.new('RGB',(1600,h),'white');draw=ImageDraw.Draw(card)
 label=f'{index:03d}/100' if index<=100 else 'TARGETED EXTRA'
 draw.text((10,5),f'{label}  {slug}  {r["font_px"]}px  dg={r["delta_g"]}  score={r["correct"]}/100',font=head,fill='black')
 draw.text((10,32),'PNG / SOURCE SCREEN (QA gain only)',font=small,fill='black');draw.text((545,32),'ACTUAL REPLY SCREENSHOT',font=small,fill='black');draw.text((1080,32),'RAW TXT (no correction)',font=small,fill='black')
 bbox=source.getbbox();bbox=(max(0,bbox[0]-10),max(0,bbox[1]-10),min(1080,bbox[2]+10),min(1200,bbox[3]+10));pa=source.crop(bbox);pb=screen.crop(bbox);peak=max(int(np.asarray(pa).max()),int(np.asarray(pb).max()),1);lut=[min(255,round(v*255/peak)) for v in range(256)]*3
 mid=60+(h-82)//2;fit(card,pa.point(lut),(10,60,520,mid));fit(card,pb.point(lut),(10,mid+8,520,h-20));fit(card,crop,(545,60,1050,h-15))
 for j,line in enumerate(lines):draw.text((1080,60+j*24),line,font=font,fill='black')
 draw.text((10,h-19),f'RGB exact={pixels["exact"]}; maxdiff={pixels["max_abs_difference"]}; originals unchanged',font=small,fill='black');cards.append(card)
 results.append(dict(draw_index=index if index<=100 else None,scope='random100' if index<=100 else 'targeted_extra',key=key,case_id=slug,round=n,font_px=r['font_px'],delta_g=r['delta_g'],response=txt,correct=r['correct'],automatic_checks=checks,source_pixels=pixels,image_manifest_source_round=m.get('round'),reply_bounds=box,reply_crop=str(crop_path.relative_to(W)),original_png=str((ev/'source-images'/r['image']).relative_to(ROOT)),source_screen=str((ev/r['source_screen']).relative_to(ROOT)),reply_screenshot=str((ev/r['screenshot']).relative_to(ROOT)),visual_review='PENDING'))
for start in range(0,len(cards),5):
 subset=cards[start:start+5];height=sum(x.height for x in subset)+8*(len(subset)-1);board=Image.new('RGB',(1600,height),'#BBBBBB');y=0
 for card in subset:board.paste(card,(0,y));y+=card.height+8
 name=f'board-{start//5+1:02d}.png';board.save(W/'boards'/name)
 for row in results[start:start+5]:row['board']='boards/'+name
p.save_json(W/'checks.json',results);p.save_json(W/'ocr-jobs.json',jobs)
p.save_json(W/'automatic-summary.json',dict(random_sample=100,random_checks_pass=sum(all(r['automatic_checks'].values()) for r in results[:100]),random_source_pixel_exact=sum(r['source_pixels']['exact'] for r in results[:100]),targeted_conditions=targets,targeted_already_in_sample=[x for x in targets if x in ids],targeted_extra=extra,total_rows=len(results),unreadable=sum(r['response']=='[UNREADABLE]' for r in results[:100]),transcription=sum(r['response']!='[UNREADABLE]' for r in results[:100]),failed=[{'key':r['key'],'checks':[k for k,v in r['automatic_checks'].items() if not v]} for r in results if not all(r['automatic_checks'].values())],boards=math.ceil(len(cards)/5)))
for z,meta,manifest in archives.values():z.close()
print(json.dumps(p.read_json(W/'automatic-summary.json'),ensure_ascii=False,indent=2))
