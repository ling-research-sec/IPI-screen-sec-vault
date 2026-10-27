#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
work=Path(__file__).resolve().parent
sys.path.insert(0,str(work/'runner'))
import pipeline as p
c=p.Config(work/'config-full.json');target=int(sys.argv[1]);live=json.loads((work/'live-session.json').read_text());pid=live['pid'];log=Path(live['log'])
while True:
    records=[p.read_json(path) for path in (c.evidence(1)/'records').glob('exp2-result-*.json')]
    if len(records)>=target:
        for d in records:
            v=d['case_id'];p.validate_existing(c,1,v)
            for path_key,hash_key in [('response_file','response_sha256'),('screenshot','screenshot_sha256'),('source_screen','source_screen_sha256')]:
                p.require(p.file_hash(c.evidence(1)/d[path_key])==d[hash_key],'Evidence SHA256 mismatch')
            scoring=p.score(c.reference,d['response'],c.whitespace)
            p.require(all(d[k]==value for k,value in scoring.items()),'Deterministic score mismatch')
        latest=max(records,key=lambda d:d['completed_utc'])
        summary={'checkpoint':target,'completed':len(records),'valid_evidence':len(records),'font_px':latest['font_px'],'delta_g':latest['delta_g'],'scan_failures':0,'per_font':{str(f):sum(d['font_px']==f for d in records) for f in [16,24,32,40,64]}}
        p.save_json(work/f'checkpoint-{target:03d}.json',summary)
        print(json.dumps(summary,ensure_ascii=False),flush=True);break
    try:os.kill(pid,0)
    except ProcessLookupError:
        print(json.dumps({'status':'RUNNER_EXITED_BEFORE_CHECKPOINT','completed':len(records),'target':target,'log_tail':log.read_text()[-3500:]},ensure_ascii=False),flush=True)
        sys.exit(2)
    time.sleep(3)
