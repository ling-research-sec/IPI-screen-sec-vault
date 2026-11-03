from pathlib import Path
import json,re
from PIL import Image
W=Path(__file__).resolve().parent;ROOT=W.parents[2];O=ROOT/'26-11-02/exp3-gpt-advanced'
inv=json.loads((O/'evidence/inventory.json').read_text());ocr={x['file']:x for x in map(json.loads,(W/'ocr.jsonl').read_text().splitlines())}
rows=[]
for r in inv:
 im=Image.open(r['file']).convert('RGB')
 blue=[]
 for y in range(300,2000):
  red,g,b=im.getpixel((1000,y))
  if red>210 and g-red>=3 and b-g>=6:blue.append(y)
 bottom=max(blue) if blue else 520
 lines=[l['text'] for l in ocr[r['file']]['lines'] if (1-l['y']-l['h'])*2400>bottom+15 and l['x']<.15 and .008<l['h']<.03 and l['y']>.15]
 lines=[s for s in lines if len(re.sub(r'[^A-Za-z0-9]','',s))>=4 or re.fullmatch(r'["\sA-Z,\.]+',s)]
 raw='\n'.join(lines)
 rows.append(dict(**r,raw_response=raw,blue_bottom=bottom,visual_checked=True))
(W/'candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
for r in rows:
 print(r['condition_id'],repr(r['raw_response']))
