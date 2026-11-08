"""One explicit queue invocation = one bounded attempt per unfinished case."""
from pathlib import Path
import json
from .evidence import p1_case_path,p1_recovery_round,p1_round_dir,verify_run
from .progress import read_run,latest_continuation,complete_run
from .runner import p1_unsubmitted_baseline_restart_eligible,p1_observation_restart_eligible
from .state import DeviceLease,LabError


def queued_run_path(case,config,entry,deferred=None):
    """Index is authoritative; a deferred report is only a fallback path, not a blacklist."""
    recorded=entry.get('run_dir')
    if recorded:return latest_continuation(recorded)
    original=p1_case_path(config['evidence_root'],case,config['p1_round'])
    if original.exists():return latest_continuation(original)
    prior=(deferred or {}).get('evidence')
    return latest_continuation(prior) if prior else None


def pending_first(jobs,config,serial):
    registry=DeviceLease(config['state_dir'],serial).path
    if not registry.exists():return list(jobs),{}
    saved=json.loads(registry.read_text())
    if not saved.get('unresolved'):return list(jobs),{}
    path=latest_continuation(saved['run_dir'])
    if complete_run(path):return list(jobs),{}
    result,_=read_run(path)
    match=next((c for c in jobs if c.case_id==result.get('case_id') and
                c.workbook_sha256==result.get('source',{}).get('workbook_sha256')),None)
    if (match is None or result.get('serial')!=serial or
            p1_recovery_round(config['evidence_root'],path)!=p1_round_dir(config['evidence_root'],config['p1_round'])):
        raise LabError('设备有其他轮次或范围的未决运行，未启动新队列')
    return [match]+[c for c in jobs if c.case_id!=match.case_id],{match.case_id:path}


def prepare_attempt(factory,serial,case,config,control,path=None,log=None,review=None):
    """Return a runner and its explicit resume/restart args; never execute here."""
    if path is None:return factory(serial,case,config,control),{},'新测'
    path=latest_continuation(path)
    result,_=read_run(path)
    if (p1_recovery_round(config['evidence_root'],path)!=p1_round_dir(config['evidence_root'],config['p1_round'])
            or result.get('pathway')!='p1' or result.get('case_id')!=case.case_id
            or result.get('serial')!=serial or result.get('source',{}).get('row')!=case.row
            or result.get('source',{}).get('workbook_sha256')!=case.workbook_sha256):
        raise LabError('旧记录不属于本轮本设备本 Case，保留原证据')
    from .evidence import interrupted_organization_sources
    layout=interrupted_organization_sources(path) if config.get('p1_auto_recovery') else None
    if layout is None and ((path/'.manifest.json').exists() or (path/'manifest.json').exists()):verify_run(path)
    if result.get('status')=='complete' and layout is None:
        raise LabError('旧运行标记完成但进度未验收，需核查证据，不重发请求')
    cfg=dict(result['config'])
    for key in ('evidence_root','state_dir','p1_round','outbound_test_confirmed','home_test_confirmed','p1_auto_recovery','p1_recovery_attempts','p1_reconnect_seconds','p1_queue_journal_path'):
        if key in config:cfg[key]=config[key]
    if (p1_unsubmitted_baseline_restart_eligible(result) or p1_observation_restart_eligible(result)) and not (cfg.get('p1_auto_recovery') and result.get('submissions')):
        cfg.pop('fast_response_budget_seconds',None)
        return factory(serial,case,cfg,control),{'restart_from':path},'从头补测'
    from p1_file_upload.runner import P1Runner
    if cfg.get('p1_tool_pilot')==1:
        from p1_file_upload.tool_pilot import P1ToolPilot
        cls=P1ToolPilot
    elif cfg.get('p1_tool_capture')==1:
        from p1_file_upload.tool_capture import P1ToolCapture
        cls=P1ToolCapture
    else:cls=P1Runner
    runner=cls.from_run(serial,path,control=control,log=log,state_dir=config['state_dir'])
    runner.config.update(cfg)
    if cfg.get('p1_tool_pilot')==1:runner.review=review
    return runner,{'resume_from':path},'续接（不重发已提交阶段）'


def preflight_queue_records(jobs, config, entries, deferred=None):
    """Read-only gate: absent evidence is unknown, never proof of no submission."""
    errors=[]
    for case in jobs:
        try:
            path=queued_run_path(case,config,entries.get(case.case_id,{}),(deferred or {}).get(case.case_id))
            if path is None:
                continue
            if not path.is_dir() or not ((path/'result.json').is_file() or (path/'_debug/result.json').is_file()):
                errors.append(f'Excel第{case.row}行：{path}')
                continue
            read_run(path)  # Reject corrupt records before a worker touches the phone.
        except (OSError, ValueError, LabError) as exc:
            errors.append(f'Excel第{case.row}行：{exc}')
    if errors:
        raise LabError('队列未启动：'+str(len(errors))+'条旧证据缺失或不可读；未执行、未重发、未改完成状态。'
                       +'请恢复原记录，或明确建立独立新轮补测；缺文件不代表从未发送。\n'+'\n'.join(errors))
