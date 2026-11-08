from PIL import Image,ImageOps,ImageDraw
from pathlib import Path
import json,collections
OUT=Path(__file__).parent;rows=json.loads((OUT/'最终精选60条.json').read_text());groups=collections.defaultdict(list)
for r in rows:groups[(r['phase'],r['scene_index'])].append(r)
(OUT/'visual').mkdir(exist_ok=True)
for (phase,scene),rs in groups.items():
 sheet=Image.new('RGB',(1800,1460),'#ddd');d=ImageDraw.Draw(sheet)
 for col,r in enumerate(rs):
  raw=Path(r['raw'])
  for row,name in enumerate(('post.png','post_tool_app.png' if r['scene']!='改变模型回答' else 'baseline.png')):
   p=raw/name
   if not p.exists():continue
   im=Image.open(p).convert('RGB');im.thumbnail((350,690));x=col*360+(350-im.width)//2;y=row*730+30
   sheet.paste(im,(x,y));d.text((col*360+4,row*730+5),f'{phase} row{r["row"]} {name}',fill='black')
 sheet.save(OUT/'visual'/f'{phase}-{scene:02d}.jpg',quality=92)
print('CONTACT_SHEETS=12 ORIGINAL_IMAGES_UNCHANGED=true')
