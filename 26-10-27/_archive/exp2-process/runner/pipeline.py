#!/usr/bin/env python3
"""Config-driven Android screen transcription experiments; no live actions without --execute."""
from __future__ import annotations
import argparse, binascii, contextlib, datetime as dt, fcntl, hashlib, json, math, os
from pathlib import Path
import re, shlex, shutil, stat, struct, subprocess, sys, tempfile, time, uuid, zipfile
import xml.etree.ElementTree as ET

SKILL = 'android-screen-readability'
APP = 'ai.perplexity.app.android'
SCRIPT_DIR = Path(__file__).resolve().parent


class PipelineError(RuntimeError): pass


def require(condition, message):
    if not condition: raise PipelineError(message)


def digest(data): return hashlib.sha256(data).hexdigest()
def file_hash(p): return digest(Path(p).read_bytes())
def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()
def read_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))


def value_key(v):
    try:
        number=float(v)
        if math.isfinite(number): return format(number,'.15g')
    except (TypeError,ValueError): pass
    return str(v)


def save_json(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(p)


def png_size(data):
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'Not a PNG screenshot/image')
    pos = 8; size = None; ended = False
    while pos + 12 <= len(data):
        n = struct.unpack('>I', data[pos:pos+4])[0]; kind = data[pos+4:pos+8]
        body = data[pos+8:pos+8+n]; crc = data[pos+8+n:pos+12+n]
        require(len(body) == n and len(crc) == 4, 'Truncated PNG')
        require(binascii.crc32(kind + body) & 0xffffffff == struct.unpack('>I', crc)[0], 'PNG CRC mismatch')
        if kind == b'IHDR': size = struct.unpack('>II', body[:8])
        pos += n + 12
        if kind == b'IEND': ended = True; break
    require(size is not None and ended, 'Incomplete PNG')
    return size


def score(reference, response, whitespace='ignore'):
    """Minimum edits, then maximum exact matches. None is an unmatchable [UNK] token."""
    def clean(s):
        if whitespace == 'ignore': return re.sub(r'\s+', '', s)
        if whitespace == 'linebreaks-only': return s.replace('\r', '').replace('\n', '')
        require(whitespace == 'preserve', 'Unknown whitespace policy'); return s
    expected = list(clean(reference)); require(expected, 'Empty reference')
    predicted = []
    if response.strip() != '[UNREADABLE]':
        for part in re.split(r'(\[UNK\])', response):
            predicted.extend([None] if part == '[UNK]' else list(clean(part)))
    # (edit distance, negative exact matches, substitutions, deletions, insertions)
    prev = [(j, 0, 0, 0, j) for j in range(len(predicted)+1)]
    for i, a in enumerate(expected, 1):
        now = [(i, 0, 0, i, 0)]
        for j, b in enumerate(predicted, 1):
            c, m, s, d, ins = prev[j-1]; same = a == b
            candidates = [(c + int(not same), m-int(same), s+int(not same), d, ins)]
            c, m, s, d, ins = prev[j]; candidates.append((c+1, m, s, d+1, ins))
            c, m, s, d, ins = now[-1]; candidates.append((c+1, m, s, d, ins+1))
            now.append(min(candidates))
        prev = now
    edits, negative_matches, s, d, ins = prev[-1]; total = len(expected)
    return dict(correct=-negative_matches, substitutions=s, deletions=d, insertions=ins,
                edit_distance=edits, total=total, accuracy=-negative_matches/total, cer=edits/total,
                unk_tokens=response.count('[UNK]'), unreadable=response.strip() == '[UNREADABLE]',
                exact_transcription=response.strip('\r\n') == reference.strip('\r\n'))


class Config:
    def __init__(self, filename):
        self.path = Path(filename).expanduser().resolve(); self.raw = read_json(self.path)
        d = self.raw
        require(d.get('version') == 1, 'Expected config version 1')
        def absolute(key):
            p = Path(d[key]).expanduser(); require(p.is_absolute(), key + ' must be absolute'); return p.resolve()
        self.root = absolute('experiment_dir'); require(self.root.name not in ('', '.', '..'), 'Invalid experiment directory')
        self.reference_path = absolute('reference_file'); self.prompt_path = absolute('prompt_file')
        self.reference = self.reference_path.read_text(encoding='utf-8').strip('\r\n')
        self.prompt = ' '.join(self.prompt_path.read_text(encoding='utf-8').split())
        require(self.prompt and self.prompt.isascii() and '%s' not in self.prompt,
                'v1 input transport requires an ASCII prompt without literal %s; configure another input adapter otherwise')
        self.whitespace = d.get('whitespace', 'ignore'); score(self.reference, '', self.whitespace)
        self.rounds = d['rounds']; self.values = d['values']
        require(self.rounds and all(type(n) is int and n > 0 for n in self.rounds) and len(set(self.rounds)) == len(self.rounds), 'rounds must be distinct positive integers')
        require(self.values and len({value_key(v) for v in self.values}) == len(self.values), 'values must be nonempty and distinct')
        require(all(type(v) in (str,int,float) and (not isinstance(v,float) or math.isfinite(v)) for v in self.values), 'values must be finite scalars')
        for v in self.values: require(re.fullmatch(r'[A-Za-z0-9_.-]+', str(v)) and '..' not in str(v), 'Unsafe case ID')
        self.stem = d.get('artifact_stem', 'exp1'); require(re.fullmatch(r'[A-Za-z0-9_-]+', self.stem), 'Unsafe artifact_stem')
        self.conditions = d.get('conditions', {})
        if self.conditions:
            require(all(str(v) in self.conditions for v in self.values), 'Missing two-dimensional condition')
            pairs=[(self.conditions[str(v)]['font_px'],self.conditions[str(v)]['delta_g']) for v in self.values]
            require(len(set(pairs))==len(pairs), 'Duplicate font/gray condition')
            require(all(type(f) is int and type(g) is int and f>0 and 1<=g<=32 for f,g in pairs), 'Invalid font/gray condition')
        self.parameter_key = d.get('parameter_key', 'gray'); self.label = d.get('parameter_label', '名义灰度')
        self.serial = d['serial']; require(isinstance(self.serial, str) and self.serial, 'Explicit device serial required')
        require(d.get('adapter') == 'perplexity-default-assistant-v1', 'Unsupported adapter; preserve requested App and add/validate its UI adapter first')
        self.app = d.get('assistant_package', APP); require(self.app == APP, 'Perplexity adapter cannot silently substitute for a different App')
        self.ui = d['ui']; self.screen = tuple(self.ui['screen_size']); self.image_size = tuple(d['image_size'])
        require(len(self.screen) == len(self.image_size) == 2, 'Expected width/height pairs')
        for name in ('keyboard_tap', 'gallery_tap'):
            x, y = self.ui[name]; require(0 <= x < self.screen[0] and 0 <= y < self.screen[1], name + ' outside validated viewport')
        require(type(self.ui['validated_version_code']) is int, 'Pin a visually validated App version before using coordinate entry')
        self.brightness = d.get('brightness', {'action': 'preserve'})
        require(self.brightness['action'] in ('preserve', 'manual'), 'Brightness action must be preserve or manual')
        if self.brightness['action'] == 'manual': require(type(self.brightness['value']) is int and 0 <= self.brightness['value'] <= 255, 'Brightness value out of range')
        self.archive_root = self.root.parent / '_archive'
        slug = re.sub(r'[^\w.-]', '_', self.root.name)
        self.work = self.archive_root / ('.' + slug + '-screen-readability-work')
        self.timeout = float(d.get('response_timeout_s', 180)); self.poll_s = float(d.get('poll_s', 4))
        require(self.timeout > 0 and self.poll_s >= 0, 'Invalid polling/timeout')
        for v in self.values:
            require(self.image(v).is_absolute(), 'image_pattern must resolve to an absolute path')
            phone = self.phone(v); require(phone.startswith('/sdcard/') and '..' not in Path(phone).parts, 'phone_image_pattern must stay under /sdcard')
    def image(self, v): return Path(self.raw['image_pattern'].format(value=v, id=str(v))).expanduser()
    def phone(self, v): return self.raw['phone_image_pattern'].format(value=v, id=str(v))
    def evidence(self, n): return self.root / f'evidence-{n:02d}'
    def record(self, n, v): return self.evidence(n) / 'records' / f'{self.stem}-result-{v}.json'
    def identity(self, v):
        return dict(source_sha256=file_hash(self.image(v)), reference_sha256=digest(self.reference.encode()),
                    prompt_sha256=digest(self.prompt.encode()), parameter_key=self.parameter_key,
                    assistant_package=self.app, device=self.serial)


class Device:
    def __init__(self, config): self.c = config
    def adb(self, *args, timeout=40):
        return subprocess.check_output(['adb', '-s', self.c.serial, *map(str, args)], stderr=subprocess.STDOUT, timeout=timeout)
    def shell(self, *args, timeout=40): return self.adb('shell', ' '.join(shlex.quote(str(x)) for x in args), timeout=timeout).decode()
    def brightness(self):
        return dict(mode=int(self.shell('settings', 'get', 'system', 'screen_brightness_mode').strip()),
                    value=int(self.shell('settings', 'get', 'system', 'screen_brightness').strip()))
    def preflight(self):
        require(self.adb('get-state').decode().strip() == 'device', 'Device not ready')
        role = self.shell('cmd', 'role', 'get-role-holders', 'android.app.role.ASSISTANT').strip()
        require(role == self.c.app, 'Default assistant differs; do not change the role automatically')
        size = re.findall(r'(?:Physical|Override) size:\s*(\d+)x(\d+)', self.shell('wm', 'size'))
        require(size and tuple(map(int, size[-1])) == self.c.screen, 'Device viewport differs from the validated tap profile')
        version = re.search(r'versionCode=(\d+)', self.shell('dumpsys', 'package', self.c.app))
        require(version and int(version[1]) == self.c.ui['validated_version_code'], 'App version differs; visually validate the UI profile before updating its version pin')
        return dict(assistant=role, screen=list(self.c.screen), version_code=int(version[1]), brightness=self.brightness())
    def foreground(self):
        text = self.shell('dumpsys', 'activity', 'activities')
        found = re.search(r'(?:topResumedActivity|mResumedActivity).*?\s([\w.]+/[\w.$]+)', text)
        return found[1] if found else ''
    def check_component(self, expected):
        def canonical(s):
            if '/' not in s: return s
            p, a = s.split('/', 1); return p + '/' + (p+a if a.startswith('.') else a)
        require(canonical(self.foreground()) == canonical(expected), 'Unexpected foreground activity; stop before tapping')
    def tap(self, point): self.shell('input', 'tap', *point)
    def tap_node(self, node):
        x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds', '')))
        self.tap(((x1+x2)//2, (y1+y2)//2))
    def dump(self, path):
        remote = '/sdcard/' + SKILL + '-ui.xml'
        output = self.shell('uiautomator', 'dump', remote)
        require('dumped to' in output, 'UI did not become idle; do not reuse a stale dump')
        data = self.adb('exec-out', 'cat', remote); nodes = list(ET.fromstring(data).iter('node'))
        Path(path).write_bytes(data); return nodes
    def shot(self, path):
        data = self.adb('exec-out', 'screencap', '-p'); require(png_size(data) == self.c.screen, 'Unexpected screenshot dimensions')
        Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_bytes(data)


def raw_response(c, n, case, record):
    ev = c.evidence(n); p = ev / 'responses' / f'{c.stem}-response-{case}.txt'
    require(p.is_file(), 'Missing response text: ' + str(p)); text = p.read_text(encoding='utf-8').removesuffix('\n')
    require(text == record['response'], 'Record/raw response mismatch: ' + str(p)); return text


def validate_existing(c, n, v):
    p = c.record(n, v)
    if not p.exists(): return False
    d = read_json(p); require(d.get('status') == 'completed', 'Existing incomplete result; inspect it instead of overwriting')
    raw_response(c, n, str(v), d)
    if c.conditions:
        for key in ('font_px','delta_g'):require(d.get(key)==c.conditions[str(v)][key], 'Two-dimensional condition changed')
    require(d.get('source_sha256') == file_hash(c.image(v)), 'Input image changed since this trial; use a new round/case, never overwrite history')
    require(d.get('prompt_sent') == c.prompt, 'Prompt changed since this trial; use a separate protocol/round')
    if 'reference_sha256' in d: require(d['reference_sha256'] == digest(c.reference.encode()), 'Reference changed')
    if 'parameter_key' in d: require(d['parameter_key'] == c.parameter_key, 'Parameter type changed')
    else: require('grey' in d and c.parameter_key == 'gray', 'Legacy records require explicit schema adaptation')
    for folder, name in [('screenshots', f'{c.stem}-screenshot-{v}.png'), ('source-screens', f'g{v}-source-clean.png')]:
        require(png_size((c.evidence(n)/folder/name).read_bytes()) == c.screen, 'Missing/corrupt existing evidence')
    return True


def validate_round_protocol(c,n):
    for path in (c.evidence(n)/'records').glob(c.stem+'-result-*.json'):
        d=read_json(path)
        key=d.get('parameter_key','gray' if 'grey' in d else None)
        require(key==c.parameter_key,'Parameter type differs from prior trials in this round; use a separate experiment/protocol')
        if 'reference_sha256' in d:require(d['reference_sha256']==digest(c.reference.encode()),'Mixed references in one round')
        if 'prompt_sent' in d:require(d['prompt_sent']==c.prompt,'Prompt differs from prior trials in this round; use a separate protocol')


def plan(c):
    result = []
    for n in c.rounds:
        validate_round_protocol(c,n)
        for v in c.values:
            require(c.image(v).is_file(), 'Missing source: ' + str(c.image(v)))
            require(png_size(c.image(v).read_bytes()) == c.image_size, 'Wrong source dimensions')
            result.append(dict(round=n, value=v, status='completed' if validate_existing(c,n,v) else 'pending'))
    return dict(jobs=result, total=len(result), pending=sum(x['status']=='pending' for x in result), side_effects=False)


def preflight(c, device=None):
    planned=plan(c);device=device or Device(c);environment=device.preflight();inputs=[]
    for v in c.values:
        actual=device.shell('sha256sum',c.phone(v)).split()[0]
        require(actual==file_hash(c.image(v)),'Phone input missing/different: '+c.phone(v))
        inputs.append(dict(value=v,hash_match=True))
    current=environment['brightness'];target=c.brightness
    change=target['action']=='manual' and current!={'mode':0,'value':target['value']}
    return dict(plan=planned,device=environment,phone_inputs=inputs,settings_change_required=change,side_effects=False)


def work_dir(c):
    c.archive_root.mkdir(parents=True, exist_ok=True)
    owner = c.work/'owner.json'
    if c.work.exists():
        require(owner.is_file() and read_json(owner).get('experiment_dir') == str(c.root) and read_json(owner).get('skill') == SKILL,
                'Existing work directory is not owned by this pipeline')
    else:
        c.work.mkdir(); save_json(owner, dict(skill=SKILL, experiment_dir=str(c.root), created_utc=utc(),
            archive_name=c.root.name+'-pipeline-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]+'.zip'))
    return c.work


@contextlib.contextmanager
def locked(c):
    work_dir(c)
    with (c.work/'run.lock').open('a') as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise PipelineError('Another runner holds this experiment lock; poll its live process instead of restarting')
        try: yield
        finally: fcntl.flock(handle, fcntl.LOCK_UN)


def observed_brightness(c, device):
    b = device.brightness()
    if c.brightness['action'] == 'manual': require(b == {'mode':0,'value':c.brightness['value']}, 'Brightness changed during the trial')
    return b


def protocol_snapshot(c):
    value=dict(config=c.raw,reference=c.reference,prompt_sent=c.prompt,
               prompt_source=c.prompt_path.read_text(encoding='utf-8'),whitespace=c.whitespace)
    key=digest(json.dumps(value,ensure_ascii=False,sort_keys=True).encode())
    target=c.work/'protocols'/(key+'.json')
    if target.exists():require(read_json(target)==value,'Protocol snapshot changed')
    else:save_json(target,value)
    return str(target.relative_to(c.work))


def run_trial(c, device, n, v):
    if validate_existing(c,n,v): return {'round':n,'value':v,'status':'verified-existing'}
    d = c.work/f'round{n:02d}'/f'g{v}'; state_path = d/'state.json'
    require(not state_path.exists(), 'An unfinished attempt exists. Inspect its live process/UI first; never blindly resubmit. Preserve uncertain evidence under excluded/')
    for folder in ('screenshots','responses','source-screens','records','excluded'): (c.evidence(n)/folder).mkdir(parents=True,exist_ok=True)
    d.mkdir(parents=True)
    state = dict(round=n, value=v, identity=c.identity(v), started_utc=utc(), submitted=False, phase='setup',protocol_archive_member=protocol_snapshot(c))
    def phase(value): state['phase']=value;state['updated_utc']=utc();save_json(state_path,state)
    phase('setup')
    try:
        brightness = observed_brightness(c,device)
        remote = c.phone(v); phone_sha=device.shell('sha256sum',remote).split()[0]
        require(phone_sha == state['identity']['source_sha256'], 'Phone input hash differs; import/verify the image first')
        device.shell('am','force-stop',c.app); gallery=c.raw['gallery_component']
        device.shell('am','force-stop',gallery.split('/')[0])
        phone_name=Path(remote).name.replace("'","''"); relative=str(Path(remote).parent).removeprefix('/sdcard/').rstrip('/')+'/'
        where=f"_display_name='{phone_name}' AND relative_path='{relative.replace(chr(39),chr(39)*2)}'"
        query=device.shell('content','query','--uri','content://media/external/images/media','--projection','_id:_display_name:relative_path','--where',where)
        (d/'source-query.txt').write_text(query);ids=re.findall(r'_id=(\d+)',query);require(len(ids)==1,'MediaStore image missing or ambiguous')
        device.shell('am','start','-W','-a','android.intent.action.VIEW','-d','content://media/external/images/media/'+ids[0],'-t','image/png','-n',gallery,'--grant-read-uri-permission')
        device.check_component(gallery); nodes=device.dump(d/'source-initial.xml')
        if any(x.get('text') or x.get('content-desc')=='分享' for x in nodes): device.tap(c.ui['gallery_tap']);time.sleep(1)
        nodes=device.dump(d/'source-clean.xml');require(not any(x.get('text') for x in nodes),'Gallery controls remain visible')
        source_screen=c.evidence(n)/'source-screens'/f'g{v}-source-clean.png';time.sleep(1);device.shot(source_screen)
        phase('source-ready');device.shell('input','keyevent','219');time.sleep(float(c.ui.get('assistant_settle_s',3)))
        device.check_component(c.ui['assistant_activity']);device.tap(c.ui['keyboard_tap'])
        nodes=device.dump(d/'input.xml');edits=[x for x in nodes if x.get('class')=='android.widget.EditText']
        require(len(edits)==1 and not edits[0].get('text'),'Not a fresh empty assistant input')
        device.shell('input','text',c.prompt.replace(' ','%s'))
        nodes=device.dump(d/'prompt.xml');edits=[x for x in nodes if x.get('class')=='android.widget.EditText']
        require(len(edits)==1 and edits[0].get('text')==c.prompt,'Prompt differs (possibly Chinese IME); correct the unsent input and preserve this attempt before retrying')
        send=[x for x in nodes if x.get('content-desc')==c.ui['send_desc']];require(len(send)==1,'Send control missing/ambiguous')
        device.shot(d/'prompt.png');phase('prompt-verified')
        state['submitted']=True;phase('submitting');device.tap_node(send[0]);phase('awaiting-answer')
        deadline=time.monotonic()+c.timeout;previous=None;stable=0
        while time.monotonic()<deadline:
            time.sleep(c.poll_s);nodes=device.dump(d/'answer.xml')
            text='\n'.join(x.get('text') for x in nodes if x.get('class')=='android.widget.TextView' and x.get('text'))
            thinking=any(any(token in x.get('content-desc','') for token in c.ui['thinking_contains']) for x in nodes)
            complete=any(x.get('content-desc')==c.ui['copy_desc'] for x in nodes) and not thinking
            stable=stable+1 if text and text==previous else 0;previous=text
            if complete and stable>=1: break
        else: phase('timeout');raise PipelineError('Response timeout; preserve as uncertain, not [UNREADABLE]')
        shot=c.evidence(n)/'screenshots'/f'{c.stem}-screenshot-{v}.png';device.shot(shot)
        response_file=c.evidence(n)/'responses'/f'{c.stem}-response-{v}.txt';response_file.write_text(text+'\n',encoding='utf-8')
        after=observed_brightness(c,device);owner=read_json(c.work/'owner.json')
        label='最大亮度' if brightness=={'mode':0,'value':255} else f"设置值{brightness['value']}（模式{brightness['mode']}）"
        record=dict(round=n,repeat=n,case_id=str(v),parameter_value=v,status='completed',
            started_utc=state['started_utc'],completed_utc=utc(),**state['identity'],prompt_sent=c.prompt,
            phone_source_sha256=phone_sha,
            prompt_transport='ASCII; paragraph whitespace collapsed and UI-verified',
            image=c.image(v).name,image_size=list(c.image_size),font_px=c.conditions.get(str(v),{}).get('font_px',c.raw.get('font_px')),
            delta_g=c.conditions.get(str(v),{}).get('delta_g',v if c.parameter_key=='gray' else None),
            screen_brightness_mode=brightness['mode'],screen_brightness=brightness['value'],brightness_after=after,brightness_label=label,
            response=text,response_file=str(response_file.relative_to(c.evidence(n))),screenshot=str(shot.relative_to(c.evidence(n))),
            source_screen=str(source_screen.relative_to(c.evidence(n))),source_rgb_gate='not_used',
            ui_archive=os.path.relpath(c.archive_root/owner['archive_name'],c.root),
            protocol_archive_member=state['protocol_archive_member'],
            answer_xml_archive_member=str((d/'answer.xml').relative_to(c.work)),prompt_xml_archive_member=str((d/'prompt.xml').relative_to(c.work)),
            response_sha256=file_hash(response_file),screenshot_sha256=file_hash(shot),source_screen_sha256=file_hash(source_screen),
            **score(c.reference,text,c.whitespace))
        require(not c.record(n,v).exists(),'Result already exists; concurrent write detected');save_json(c.record(n,v),record);phase('completed')
        return dict(round=n,value=v,status='completed',correct=record['correct'],total=record['total'])
    except BaseException as error:
        state['error']=type(error).__name__+': '+str(error);state['updated_utc']=utc();save_json(state_path,state)
        try: device.shot(d/'failure-current.png')
        except Exception: pass
        raise


def run(c, device=None):
    planned=plan(c)
    if not planned['pending']:
        result=[dict(round=j['round'],value=j['value'],status='verified-existing') for j in planned['jobs']]
        return result
    device=device or Device(c);preflight(c,device)
    with locked(c):
        save_json(c.work/'config.json',c.raw);(c.work/'reference.txt').write_text(c.reference);(c.work/'prompt.txt').write_text(c.prompt)
        if c.brightness['action']=='manual':
            device.shell('settings','put','system','screen_brightness_mode','0');device.shell('settings','put','system','screen_brightness',c.brightness['value'])
        results=[]
        for n in c.rounds:
            for v in c.values:
                result=run_trial(c,device,n,v);results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
        return results


def scored_data(c):
    rounds=[]
    for n in c.rounds:
        validate_round_protocol(c,n)
        require(all(c.record(n,v).exists() for v in c.values),'Requested trials are incomplete; do not publish a completed report')
        rows=[]
        for p in (c.evidence(n)/'records').glob(c.stem+'-result-*.json'):
            d=read_json(p);case=d.get('case_id',str(d.get('grey',p.stem.removeprefix(c.stem+'-result-'))))
            require(d.get('status')=='completed','Incomplete record in formal records/')
            if 'reference_sha256' in d: require(d['reference_sha256']==digest(c.reference.encode()),'Mixed references; use per-protocol reports rather than re-score old trials silently')
            text=raw_response(c,n,case,d)
            label=d.get('brightness_label') or ('最大亮度' if d.get('screen_brightness')==255 and d.get('screen_brightness_mode')==0 else c.raw.get('legacy_condition_label','历史记录'))
            rows.append(dict(font_px=d.get('font_px'),delta_g=d.get('delta_g'),round=n,case_id=case,value=d.get('parameter_value',d.get('grey',case)),response=text,
                screenshot=f'{c.stem}-screenshot-{case}.png',brightness_label=label,**score(c.reference,text,c.whitespace)))
        def key(row):
            try:return (0,float(row['value']))
            except (ValueError,TypeError):return (1,str(row['value']))
        rows.sort(key=key);require(len({value_key(x['value']) for x in rows})==len(rows),'Duplicate parameter values in a round')
        total=sum(x['correct'] for x in rows);denominator=sum(x['total'] for x in rows);mean=total/denominator
        sd=math.sqrt(sum((x['accuracy']-mean)**2 for x in rows)/(len(rows)-1)) if len(rows)>1 else None
        rounds.append(dict(round=n,rows=rows,total_correct=total,total_characters=denominator,mean_accuracy=mean,sample_sd=sd))
    return dict(title=c.raw.get('title','屏幕识读实验'),date=c.raw.get('date',''),parameter_label=c.label,
        reference=c.reference,reference_total=score(c.reference,'',c.whitespace)['total'],root=str(c.root),rounds=rounds,
        has_conditions=bool(c.conditions),context=c.raw.get('report_context',''),condition_note=c.raw.get('condition_note','以逐轮记录的条件为准；历史确认不替代机器采集日志。'))


def read_xlsx(p):
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(p) as z:
        require(z.testzip() is None,'Corrupt XLSX')
        ss=[''.join(t.text or '' for t in x.findall('.//m:t',ns)) for x in ET.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
        output=[]
        for name in ('xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml'):
            cells={}
            for cell in ET.fromstring(z.read(name)).findall('.//m:c',ns):
                v=cell.find('m:v',ns);s=v.text if v is not None and v.text else '';f=cell.find('m:f',ns)
                if cell.get('t')=='s':s=ss[int(s)]
                elif cell.get('t')=='inlineStr':s=''.join(t.text or '' for t in cell.findall('.//m:t',ns))
                cells[cell.get('r')]=(s,f.text if f is not None else None)
            output.append(cells)
        tables=[x for x in z.namelist() if x.startswith('xl/tables/') and x.endswith('.xml')]
        require(len(tables)==1,'Expected one results table; adapt the report template before editing')
        ref=ET.fromstring(z.read(tables[0])).get('ref','');match=re.fullmatch(r'A9:(?:I|M)(\d+)',ref)
        require(match,'Unsupported workbook layout; preserve it and adapt the report code first')
        return output,int(match[1])-9


def report(c,node,modules,output_dir=None):
    out=Path(output_dir).resolve() if output_dir else c.root
    require(Path(node).is_file() and Path(modules,'@oai','artifact-tool').is_dir(),'Use the bundled Node and node_modules returned by load_workspace_dependencies')
    with locked(c):
        data=scored_data(c)
        data['output_dir']=str(out)
        for row in data['rounds']:
            template=c.root/f"实验结果-{row['round']:02d}.xlsx"
            if template.exists(): _,row['existing_rows']=read_xlsx(template);row['template']=str(template)
            else: row['existing_rows']=0;row['template']=None
            target=out/template.name
            if target.exists():
                backup=c.work/'report-backups'/template.name;backup.parent.mkdir(exist_ok=True)
                ledger=c.work/'report-output-hashes.json'
                generated=read_json(ledger).get(str(target)) if ledger.exists() else None
                require(not backup.exists() or file_hash(target) in (file_hash(backup),generated),
                        'Report changed outside this pipeline; inspect before overwriting')
                if not backup.exists():shutil.copy2(target,backup)
        link=c.work/'node_modules'
        if link.is_symlink():require(link.resolve()==Path(modules).resolve(),'Unexpected module symlink')
        else:require(not link.exists(),'Unexpected node_modules directory');link.symlink_to(Path(modules).resolve(),target_is_directory=True)
        shutil.copy2(SCRIPT_DIR/'report.mjs',c.work/'report.mjs');save_json(c.work/'report-data.json',data)
        subprocess.run([str(node),str(c.work/'report.mjs'),str(c.work/'report-data.json')],check=True)
        # Artifact Tool can create inspection sidecars next to the workbook; keep them out of the experiment root.
        for row in data['rounds']:
            side=out/f"实验结果-{row['round']:02d}.xlsx.inspect.ndjson"
            if side.exists():shutil.move(str(side),c.work/f"round{row['round']:02d}-inspect.ndjson")
    return verify_reports(c,out)


def verify_reports(c,output_dir=None):
    data=scored_data(c);out=Path(output_dir).resolve() if output_dir else c.root
    for rd in data['rounds']:
        sheets,count=read_xlsx(out/f"实验结果-{rd['round']:02d}.xlsx");require(count==len(rd['rows']),'Report row count differs')
        main,raw=sheets;by_value={value_key(x['value']):x for x in rd['rows']};seen=set()
        for i in range(count):
            row=i+10;key=value_key(main[f'A{row}'][0]);require(key in by_value,'Unexpected case in report');r=by_value[key];seen.add(key)
            if c.conditions:
                for col,name in [('J','font_px'),('K','delta_g'),('L','round')]:require(int(float(main[f'{col}{row}'][0]))==r[name], 'Condition mismatch')
                require(abs(float(main[f'M{row}'][0])-r['cer'])<1e-10, 'CER mismatch')
            for col,name in [('B','correct'),('D','substitutions'),('E','deletions'),('F','insertions'),('G','unk_tokens')]:require(int(float(main[f'{col}{row}'][0]))==r[name],'Score mismatch')
            require(abs(float(main[f'C{row}'][0])-r['accuracy'])<1e-10,'Rate mismatch')
            actual=raw[f'B{i+9}'][0];expected=r['response']
            require(actual==expected or (expected.startswith('=') and actual=="'"+expected),'Full reply mismatch')
            require(raw[f'B{i+9}'][1] is None,'A raw reply became an executable formula')
        require(len(seen)==count,'Duplicate report cases')
        if c.conditions:
            baseline=read_json(c.evidence(1)/'records'/'baseline48-reference.json')['rows']
            require(len(baseline)==96,'Historical baseline must contain 3x32 rows')
            for i,b in enumerate(baseline,9):
                for col,key in [('E','round'),('F','delta_g'),('G','font_px'),('H','correct'),('I','accuracy'),('J','substitutions'),('K','deletions'),('L','insertions'),('M','cer')]:
                    require(abs(float(raw[f'{col}{i}'][0])-b[key])<1e-10,'Historical baseline cell mismatch')
                source=c.root.parent.parent/b['record_path']
                require(file_hash(source)==b['record_sha256'],'Historical baseline source changed')
            for g in range(1,33):
                row=g+9
                require(int(float(main[f'O{row}'][0]))==g,'Comparison gray mismatch')
                expected=sum(b['accuracy'] for b in baseline if b['delta_g']==g)/3
                require(abs(float(main[f'T{row}'][0])-expected)<1e-10,'48px mean mismatch')
                for col,font in [('P',16),('Q',24),('R',32),('S',40),('U',64)]:
                    matches=[r for r in rd['rows'] if r['font_px']==font and r['delta_g']==g]
                    if matches:require(len(matches)==1 and abs(float(main[f'{col}{row}'][0])-matches[0]['accuracy'])<1e-10,'New-font comparison mismatch')
                    else:require(main[f'{col}{row}'][0]=='待测','Missing condition represented as measured data')
        for label,key in [('B4','mean_accuracy')]:require(abs(float(main[label][0])-rd[key])<1e-10,'Summary mismatch')
        require(int(float(main[f'B{count+11}'][0]))==rd['total_correct'],'Total mismatch')
        require(int(float(main['F4'][0]))==count,'Count mismatch')
        if count>1:require(abs(float(main['D4'][0])-rd['sample_sd']*100)<1e-8,'SD mismatch')
        for r in rd['rows']:
            for p in (c.evidence(rd['round'])/'screenshots'/r['screenshot'],c.evidence(rd['round'])/'source-screens'/f"g{r['case_id']}-source-clean.png"):
                require(png_size(p.read_bytes())==c.screen,'Evidence PNG invalid')
    return dict(status='PASS',rounds=len(data['rounds']),rows=sum(len(x['rows']) for x in data['rounds']))


def archive(c):
    verification=verify_reports(c)
    with locked(c):
        owner=read_json(c.work/'owner.json');target=c.archive_root/owner['archive_name'];require(not target.exists(),'Archive already exists')
        # A pending submitted attempt cannot be hidden by cleanup.
        for p in c.work.glob('round*/g*/state.json'):require(read_json(p)['phase']=='completed','Unfinished attempt exists; inspect/preserve it before archiving')
        save_json(c.work/'verification.json',verification)
        files={};links={}
        for base,dirs,names in os.walk(c.work,followlinks=False):
            base=Path(base)
            for name in list(dirs):
                p=base/name
                if p.is_symlink():links[p.relative_to(c.work).as_posix()]=os.readlink(p);dirs.remove(name)
            for name in names:
                p=base/name;rel=p.relative_to(c.work).as_posix()
                if p.is_symlink():links[rel]=os.readlink(p)
                else:files[rel]=file_hash(p)
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for rel in files:z.write(c.work/rel,rel)
            for rel,value in links.items():
                info=zipfile.ZipInfo(rel);info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,value)
            z.writestr('manifest.json',json.dumps({'files':files,'symlinks':links},ensure_ascii=False))
        with zipfile.ZipFile(target) as z:
            require(z.testzip() is None,'Archive CRC failure')
            with tempfile.TemporaryDirectory(prefix='.restore-test-',dir=c.archive_root) as temp:
                for rel,h in files.items():
                    p=Path(temp)/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(rel));require(file_hash(p)==h,'Archive restore mismatch')
                for rel,value in links.items():
                    require(z.read(rel).decode()==value,'Archive symlink mismatch')
                    p=Path(temp)/rel;p.parent.mkdir(parents=True,exist_ok=True);os.symlink(value,p)
                    require(os.readlink(p)==value,'Restored symlink mismatch')
        shutil.rmtree(c.work)
    return dict(status='PASS',archive=str(target),files=len(files),restore_test='PASS')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('plan','preflight','run','score','report','verify','archive'):
        s=sub.add_parser(name);s.add_argument('config')
        if name in ('run','report','archive'):s.add_argument('--execute',action='store_true')
        if name in ('report','verify'):s.add_argument('--output-dir')
        if name=='report':s.add_argument('--node',required=True);s.add_argument('--node-modules',required=True)
        if name=='score':s.add_argument('--output')
    a=p.parse_args();c=Config(a.config)
    if a.command in ('run','report','archive'):require(a.execute,'Explicit --execute is required; inspect plan/preflight first')
    if a.command=='plan':result=plan(c)
    elif a.command=='preflight':result=preflight(c)
    elif a.command=='run':
        jobs=run(c);result=dict(status='completed',jobs=len(jobs),new_trials=sum(x['status']=='completed' for x in jobs),verified_existing=sum(x['status']=='verified-existing' for x in jobs))
    elif a.command=='score':
        full=scored_data(c)
        if a.output:save_json(Path(a.output),full)
        result=[{k:v for k,v in r.items() if k!='rows'} for r in full['rounds']]
    elif a.command=='report':result=report(c,a.node,a.node_modules,a.output_dir)
    elif a.command=='verify':result=verify_reports(c,a.output_dir)
    else:result=archive(c)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except (PipelineError,subprocess.CalledProcessError,subprocess.TimeoutExpired,OSError,ValueError) as e:
        print(f'ERROR: {e}',file=sys.stderr);sys.exit(1)
