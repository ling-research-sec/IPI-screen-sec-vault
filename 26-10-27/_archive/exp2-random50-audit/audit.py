from pathlib import Path
import sys,json,re,hashlib,random,zipfile,xml.etree.ElementTree as ET
import numpy as np
from PIL import Image,ImageOps,ImageDraw,ImageFont
W=Path(__file__).resolve().parent;ROOT=W.parents[2];E=ROOT/'26-10-27/exp2-perplexity';EV=E/'evidence-01'
sys.path.insert(0,str(W.parent/'exp2-process/runner'));import pipeline as p
selection=p.read_json(W/'sample-manifest.json');ids=selection['draw_order']
assert random.Random(int(selection['seed_hex'],16)).sample(selection['population_ids'],50)==ids and len(set(ids))==50
c=p.Config(W.parent/'exp2-process/config-full.json');images={m['case_id']:m for m in p.read_json(EV/'records/image-manifest.json')}
sheets,n=p.read_xlsx(E/'实验结果-01.xlsx');main,raw=sheets;assert n==160
rows={main[f'A{r}'][0]:r for r in range(10,170)};rawrows={raw[f'A{r}'][0]:r for r in range(9,169)}
for d in ['reply-crops','boards']:(W/d).mkdir(exist_ok=True)
font=ImageFont.truetype('/System/Library/Fonts/Menlo.ttc',29);small=ImageFont.truetype('/System/Library/Fonts/Menlo.ttc',23);head=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',32)
cards=[];results=[];crop_jobs=[]
def paste_fit(board,im,box):
 im=im.copy();im.thumbnail((box[2]-box[0],box[3]-box[1]),Image.Resampling.NEAREST)
 board.paste(im,(box[0]+((box[2]-box[0])-im.width)//2,box[1]))
def corr(a,b):
 if not a.std() or not b.std():return None
 return float(np.corrcoef(a.flatten(),b.flatten())[0,1])
for index,case in enumerate(ids,1):
 r=p.read_json(EV/'records'/f'exp2-result-{case}.json');m=images[case]
 txt=(EV/r['response_file']).read_text().removesuffix('\n');checks={}
 checks['ids_and_conditions']=r['case_id']==r['parameter_value']==m['case_id']==case and r['font_px']==m['font_px'] and r['delta_g']==m['delta_g'] and r['round']==m['round']==1
 checks['input_hash']=p.file_hash(EV/'source-images'/r['image'])==r['source_sha256']==r['phone_source_sha256']==m['png_sha256']
 for key,hkey in [('response_file','response_sha256'),('screenshot','screenshot_sha256'),('source_screen','source_screen_sha256')]:checks[hkey]=p.file_hash(EV/r[key])==r[hkey]
 checks['txt_equals_record']=txt==r['response'];checks['reference']=m['expected_text']==c.reference and r['reference_sha256']==p.digest(c.reference.encode())
 with zipfile.ZipFile((E/r['ui_archive']).resolve()) as z:
  answer=z.read(r['answer_xml_archive_member']);prompt=z.read(r['prompt_xml_archive_member']);query=z.read(f'round01/g{case}/source-query.txt').decode();state=json.loads(z.read(f'round01/g{case}/state.json'))
  am=ET.fromstring(answer);pn=ET.fromstring(prompt);archive_manifest=json.loads(z.read('manifest.json'))
  checks['archived_ui_hash']=hashlib.sha256(answer).hexdigest()==archive_manifest['files'][r['answer_xml_archive_member']] and hashlib.sha256(prompt).hexdigest()==archive_manifest['files'][r['prompt_xml_archive_member']]
  text_nodes=[x for x in am.iter('node') if x.get('class')=='android.widget.TextView' and x.get('text')]
  checks['answer_xml_equals_txt']='\n'.join(x.get('text') for x in text_nodes)==txt
  checks['completion_ui']=any(x.get('content-desc')==c.ui['copy_desc'] for x in am.iter('node')) and not any(any(t in x.get('content-desc','') for t in c.ui['thinking_contains']) for x in am.iter('node'))
  edits=[x for x in pn.iter('node') if x.get('class')=='android.widget.EditText'];checks['prompt']=len(edits)==1 and edits[0].get('text')==r['prompt_sent']==c.prompt
  checks['source_query']=f'_display_name={case}.png,' in query and 'relative_path=Pictures/26-10-27-exp2/' in query
  checks['state_completed']=state['phase']=='completed' and state['submitted'] and state['value']==case
 row=rows[case];rr=rawrows[case];checks['xlsx_reply']=raw[f'B{rr}'][0]==txt
 checks['xlsx_conditions']=int(float(main[f'J{row}'][0]))==r['font_px'] and int(float(main[f'K{row}'][0]))==r['delta_g'] and int(float(main[f'L{row}'][0]))==1
 score=p.score(c.reference,txt);checks['scoring']=all(r[k]==v for k,v in score.items()) and all(int(float(main[f'{col}{row}'][0]))==r[key] for col,key in [('B','correct'),('D','substitutions'),('E','deletions'),('F','insertions')]) and abs(float(main[f'M{row}'][0])-r['cer'])<1e-10
 source=Image.open(EV/'source-images'/r['image']).convert('RGB');screen=Image.open(EV/r['source_screen']).convert('RGB');reply=Image.open(EV/r['screenshot']).convert('RGB');checks['dimensions']=source.size==screen.size==reply.size==(1080,2400)
 # Inspect the entire possible text region, including outside the expected glyph bounds.
 region=(65,650,1030,1120);a=np.asarray(source.crop(region)).astype(np.float64);b=np.asarray(screen.crop(region)).astype(np.float64);delta=b-a
 pixels={'region':region,'pixel_exact':bool(np.array_equal(a,b)),'changed_pixels':int(np.count_nonzero(np.any(delta!=0,axis=2))),'max_abs_difference':float(np.abs(delta).max()),'rmse':float(np.sqrt(np.mean(delta**2))),'input_max':float(a.max()),'source_screen_max':float(b.max()),'correlation':corr(a,b),'zero_intercept_gain':float((a*b).sum()/(a*a).sum())}
 bounds=[list(map(int,re.findall(r'\d+',x.get('bounds')))) for x in text_nodes];box=(max(0,min(b[0] for b in bounds)-10),max(0,min(b[1] for b in bounds)-10),min(1080,max(b[2] for b in bounds)+10),min(2400,max(b[3] for b in bounds)+10))
 crop=reply.crop(box);crop_path=W/'reply-crops'/f'{case}.png';crop.save(crop_path);crop_jobs.append({'case_id':case,'image':str(crop_path),'bounds':box})
 card=Image.new('RGB',(2100,610),'white');draw=ImageDraw.Draw(card)
 draw.text((16,8),f'{index:02d}/50  {case}  font={r["font_px"]}px  dg={r["delta_g"]}  correct={r["correct"]}/100',font=head,fill='black')
 draw.text((16,52),'INPUT PNG / SOURCE SCREEN',font=small,fill='black');draw.text((700,52),'ACTUAL REPLY SCREENSHOT',font=small,fill='black');draw.text((1410,52),'SAVED RAW TXT (no correction)',font=small,fill='black')
 bbox=source.getbbox();src_box=(max(0,bbox[0]-10),max(0,bbox[1]-10),min(1050,bbox[2]+10),min(1200,bbox[3]+10));pa=source.crop(src_box);pb=screen.crop(src_box)
 peak=max(np.asarray(pa).max(),np.asarray(pb).max(),1);lut=[min(255,round(v*255/int(peak))) for v in range(256)]*3
 paste_fit(card,pa.point(lut),(16,96,670,320));paste_fit(card,pb.point(lut),(16,346,670,570));draw.text((16,320),'Source screen below; same display gain',font=small,fill='black')
 paste_fit(card,crop,(700,96,1385,530))
 y=98
 for line in txt.splitlines():
  for start in range(0,max(1,len(line)),34):draw.text((1410,y),line[start:start+34],font=font,fill='black');y+=39
 draw.text((700,548),f'Pixel exact: {pixels["pixel_exact"]}; maxdiff={pixels["max_abs_difference"]:g}; corr={pixels["correlation"]:.4f}',font=small,fill='black')
 draw.text((700,579),'Left crops gain-enhanced for QA only; originals unchanged.',font=small,fill='black')
 cards.append(card)
 results.append({'draw_index':index,'case_id':case,'font_px':r['font_px'],'delta_g':r['delta_g'],'correct':r['correct'],'response':txt,'automatic_checks':checks,'source_pixels':pixels,'reply_crop':str(crop_path.relative_to(W)),'visual_review':'PENDING','ocr_review':'PENDING'})
for i in range(0,len(cards),2):
 board=Image.new('RGB',(2100,1230),'#BBBBBB');board.paste(cards[i],(0,0));board.paste(cards[i+1],(0,620));board.save(W/'boards'/f'pair-{i//2+1:02d}.png')
p.save_json(W/'checks.json',results);p.save_json(W/'ocr-jobs.json',crop_jobs)
print(json.dumps({'sample':len(results),'all_file_xml_sheet_checks_pass':sum(all(r['automatic_checks'].values()) for r in results),'source_pixel_exact':sum(r['source_pixels']['pixel_exact'] for r in results),'source_pixel_different':sum(not r['source_pixels']['pixel_exact'] for r in results),'reply_transcription_cases':sum(r['response']!='[UNREADABLE]' for r in results),'visual_boards':25},indent=2))
