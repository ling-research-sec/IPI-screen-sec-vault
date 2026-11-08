"""Local persistent registration. Manual marks never rewrite experiment evidence."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
from .evidence import atomic_json,verify_run,sha,utc
from .state import LabError


def read_run(path):
    from .p2_archive import resolve_run
    path=resolve_run(path)
    if (path/'input.json').is_file() and not (path/'result.json').exists():
        try:
            protocol=json.loads((path/'input.json').read_text()).get('inputs',{}).get('config',{})
        except (ValueError,OSError):
            protocol={}
        if 'p3' in path.parts and protocol:
            raise LabError('此设备保留 P3 日历流程断点（input/checkpoints 格式），请核对并交接 P3；不会按 P1 result.json 读取或重复发送：'+str(path))
    raw=path/'_debug' if (path/'_debug/result.json').exists() else path
    if not (raw/'result.json').is_file():
        raise LabError('旧证据记录缺失：'+str(raw/'result.json')+'；保留原提交状态，请恢复文件或明确新轮补测，不自动重发')
    result=json.loads((raw/'result.json').read_text())
    if not isinstance(result,dict):raise LabError('运行记录不是有效对象')
    # An intent line is fsynced before any tap. Recover it even when process exit
    # interrupted the subsequent atomic result replacement; never replay that phase.
    journal=raw/'events.jsonl'
    if not journal.exists() and (path/'events.jsonl').exists():journal=path/'events.jsonl'
    if journal.exists():
        submissions=dict(result.get('submissions',{}));rank={'may_have_been_sent':1,'received':2,'response_observed':3,'response_sampled_unverified':3}
        for line in journal.read_text().splitlines(keepends=True):
            try:event=json.loads(line)
            except ValueError:
                if not line.endswith('\n'):break
                raise LabError('提交日志存在损坏的完整记录，保留现场，不重新发送')
            if event.get('stage')=='submission' and event.get('label') and event.get('state') in rank:
                label=event['label'];state=event['state']
                if rank[state]>rank.get(submissions.get(label),0):submissions[label]=state
            if result.get('pathway') == 'p2':
                if event.get('stage') == 'p2_checkpoint' and event.get('label'):
                    fields={k:v for k,v in event.items() if k not in ('time','stage','label')}
                    result.setdefault('p2_progress',{}).setdefault(event['label'],{}).update(fields)
                elif event.get('stage') == 'p2_note_source_bound':
                    result['p2_source_binding']={k:v for k,v in event.items() if k not in ('time','stage')}
                elif event.get('stage') == 'p2_assistant_identity_bound':
                    result.setdefault('p2_source_binding',{})['assistant_identity']=event['identity']
        result['submissions']=submissions
    # A new verifier may prove an old selection-copy record complete. Derive a
    # current view only: never rewrite its sealed result, manifest or A/C evidence.
    if (result.get('pathway')=='p2' and result.get('status')=='needs_post_review'
            and result.get('post_capture',{}).get('copy_failure_reason')=='selection_scope_or_text_coverage_unconfirmed'):
        from p2_screen_pdf.post_capture import selection_copy_proof
        import copy
        proof=selection_copy_proof(result,raw)
        if proof:
            candidate=copy.deepcopy(result)
            candidate.update(status='complete',completion_status='complete',
                             recorded_status=result['status'],completion_reclassified_by='selection_exact_reply_v1')
            candidate['post_capture'].update(status='complete',text_coverage='exact_reply_text_in_selection_copy',selection_verification=proof)
            candidate['post_capture'].pop('copy_failure_reason',None)
            candidate['post_response']['full_response']='selection_copy_with_exact_reply_and_viewport_coverage'
            try:
                if _complete_p2(path,candidate,raw):result=candidate
            except (OSError,ValueError,KeyError,TypeError,AttributeError,LabError):pass
    return result,raw


def latest_continuation(path):
    """Do not allow a stale ancestor to replay stages completed by its child."""
    from .p2_archive import resolve_run,round_for,round_runs
    path=resolve_run(path);visited=set()
    while path not in visited:
        visited.add(path);children=[]
        if not path.parent.is_dir():return path
        # Legacy runs share a case parent; new runs share a pathway across rounds.
        candidates=set(path.parent.iterdir()) | set(path.parent.parent.glob('第*轮/case*'))
        folder=round_for(path)
        if folder is not None:
            candidates.update(round_runs(folder))
            candidates.update(folder.parent.glob('第*轮archive/case*'))
        # Archived parents may have their new continuation in the clean round.
        for base in path.parents:
            if base.name != 'p1':continue
            from .evidence import p1_recovery_round
            folder=p1_recovery_round(base.parent,path)
            if folder is not None and folder.is_dir():candidates.update(folder.iterdir())
            break
        for candidate in candidates:
            if not candidate.is_dir() or candidate.resolve()==path:continue
            try:result,_=read_run(candidate)
            except (OSError,ValueError,LabError):continue
            parents=[resolve_run(result[k]) for k in ('resumed_from','fresh_restart_of') if result.get(k)]
            if path in parents:
                children.append(candidate.resolve())
        if not children:return path
        if len(children)!=1:raise LabError('发现多个续接分支，先人工核查，不重复发送')
        path=children[0]
    raise LabError('续接记录形成循环，请人工核查')


def verified_post_screenshot_fallback(raw, info):
    """A real, unchanged post screenshot can stand in for unavailable clipboard text."""
    from .ui import png_ok
    if (info.get('status')!='screenshot_only' or info.get('source')!='post_screenshot'
            or not info.get('reason')):
        return False
    try:
        png=Path(raw)/'post.png'
        return png_ok(png.read_bytes()) and sha(png)==info.get('sha256')
    except OSError:return False


def complete_run(path):
    """Full stages + timer + native post MD + manifest, not just a screenshot/status."""
    try:
        result,raw=read_run(path)
        if result.get('pathway') == 'p2':
            return _complete_p2(path, result, raw)
        if result.get('status')!='complete' or not result.get('p1_cycle_complete'):return False
        if result.get('p1_protocol',{}).get('post_prompt_source')!='xlsx_D':return False
        config=result.get('config',{})
        fast=bool(config.get('p1_fast_capture') or config.get('gui_direct_batch'))
        phase_state='response_sampled_unverified' if fast else 'response_observed'
        if config.get('p1_fast_capture') and any(
                result.get(k+'_response',{}).get('response_seen') is not True
                for k in ('baseline','injection','post')):return False
        if any(result.get('submissions',{}).get(k)!=phase_state for k in ('baseline','injection','post')):return False
        wait=result.get('injection_wait',{})
        if wait.get('status')!='completed' or wait.get('remaining_seconds',0)!=0:return False
        if wait.get('elapsed_active_seconds',wait.get('elapsed_wall_seconds',-1))<wait.get('requested_seconds',0):return False
        verify_run(path)
        source=result['source']
        from p1_file_upload.pdf_payload import CHAT_ARTIFACT, CHAT_MESSAGE, LEGACY_MODE, PDF_MODE, verify_payload
        protocol = result['p1_protocol']
        mode = result.get('config', {}).get('p1_injection_mode', LEGACY_MODE)
        if mode != protocol.get('injection_mode', LEGACY_MODE):
            return False
        if mode == PDF_MODE:
            if (protocol.get('injection_prompt_source') != 'xlsx_C_pdf_page_2'
                    or protocol.get('injection_chat_message') != CHAT_MESSAGE
                    or (raw/'actual_attacker_prompt.txt').exists()):
                return False
            verify_payload(raw, source, result['p1_pdf_attachment'])
            injection = (CHAT_ARTIFACT+'.txt', CHAT_MESSAGE)
        elif mode == LEGACY_MODE:
            injection = ('actual_attacker_prompt.txt',source['attacker_prompt'])
        else:
            return False
        for name,text in [('actual_baseline_prompt.txt',source['user_prompt']),
                          injection,
                          ('actual_post_prompt.txt',source['verification_prompt'])]:
            if (raw/name).read_bytes()!=text.encode():return False
        if any(not (raw/name).is_file() for name in ['baseline.png','response.png','post.png']):return False
        if source['scenario']=='改变模型回答' or result.get('config',{}).get('answer_artifacts_version')==2:
            info=result.get('post_clipboard',{})
            if not verified_post_screenshot_fallback(raw,info):
                if info.get('status')!='copied' or info.get('source') not in ('native_Gemini_copy_button','android_text_selection_select_all_copy') or not (raw/'post_response_clipboard.md').is_file():return False
                if not (raw/'post_response_clipboard.md').read_bytes().strip():return False
                if sha(raw/'post_response_clipboard.md')!=info.get('sha256'):return False
        if source['scenario']!='改变模型回答' and source.get('source_schema')=='formal_ABCDE':
            if result.get('config',{}).get('p1_tool_capture'):
                from p1_file_upload.tool_capture import verified_tool_capture
                return verified_tool_capture(result,raw)
            from p1_file_upload.tool_pilot import verified_tool_evidence
            return verified_tool_evidence(result,raw)
        return True
    except (OSError,ValueError,KeyError,TypeError,AttributeError,LabError):return False


def _complete_p2(path, result, raw):
    from p2_screen_pdf.runner import SCREEN_PROMPT
    from .gemini_controller import response_service_error_text,response_status_text
    source = result['source']
    protocol = result.get('p2_protocol', {})
    if protocol.get('collection_version')==2:
        from .ui import png_ok
        if result.get('config',{}).get('p2_recovery_version') in (1,2):
            from p2_screen_pdf.recovery import source_binding_valid
            from p2_screen_pdf.runner import COLLECTION_PROTOCOL
            if (protocol.get('protocol_version') != COLLECTION_PROTOCOL
                    or not source_binding_valid(result,raw)):
                return False
            for source_name,alias in [('baseline.png','01-前测.png'),('gemini_response.png','02-读屏回答.png'),('post.png','03-后测.png')]:
                if sha(raw/source_name) != sha(raw/alias):return False
        if not (result.get('status')=='complete' and result.get('p2_cycle_complete') and result.get('note_editor_exact') and result.get('note_gray')==248 and result.get('screen_context_route')=='direct_assistant_text_no_attachment'):return False
        for label in ('baseline','injection','post'):
            if result.get('submissions',{}).get(label)!='response_sampled_unverified' or not result.get(label+'_response',{}).get('response_seen'):return False
            if response_service_error_text((raw/(label+'_response_visible.txt')).read_text()):return False
            if response_status_text((raw/(label+'_response_visible.txt')).read_text()):return False
        for name,text in [('actual_baseline_prompt.txt',source['user_prompt']),('actual_attacker_prompt.txt',source['attacker_prompt']),('actual_screen_prompt.txt',SCREEN_PROMPT),('actual_post_prompt.txt',source['verification_prompt'])]:
            if (raw/name).read_text()!=text:return False
        for name in ['baseline.png','gemini_response.png','post.png','note_screen_248.png','screen_context.png']:
            if not png_ok((raw/name).read_bytes()):return False
        if source['scenario']!='改变模型回答':
            from p2_screen_pdf.tool_runner import verified_p2_tool_capture
            if not verified_p2_tool_capture(result,raw):return False
        if result.get('config',{}).get('p2_post_save_version')==1 and not result.get('post_capture'):return False
        if result.get('post_capture'):
            from p2_screen_pdf.post_capture import post_artifacts_valid
            if not post_artifacts_valid(result,raw):return False
        verify_run(path);return True
    if not (result.get('status') == 'complete' and result.get('p2_cycle_complete')
            and source['scenario'] == '改变模型回答' and source['source_schema'] == 'formal_ABCDE'
            and protocol.get('post') == 'xlsx_D' and result.get('screen_source') == 'screen_note_app'
            and result.get('note_gray') == 248 and result.get('note_editor_exact') is True
            and result.get('p2_baseline_check', {}).get('status') == 'passed'):
        return False
    if any(result.get('submissions', {}).get(k) != 'response_observed'
           for k in ('baseline', 'injection', 'post')):
        return False
    wait = result.get('injection_wait', {})
    if (wait.get('status') != 'completed' or wait.get('remaining_seconds') != 0
            or wait.get('elapsed_active_seconds', -1) < wait.get('requested_seconds', 0)):
        return False
    for name, text in [('actual_baseline_prompt.txt', source['user_prompt']),
                       ('actual_attacker_prompt.txt', source['attacker_prompt']),
                       ('actual_screen_prompt.txt', SCREEN_PROMPT),
                       ('actual_post_prompt.txt', source['verification_prompt'])]:
        if (raw / name).read_bytes() != text.encode():
            return False
    if any(not (raw / (name + '.png')).is_file() for name in
           ('baseline', 'note_config_248', 'note_screen_248', 'screen_context', 'gemini_response', 'post')):
        return False
    md = raw / 'post_response_clipboard.md'
    copy = result.get('post_clipboard', {})
    if (copy.get('status') != 'copied' or copy.get('source') not in ('native_Gemini_copy_button','android_text_selection_select_all_copy')
            or not md.read_bytes().strip() or sha(md) != copy.get('sha256')):
        return False
    verify_run(path)
    return True


def p2_pending(cases, entries, selected=None):
    from p2_screen_pdf.tool_runner import p2_supported
    return [(i, c) for i, c in enumerate(cases)
            if (selected is None or i == selected) and c.source_schema == 'formal_ABCDE'
            and p2_supported(c) and not ProgressStore.checked(entries.get(c.case_id, {}))]


class ProgressStore:
    def __init__(self,state_dir,workbook_hash,pathway='p1',*,round_dir=None,protocol_version=None):
        self.round_dir=Path(round_dir).resolve() if round_dir is not None else None
        self.protocol_version=protocol_version
        identity=pathway+'|'+workbook_hash
        if self.round_dir is not None:identity+='|'+str(self.round_dir)
        if protocol_version is not None:identity+='|protocol='+protocol_version
        key=hashlib.sha256(identity.encode()).hexdigest()[:24]
        self.path=Path(state_dir)/'progress'/(key+'.json')
        self.workbook_hash=workbook_hash;self.pathway=pathway

    def read(self):
        if not self.path.exists():
            data={'workbook_sha256':self.workbook_hash,'pathway':self.pathway,'cases':{}}
            if self.round_dir is not None:data['round_dir']=str(self.round_dir)
            if self.protocol_version is not None:data['protocol_version']=self.protocol_version
            return data
        return json.loads(self.path.read_text())

    @contextmanager
    def edit(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.with_suffix('.lock').open('a+') as fd:
            fcntl.flock(fd,fcntl.LOCK_EX)
            data=self.read();yield data;atomic_json(self.path,data)

    @staticmethod
    def checked(entry):
        manual=entry.get('manual')
        return bool(entry.get('auto_complete')) if manual is None else bool(manual)

    def record(self,case,run_dir,stage,status='running',allow_auto=False,reset_manual=True,only_if_newer=False):
        from .p2_archive import resolve_run,round_for
        run_dir=str(resolve_run(run_dir))
        actual_round=round_for(run_dir) if self.pathway=='p2' else Path(run_dir).parent
        if self.round_dir is not None and actual_round!=self.round_dir:
            raise LabError('运行证据与进度轮次不一致')
        if self.protocol_version is not None:
            current=read_run(run_dir)[0]
            if (current.get('pathway')!=self.pathway or current.get('config',{}).get('p2_protocol_version')!=self.protocol_version
                    or current.get('source',{}).get('workbook_sha256')!=self.workbook_hash):
                raise LabError('运行证据与冻结协议/源表不一致')
        verified=allow_auto and complete_run(run_dir)
        try:
            current=read_run(run_dir)[0];remaining=current.get('injection_wait',{}).get('remaining_seconds');created=current.get('created','')
        except (OSError,ValueError,LabError):remaining=None;created='';current={}
        with self.edit() as data:
            entry=data['cases'].setdefault(case.case_id,{})
            if only_if_newer and entry.get('run_created','')>=created:return False
            old_auto=entry.get('auto_run')
            entry.update(case_id=case.case_id,scenario=case.scenario,row=case.row,
                         run_dir=run_dir,stage=stage,status=status,run_created=created,remaining_seconds=remaining,updated=utc())
            if current.get('p2_tool_route'):
                entry['tool_invocation_status']=current['p2_tool_route'].get('invocation_status','pending')
            if current.get('post_capture'):
                entry['post_capture_status']=current['post_capture'].get('status','unconfirmed')
            if verified:
                entry.update(auto_complete=True,auto_run=run_dir)
                if reset_manual and old_auto!=run_dir:entry['manual']=None
            data['latest_run']=run_dir
        return True

    def mark_manual(self,case,checked,note):
        if not note.strip():raise LabError('人工登记需要完整流程确认说明')
        with self.edit() as data:
            entry=data['cases'].setdefault(case.case_id,{})
            entry.update(case_id=case.case_id,scenario=case.scenario,row=case.row,
                         manual=bool(checked),manual_note=note,manual_time=utc())
            entry.setdefault('manual_history',[]).append({'checked':bool(checked),'note':note,'time':utc()})
            if checked:entry['operator_closed_run']=entry.get('run_dir')
            else:entry.pop('operator_closed_run',None)

    def abandon_run(self,case_id,run_dir):
        with self.edit() as data:
            entry=data['cases'].setdefault(case_id,{})
            entry['operator_closed_run']=str(Path(run_dir).resolve())

    def import_run(self,path):
        from .p2_archive import resolve_run,round_for
        path=resolve_run(path)
        actual_round=round_for(path) if self.pathway=='p2' else path.parent
        if self.round_dir is not None and actual_round!=self.round_dir:return False
        result,_=read_run(path)
        if self.protocol_version is not None and result.get('config',{}).get('p2_protocol_version')!=self.protocol_version:return False
        if result.get('pathway')!=self.pathway or result.get('source',{}).get('workbook_sha256')!=self.workbook_hash:
            return False
        if self.pathway == 'p2':
            from .tool_capture import tool_capture_spec
            from types import SimpleNamespace
            if result.get('config', {}).get('screen_source', 'note') != 'note':
                return False
            if result['source'].get('scenario')!='改变模型回答' and (not tool_capture_spec(SimpleNamespace(**result['source'])) or result.get('config',{}).get('p2_tool_capture')!=1):return False
            if not result.get('p2_protocol') and 'p2_post_wait_seconds' not in result.get('config', {}):
                return False  # Older read-screen-only runs are not queue entries.
        else:
            protocol=result.get('p1_protocol',{})
            if protocol.get('post_prompt_source')!='xlsx_D' and result.get('config',{}).get('p1_cycle_version')!=1:return False
        from .case_loader import Case
        source=result['source'];case=Case(**{k:v for k,v in source.items() if k in Case.__dataclass_fields__})
        entry=self.read()['cases'].get(case.case_id,{})
        stage=result.get('interrupted_phase',result.get('phase','unknown'));status=result.get('status','unknown')
        if entry.get('run_dir')==str(Path(path).resolve()):
            if entry.get('status')==status and (status!='complete' or entry.get('auto_complete')):return False
            return self.record(case,path,stage,status,allow_auto=True,reset_manual=False)
        # Do not let an older disk scan replace a newer active/failed continuation.
        if entry.get('run_dir'):
            try:prior,_=read_run(entry['run_dir'])
            except (OSError,ValueError,LabError):return False
            if prior.get('created','')>=result.get('created',''):return False
        return self.record(case,path,stage,status,allow_auto=True,reset_manual=False,only_if_newer=True)

    def recheck_p2(self):
        """Clear cached completion only when the previously verified evidence no longer verifies."""
        if self.pathway != 'p2' or not self.path.exists():
            return
        snapshot = self.read()['cases']
        invalid = {key: value.get('auto_run') for key, value in snapshot.items()
                   if value.get('auto_complete') and not complete_run(value.get('auto_run') or '')}
        if not invalid:
            return
        with self.edit() as data:
            for key, run in invalid.items():
                entry = data['cases'].get(key, {})
                if entry.get('auto_run') == run:
                    entry.update(auto_complete=False, status='needs_attention', stage='evidence_recheck_failed')
                    entry.pop('auto_run', None)

    def retry_candidate(self,cases):
        """Explicit user resume includes deferred archive entries; passive lookup does not."""
        from .evidence import p1_recovery_round
        entries=self.read()['cases']
        for case in sorted(cases,key=lambda c:c.row):
            entry=entries.get(case.case_id,{})
            if case.row==36 or self.checked(entry) or not entry.get('run_dir'):continue
            try:
                path=latest_continuation(entry['run_dir'])
                result,_=read_run(path)
                if (result.get('pathway')!='p1' or result.get('case_id')!=case.case_id
                        or result.get('source',{}).get('workbook_sha256')!=self.workbook_hash
                        or result.get('status') in ('complete','manual_snapshot_only')):continue
                if self.round_dir is not None and p1_recovery_round(self.round_dir.parents[1],path)!=self.round_dir:continue
                verify_run(path)
            except (OSError,ValueError,LabError):continue
            return {**entry,'run_dir':str(path)}
        return None

    def latest_unfinished(self,cases):
        ids={c.case_id for c in cases}
        entries=[v for k,v in self.read()['cases'].items() if k in ids and v.get('run_dir')
                 and v.get('status') not in ('complete','manual_snapshot_only')
                 and v.get('operator_closed_run')!=v.get('run_dir')]
        entries.sort(key=lambda v:(v.get('run_created',''),v.get('updated','')),reverse=True)
        for entry in entries:
            if self.pathway!='p1':return entry
            try:
                latest=latest_continuation(entry['run_dir'])
                result,_=read_run(latest)
            except (OSError, ValueError, LabError):
                # Missing/broken evidence is not a resumable suggestion. The device
                # lease remains separate and still blocks uncertain submissions.
                continue
            if result.get('status') in ('complete','manual_snapshot_only'):
                continue
            if self.round_dir is not None and latest.parent!=self.round_dir:
                continue
            if str(latest)!=entry['run_dir']:
                entry={**entry,'run_dir':str(latest),
                       'stage':result.get('interrupted_phase') or result.get('active_stage') or result.get('phase'),
                       'remaining_seconds':result.get('injection_wait',{}).get('remaining_seconds')}
            return entry
        return None
