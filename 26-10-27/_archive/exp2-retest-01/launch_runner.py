#!/usr/bin/env python3
"""Durable process handle only; the Skill runner still owns preflight/lock/collection."""
import json,os,subprocess,sys,time
from pathlib import Path
W=Path(__file__).resolve().parent
def save(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
if sys.argv[1]=='--worker':
    config=Path(sys.argv[2]).resolve();stem=sys.argv[3]
    command=[sys.executable,'-u',str(W/'runner/pipeline.py'),'run',str(config),'--execute']
    log=W/(stem+'.log');exit_file=W/(stem+'-exit.json')
    with log.open('xb') as output:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        meta={'pid':process.pid,'supervisor_pid':os.getpid(),'log':str(log),'exit_status_file':str(exit_file),'config':str(config),'command':command,'started_unix':time.time()}
        save(W/'live-session.json',meta);save(W/(stem+'-handle.json'),meta)
        status=process.wait()
    save(exit_file,{'pid':process.pid,'exit_status':status,'finished_unix':time.time()})
    sys.exit(0 if status==0 else 1)
else:
    config=(W/sys.argv[1]).resolve();stem=sys.argv[2]
    prior=W/'live-session.json'
    if prior.exists():
        old=json.loads(prior.read_text());pid=old['pid']
        args=subprocess.run(['ps','-p',str(pid),'-o','args='],capture_output=True).stdout.decode('utf8','replace')
        if 'pipeline.py' in args and 'run' in args:raise SystemExit('Existing runner is live; poll its saved PID/log instead of starting another')
    if (W/(stem+'.log')).exists():raise SystemExit('Log stem already used; keep prior run immutable')
    with (W/(stem+'-supervisor.log')).open('xb') as output:
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker',str(config),stem],stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    for _ in range(100):
        handle=W/(stem+'-handle.json')
        if handle.exists():print(handle.read_text(),flush=True);break
        time.sleep(.1)
    else:raise SystemExit('Supervisor did not publish its process handle; inspect supervisor log before any restart')
