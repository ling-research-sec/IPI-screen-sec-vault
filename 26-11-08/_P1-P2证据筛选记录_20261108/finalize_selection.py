from pathlib import Path
import json,re
OUT=Path(__file__).parent;rs=json.loads((OUT/'已排序候选.json').read_text())
choices={
'P1':{
'改变模型回答':[26,4,5,6,7],
'打电话、发短信、发邮件':[38,42,39,33,43],
'智能家居':[55,56,57,58,59],
'日程安排':[69,77,78,79,67],
'导航场景':[81,82,88,91,94],
'笔记写入':[97,100,101,106,111]},
'P2':{
'改变模型回答':[26,3,4,5,6],
'打电话、发短信、发邮件':[34,35,39,40,43],
'智能家居':[50,51,53,56,58],
'日程安排':[63,65,67,71,75],
'导航场景':[82,89,91,92,93],
'笔记写入':[100,101,103,105,108]}}
# Final selection retains measurable native fields over generic long answers,
# and avoids duplicating the same case or filling a scenario with identical gates.
selected=[]
for phase,scenes in choices.items():
 for si,(scene,ids) in enumerate(scenes.items(),1):
  for rank,row in enumerate(ids,1):
   options=[r for r in rs if r['phase']==phase and r['scene']==scene and r['row']==row and r['eligibility']]
   assert options,(phase,scene,row)
   r=max(options,key=lambda r:r['rank_key']);r.update(scene_rank=rank,scene_index=si)
   r['manual_selection_reason']='按E目标接近度优先；同Case只留一份；比较可见字段/原生画面、全文复制与A/C/D链路，避免重复的授权弹窗或仅有冗长解释。'
   selected.append(r)
assert len(selected)==60 and len({(x['phase'],x['row']) for x in selected})==60
(OUT/'最终精选60条.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
for r in selected:print(r['phase'],r['scene'],r['row'],r['round'],Path(r['folder']).name)
