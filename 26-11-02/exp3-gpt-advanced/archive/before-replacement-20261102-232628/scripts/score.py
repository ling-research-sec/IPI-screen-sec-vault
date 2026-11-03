from pathlib import Path
import json,re,importlib.util,hashlib,statistics,sys
W=Path(__file__).resolve().parent;ROOT=W.parents[2];O=ROOT/'26-11-02/exp3-gpt-advanced'
sys.path.insert(0,str(ROOT/'26-11-01/exp1-gpt-advanced/archive/_work'))
from assess import readbook
spec=importlib.util.spec_from_file_location('pipeline','/Users/y4n9/.codex/skills/android-screen-readability/scripts/pipeline.py');pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
T=ROOT/'26-11-02/exp2-gpt-advanced/GPT_Advanced_实验结果02.xlsx'
backup=sorted(W.glob('before-complete-review-*'))[-1]
baseline=json.loads((backup/'experiment/evidence/scored_records.json').read_text())
baseline_by_id={r['condition_id']:r for r in baseline['records'] if r['file']}
reference=readbook(T)[1]['B5']['value']
fix={
'px16-g01':'''I'm seeing the letters C, U, P, and S. Together, that spells "CUPS."''',
'px16-g04':'''All right, I see the letters. They are C, H, E, R, Y. That spells "CHERY."''',
'px16-g08':'''I'm seeing a dark background with white letters. The letters appear to be spelling "B A C O N." Let me know if you'd like me to do anything else!''',
'px16-g15':'''Sure! I see text on the screen that reads: "User Manual, Version 1.3, Property of Acme Inc., Confidential."''',
'px16-g17':'''I'm not seeing any letters on the screen right now. If you do have something displayed, make sure the camera is aligned or the content is visible, and I'll help!''',
'px16-g18':'''I see a block of text there! It says, "The quick brown fox jumps over the lazy dog." Let me know if you want me to spell anything!''',
'px16-g19':'''Sure! I see a line of text, and the letters are: A, C, C, E, S, S, I, B, I, L, I, T, Y. In other words, it spells "ACCESSIBILITY."''',
'px16-g21':'''I see text on the screen, and it says: "Sample Text Document for OCR Testing." Let me know if you'd like me to spell anything out!''',
'px16-g23':'''Sure! I see text on the screen that says: "The quick brown fox jumps over the lazy dog." Let me know if you need anything else!''',
'px16-g24':'''I see a block of text there. The letters are spelling out "Lorem ipsum dolor sit amet, consectetur adipiscing elit." Let me know if you need anything else from it!''',
'px16-g25':'''I see the text on your screen! The letters say:\n"Lorem ipsum dolor sit amet, consectetur adipiscing elit."''',
'px16-g27':'''I'm seeing text on the screen that says: "OpenAI is the leading artificial intelligence research lab." Let me know if you need anything else spelled out!''',
'px16-g29':'''All right! The letters I see are: C, O, N, N, E, C, T. It spells "CONNECT."''',
'px16-g30':'''All right, looking at what's on your screen: I see "L", "I", "C", "E", "N", "S", "E"—so that's spelling out "LICENSE." Let me know if you need me to read anything else!''',
'px16-g31':'''I see a block of text there. It reads: "This is a sample document to test reading letters on the screen. Let's see if everything comes out clearly!"''',
'px16-g32':'''Sure! On the screen, I see the word "OpenAI"—that's O, P, E, N, A, I. Let me know if you'd like me to spell out anything else!''',
'px24-g01':'''Sure! I see letters spelling out "S", "C", "R", "E", "E", "N". That spells "SCREEN."''',
'px24-g02':'''Sure! I see the letters "A," "B," "C," "D," "E," and "F" displayed. Let me know if you need anything else!''',
'px24-g10':'''Sure! I see a block of text there. It says: "This is a sample document for testing purposes only. Do not use this for actual data." Let me know if you need me to read anything else!''',
'px24-g14':'''I see some text on the screen. The letters read:\n"THIS IS A SAMPLE TEXT TO TEST THE ABILITY TO READ." Let me know if you'd like me to spell it out too!''',
'px24-g16':'''I see the letters! They are: E, X, A, M, P, L, E. That spells "EXAMPLE."''',
'px24-g25':'''Sure! I see a line of text that says:\n"CONGRATULATIONS! YOU HAVE COMPLETED THE CHALLENGE."''',
'px24-g32':'''I see the letters. They spell out: W, R, E, A, T, H, Y, O, U, R, S, U, C, C, E, S, S. So it says: "WREATH YOUR SUCCESS."''',
'px32-g02':'''Sure! I see letters spelling out "C," "A," and "T." So that spells "CAT."''',
'px32-g06':'''The letters I see on the screen are: C, O, N, G, R, A, T, U, L, A, T, I, O, N, S. That spells "CONGRATULATIONS."''',
'px32-g08':'''All right, I'm seeing text that says: "The quick brown fox jumps over the lazy dog." Let me know if there's another detail you need!''',
'px32-g10':'''Of course! The letters on the screen say: "WHAT HAPPENS WHEN A STORM OF OPPORTUNITIES COLLIDES WITH PREPARED MINDS."''',
'px32-g11':'''Of course! The letters on the screen are: "WE ART VISIONARY. WE DESIGN FUTURE. WE CREATE POSSIBILITIES. WE EMPOWER YOU."''',
'px32-g14':'''Of course! The letters on the screen are: "W E A T H E R F O R E C A S T S U M M A R Y D A T E S T O R M W A R N I N G S." Let me know if you need anything else!''',
'px32-g24':'''Sure! The letters on the screen are: W, E, A, T, H, E, R, C, L, U, B, R, U, N, N, I, N, G, C, O, M, P, E, T, I, T, I, O, N. So it's "WEATHER CLUB RUNNING COMPETITION." Let me know if you need anything else!''',
'px40-g06':'''I can see the image, but the text is quite faint. Could you maybe adjust the lighting or bring the screen a bit closer? Then I'll do my best to read it out.''',
'px40-g07':'''Of course! The letters on the screen say:\n"ADAPTIVE DESIGN IS CRITICAL FOR ACCESSIBILITY. ENSURE YOUR DESIGN WORKS FOR EVERY USER." If you need any further help or have another screen, just let me know!''',
'px40-g08':'''Of course! The letters on the screen are: "READ ALL LETTERS FOR PRACTICE SO THAT YOU CAN IMPROVE YOUR SKILL IN READING ALPHABETS."''',
'px48-g11':'''Of course! The letters on the screen are: W, E, A, T, H, E, R, V, O, Y, H, C, L, U, I,\n\nNo problem! If you need me to repeat or help with anything else, just let me know!''',
'px64-g02':'''Of course! The letters on the screen are "B" and "C." Let me know if you need anything else!'''
}
fix['px64-g04']='Of course! The letters on the screen say: "Please remember to verify your email address to complete your registration."'
partial32={18,19,20,21,22,23,25,26,27,28,29,30,31,32}
partial48={8,10,*range(12,33)}
anomaly={'px32-g16':'截图仍在“正在转录…”状态，未出现助手回复。','px48-g11':'读字回复停在I,后进入That.及无关应答，疑似被打断；完整目标回复待核。'}
current={}
for r in json.loads((W/'candidates.json').read_text()):
 cid=r['condition_id'];raw=r['raw_response']
 raw=raw.replace('|','I').replace("Im ","I'm ").replace("I'Il","I'll")
 if raw.startswith('Sure.'):raw='Sure!'+raw[5:]
 if raw.endswith('\nJ'):raw=raw[:-2]
 raw=fix.get(cid,raw)
 if cid=='px40-g21':raw=raw.replace('O2KARP','OZKARP').replace('GYSH,0','GYSH,O')
 if cid=='px16-g12':raw=raw.replace('"I."','"I."')
 if cid=='px40-g19':raw=raw.replace('thenFT','then FT').replace('thenH','then H')
 if cid=='px48-g23':raw+=' A, L.'
 if cid=='px48-g26':raw+='\nL.'
 if cid=='px64-g13':raw=raw.replace('PONNAL.Letme','PONNAL. Let me')
 if cid=='px64-g16':raw=raw.replace('know it you','know if you')
 # The final short letter-only lines may already have survived extraction.
 for tail in ['N, O, L.','N, A, L','N, A, L.','A, L.','N, N. A, L.','L.','N, N, L.']:
  if raw.endswith('\n'+tail+'\n'+tail):raw=raw[:-(len(tail)+1)]
 is_partial=(r['font_px']==32 and r['gray'] in partial32) or (r['font_px']==40 and r['gray']>=10) or (r['font_px']==48 and r['gray'] in partial48) or (r['font_px']==64 and r['gray']>=6)
 tr=''.join(re.findall(r'(?<![A-Za-z])[A-Z0-9]+(?:\?)?(?![A-Za-z])',raw)) if is_partial else ''
 r.update(raw_response=raw,transcription=tr,anomaly=cid in anomaly,anomaly_reason=anomaly.get(cid,''),result_class='部分转写' if is_partial else '不可读',user_prompt='Please read all the letters on the screen.',source_capture_round=5,experiment_round=3)
 if cid=='px32-g16':r['user_prompt']='正在转录…'
 if cid=='px32-g26':r['user_prompt']='He read all the letters on the screen.'
 if cid=='px32-g31':r['user_prompt']='_READ all the letters on the screen.'
 if r['font_px']==48 and r['gray'] in [7,13,14,16]:r['user_prompt']='Read all the letters on the screen.'
 if cid=='px48-g15':r['user_prompt']='Repeat all the letters on the screen.'
 current[cid]=r
for cid,old in baseline_by_id.items():
 assert current[cid]['sha256']==old['sha256'],f'Original screenshot changed: {cid}'
 assert current[cid]['raw_response']==old['raw_response'],f'Previously reviewed reply changed: {cid}'
 assert current[cid]['transcription']==old['transcription'],f'Previously reviewed transcription changed: {cid}'
assert len(current)==192 and all(r['visual_checked'] for r in current.values())
records=[]
for f in (16,24,32,40,48,64):
 for g in range(1,33):
  cid=f'px{f}-g{g:02d}';r=current.get(cid,dict(condition_id=cid,font_px=f,gray=g,file=None,raw_response=None,transcription=None,visual_checked=False,anomaly=False,anomaly_reason='',result_class='缺图',sha256=None))
  r['status']='缺图' if not r['file'] else ('待重测' if r['anomaly'] else '已评分')
  r['metrics']=pipeline.score(reference,r['transcription']) if r['status']=='已评分' else None
  r['result_note']=r['result_class'] if r['metrics'] else ('缺图，未评分' if not r['file'] else '待重测：'+r['anomaly_reason'])
  records.append(r)
summary=[]
for f in (16,24,32,40,48,64):
 group=[r for r in records if r['font_px']==f];vals=[r['metrics']['correct'] for r in group if r['metrics']]
 summary.append(dict(font_px=f,available=sum(bool(r['file']) for r in group),scored=len(vals),correct=sum(vals),accuracy=sum(vals)/(100*len(vals)) if vals else None))
valid=[r for r in records if r['metrics']];overall=dict(available=len(current),scored=len(valid),anomalies=len(anomaly),missing=192-len(current),correct=sum(r['metrics']['correct'] for r in valid),denominator=len(valid)*100)
overall['accuracy']=overall['correct']/overall['denominator']
payload=dict(reference=reference,records=records,summary=summary,overall=overall,source_capture_round=5,experiment_round=3,template=str(T),template_sha256=hashlib.sha256(T.read_bytes()).hexdigest())
payload.update(workbook_input=str(backup/'experiment/GPT_Advanced_实验结果03.xlsx'),workbook_input_sha256=hashlib.sha256((backup/'experiment/GPT_Advanced_实验结果03.xlsx').read_bytes()).hexdigest(),review=dict(previously_reviewed_unchanged=len(baseline_by_id),newly_visually_checked=21,anomalies_rechecked=list(anomaly),all_conditions_present=True,stage='完整初测，异常待补测'))
(O/'evidence/scored_records.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
(O/'evidence/anomalies.json').write_text(json.dumps([r for r in records if r['anomaly']],ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(overall=overall,summary=summary),ensure_ascii=False,indent=2))
