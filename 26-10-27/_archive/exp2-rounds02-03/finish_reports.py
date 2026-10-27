#!/usr/bin/env python3
"""Wait for this capture's successful exit, then reuse Skill report/verify. No device calls/retries."""
from pathlib import Path
import fcntl,json,os,subprocess,sys,time
W=Path(__file__).resolve().parent
NODE='/Users/y4n9/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
MODULES='/Users/y4n9/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
MARKER='/Users/y4n9/.codex/plugins/cache/openai-primary-runtime/spreadsheets/26.1020.11618/skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs'
sys.path.insert(0,str(W/'runner'));import pipeline as p
lock=(W/'finish-reports.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
c=p.Config(W/'config-full.json')
def save(d):p.save_json(W/'report-status.json',d)
try:
 save(dict(status='waiting_for_collection',pid=os.getpid(),updated_utc=p.utc()))
 while not (W/'exit.json').exists():time.sleep(15)
 exit_info=p.read_json(W/'exit.json')
 if exit_info['exit_status']!=0:
  save(dict(status='collection_stopped_no_reports_generated',capture_exit=exit_info,updated_utc=p.utc()));sys.exit(1)
 assert exit_info['completed']==320
 assert all(c.record(n,v).exists() for n in [2,3] for v in c.values)
 assert all(not (c.root/f'实验结果-{n:02d}.xlsx').exists() for n in [2,3])
 for n in [2,3]:
  for v in c.values:
   assert p.validate_existing(c,n,v);d=p.read_json(c.record(n,v));assert d['source_fidelity']['status']=='PASS'
   for key,rel in [('response_sha256',d['response_file']),('screenshot_sha256',d['screenshot']),('source_screen_sha256',d['source_screen'])]:assert p.file_hash(c.evidence(n)/rel)==d[key]
 subprocess.run([NODE,MARKER,'--operation-kind','create','--expected-output-count','2','--output-format','xlsx'],check=True)
 verification=p.report(c,NODE,MODULES);p.save_json(W/'reports-before-display-verification.json',verification)
 for n in [2,3]:subprocess.run([NODE,str(W/'display_ids.mjs'),str(c.root/f'实验结果-{n:02d}.xlsx')],check=True)
 original=p.read_xlsx
 def read_display_ids(file):
  sheets,count=original(file)
  for sheet,start in [(sheets[0],10),(sheets[1],9)]:
   for i in range(start,start+count):
    value,formula=sheet[f'A{i}'];assert value.startswith('px');sheet[f'A{i}']=('f'+value[2:],formula)
  return sheets,count
 p.read_xlsx=read_display_ids
 verified=p.verify_reports(c);p.save_json(W/'reports-after-display-verification.json',verified)
 hashes=p.read_json(W/'protected-input-hashes.json')
 for rel,h in hashes.items():assert p.file_hash(c.root.parent.parent/rel)==h
 save(dict(status='reports_verified_pending_visual_review_and_archive',completed=320,verified=verified,workbooks=[str(c.root/f'实验结果-{n:02d}.xlsx') for n in [2,3]],updated_utc=p.utc()))
except BaseException as exc:
 if not isinstance(exc,SystemExit):save(dict(status='stopped_on_report_error',error=repr(exc),updated_utc=p.utc()))
 raise
