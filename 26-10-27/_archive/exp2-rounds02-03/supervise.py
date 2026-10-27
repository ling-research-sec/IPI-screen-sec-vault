#!/usr/bin/env python3
"""Single durable supervisor. Never retries or overrides the Skill's preflight/lock/stop gates."""
from pathlib import Path
import datetime,json,os,subprocess,sys,time,fcntl
W=Path(__file__).resolve().parent
CONFIGS=[W/'config-02.json',W/'config-03.json']
PYTHON='/opt/homebrew/opt/python@3.14/bin/python3.14'
from PIL import Image  # fail before launching device work if runtime dependencies differ
ROOT=Path(json.loads(CONFIGS[0].read_text())['experiment_dir'])
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(name,d):
 p=W/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def counts():return {f'{n:02d}':len(list((ROOT/f'evidence-{n:02d}'/'records').glob('exp2-result-*.json'))) for n in [2,3]}
def command(args,logname):
 print('COMMAND',json.dumps(args),flush=True)
 with (W/logname).open('x') as log:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
  save('handle.json',dict(supervisor_pid=os.getpid(),runner_pid=child.pid,command=args,started_utc=now(),log=str(W/logname),status_file=str(W/'status.json')))
  for line in child.stdout:
   log.write(line);log.flush()
   try:item=json.loads(line)
   except (ValueError,TypeError):print(line.rstrip(),flush=True);continue
   if isinstance(item,dict) and item.get('status')=='completed' and 'value' in item:
    ct=counts();done=sum(ct.values());state=dict(status='running',completed=done,target=320,round_counts=ct,round=item['round'],case=item['value'],workflow_interruptions=len(list((ROOT/'evidence-02/excluded').glob('attempt-*'))),recognition_failures_not_invented=True,updated_utc=now());save('status.json',state)
    if done%16==0 or done==320:print('PROGRESS '+json.dumps(state,ensure_ascii=False),flush=True)
  rc=child.wait()
 if rc:raise subprocess.CalledProcessError(rc,args)
 return rc
if __name__=='__main__':
 lock=(W/'supervisor.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 keepawake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  ct=counts();save('status.json',dict(status='starting',completed=sum(ct.values()),target=320,round_counts=ct,updated_utc=now()))
  for config in CONFIGS:
   n=json.loads(config.read_text())['rounds'][0]
   command([PYTHON,'-u',str(W/'runner/pipeline.py'),'run',str(config),'--execute'],f'run-live-{n:02d}.log')
  ct=counts();assert ct=={'02':160,'03':160},ct
  save('status.json',dict(status='collection_complete',completed=320,target=320,round_counts=ct,updated_utc=now(),next='report/verify/visual review/archive'))
  save('exit.json',dict(exit_status=0,finished_utc=now(),completed=320))
 except BaseException as exc:
  ct=counts();save('status.json',dict(status='stopped_on_error',completed=sum(ct.values()),target=320,round_counts=ct,error=str(exc),updated_utc=now(),automatic_retry=False));save('exit.json',dict(exit_status=1,error=str(exc),finished_utc=now()));print('STOPPED',repr(exc),flush=True);sys.exit(1)
