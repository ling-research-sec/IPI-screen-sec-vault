from pathlib import Path
import json,hashlib,re,shutil,subprocess
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'26-11-02/exp3-gpt-advanced';WORK=Path(__file__).parent
SRC=Path('/Users/y4n9/Library/Application Support/GPT-Advanced-Single/captures/655f6610a98d40402555309ac20af296c91f60d0ff289a518cf7efd658ca93f2/第005轮')
OUT.mkdir(exist_ok=True);(OUT/'evidence/screenshots').mkdir(parents=True,exist_ok=True)
inventory=[]
for font in (16,24,32,40,48,64):
 for source in sorted((SRC/f'{font}px').glob('*.png')):
  gray=int(re.match(r'g(\d+)_',source.name)[1]);dest=OUT/'evidence/screenshots'/str(font)/source.name
  dest.parent.mkdir(exist_ok=True);shutil.copy2(source,dest)
  sha=hashlib.sha256(source.read_bytes()).hexdigest();assert sha==hashlib.sha256(dest.read_bytes()).hexdigest()
  inventory.append(dict(condition_id=f'px{font}-g{gray:02d}',font_px=font,gray=gray,file=str(dest),original_file=str(source),sha256=sha))
assert len({r['condition_id'] for r in inventory})==len(inventory)
(OUT/'evidence/inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')
for font in (16,24,32,40,48,64):
 rows=[r for r in inventory if r['font_px']==font]
 for st in range(0,len(rows),4):
  canvas=Image.new('RGB',(2160,3200),'#ddd');draw=ImageDraw.Draw(canvas)
  for i,r in enumerate(rows[st:st+4]):
   im=Image.open(r['file']).convert('RGB');assert im.size==(1080,2400)
   im=im.crop((0,285,1080,1845));x=i%2*1080;y=i//2*1600
   canvas.paste(im,(x,y+40));draw.text((x+10,y+10),r['condition_id'],fill='black')
  canvas.save(WORK/f'px{font}_{st+1:02d}.png')
with (WORK/'ocr.jsonl').open('w') as f:
 subprocess.run([str(ROOT/'26-11-01/exp1-gpt-advanced/archive/_work/ocr')]+[r['file'] for r in inventory],stdout=f,check=True)
print('PREPARE PASS snapshot_count',len(inventory))
