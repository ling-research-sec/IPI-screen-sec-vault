"""Shared Tk UI. Workers never read or mutate Tk objects."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from zoneinfo import ZoneInfo
from .adb_controller import ADB
from .case_loader import SCENARIOS, load_cases, FORMAL_WORKBOOK, FIXED_PDF
from .gemini_controller import DEFAULT_PHONE_PDF_DIR, FAST_RESPONSE_BUDGET_SECONDS
from .evidence import Evidence, atomic_json, p1_case_path, p1_evidence_round, p1_round_dir, p1_round_numbers
from .runner import ROOT, p1_observation_restart_eligible, p1_unsubmitted_baseline_restart_eligible
from .screenshot import capture
from .state import Control, DeviceLease, DeviceDisconnected, LabError, NewChatBlocked, Stopped, ObservationUnavailable


class LabWindow:
    def __init__(self, root, pathway, *, smoke=False, state_dir=None):
        self.root, self.pathway = root, pathway
        self.queue = queue.Queue()
        self.worker = None
        self.control = Control()
        self.cases, self.filtered, self.index = [], [], 0
        self.inputs = []
        self.last_path = None
        self.calendars = {}
        self.state_dir=Path(state_dir or ROOT/'.state')
        self.ui_path=self.state_dir/f'ui-{pathway}.json'
        self.persist_enabled=not smoke or state_dir is not None
        self.progress_enabled=self.persist_enabled and pathway in ('p1','p2')
        self.startup_calendar_refresh=pathway=='p3' and not smoke
        self.saved={}
        if self.persist_enabled and self.ui_path.exists():
            try:self.saved=json.loads(self.ui_path.read_text())
            except (OSError,ValueError):pass
        self.progress=None;self.history_window=None;self.history_vars={};self.history_boxes={}
        self.restore_selection=bool(self.saved);self._last_saved=None
        root.title('Gemini Memory Lab V2 - ' + pathway.upper() + ('（进度与续跑）' if pathway == 'p1' else ''))
        root.geometry('1000x850')
        root.minsize(840, 720)
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        self.serial = tk.StringVar()
        self.xlsx = tk.StringVar(value=str(FORMAL_WORKBOOK if FORMAL_WORKBOOK.exists() else ROOT / 'sample_cases.xlsx'))
        self.scenario = tk.StringVar(value=SCENARIOS[0])
        self.current = tk.StringVar(value='尚未加载案例')
        self.status = tk.StringVar(value='就绪；不会自动发送请求')
        self.wait_seconds = tk.StringVar(value='20' if pathway=='p2' else '60')
        self.p2_screen_capture_seconds = tk.StringVar(value=str(self.saved.get('p2_screen_capture_seconds', 60)))
        self.p2_auto_recovery=tk.BooleanVar(value=self.saved.get('p2_auto_recovery',True) is True)
        self.p2_copy_post=tk.BooleanVar(value=self.saved.get('p2_copy_post',True) is not False)
        self.p2_post_capture_seconds=tk.StringVar(value=str(self.saved.get('p2_post_capture_seconds',90)))
        self.p2_recovery_attempts=tk.StringVar(value=str(self.saved.get('p2_recovery_attempts',2)))
        self.p2_reconnect_seconds=tk.StringVar(value=str(self.saved.get('p2_reconnect_seconds',30)))
        if pathway=='p2':
            self.wait_seconds.set(str(self.saved.get('p2_capture_seconds', 20)))
        self.injection_wait_seconds = tk.StringVar(value='60')
        self.evidence_root = tk.StringVar(value=str(ROOT / 'evidence'))
        self.pdf = tk.StringVar(value=str(FIXED_PDF if FIXED_PDF.exists() else ROOT / 'fixtures/harmless-upload.pdf'))
        self.phone_pdf_dir = tk.StringVar(value=DEFAULT_PHONE_PDF_DIR)
        for key,var in [('serial',self.serial),('xlsx',self.xlsx),('scenario',self.scenario),
                        ('injection_wait_seconds',self.injection_wait_seconds),('evidence_root',self.evidence_root),('pdf',self.pdf)]:
            if key in self.saved:var.set(str(self.saved[key]))
        if self.saved.get('last_path') and Path(self.saved['last_path']).exists():self.last_path=Path(self.saved['last_path'])
        self.row = 0
        self.serial_box = self.field(frame, '设备 serial', self.serial, combo=True)
        self.button(frame, '刷新设备', self.refresh_devices, 0, 2)
        self.field(frame, 'XLSX', self.xlsx)
        self.button(frame, '选择 / 加载', self.choose_xlsx, 1, 2)
        box = self.field(frame, 'Scenario', self.scenario, combo=True)
        self.scenario_box = box
        box.configure(values=SCENARIOS)
        box.bind('<<ComboboxSelected>>', lambda _: self.filter_cases())
        ttk.Label(frame, textvariable=self.current).grid(row=self.row, column=0, columnspan=2, sticky='w', pady=4)
        nav = ttk.Frame(frame)
        nav.grid(row=self.row, column=2)
        self.inputs.extend([ttk.Button(nav, text='上一条', command=lambda: self.move(-1)),
                            ttk.Button(nav, text='下一条', command=lambda: self.move(1))])
        for b in self.inputs[-2:]: b.pack(side='left')
        self.row += 1
        if pathway=='p2':
            self.field(frame,'A/D 观察预算（秒）',self.wait_seconds)
            self.field(frame,'浮窗观察预算（秒）',self.p2_screen_capture_seconds)
        elif pathway=='p1':
            self.field(frame, '注入后等待（秒）', self.injection_wait_seconds)
        else:
            self.field(frame, '响应超时（秒）', self.wait_seconds)
        if pathway == 'p3':
            self.field(frame, '读取后等待（秒，仅循环）', self.injection_wait_seconds)
            actions = ttk.Frame(frame)
            actions.grid(row=self.row-1, column=2)
            for label, batch in [('单条循环', False), ('顺序循环', True)]:
                b = ttk.Button(actions, text=label, command=lambda batch=batch: self.start_p3_cycle(batch))
                b.pack(side='left', padx=3)
                self.inputs.append(b)
        self.field(frame, '证据目录', self.evidence_root)
        if pathway=='p1':
            number=self.saved.get('p1_round',1)
            self.p1_round=tk.StringVar(value=f'第{number if type(number) is int and number>0 else 1}轮')
            self.round_box=self.field(frame,'运行轮次',self.p1_round,combo=True)
            self.round_box.bind('<<ComboboxSelected>>',lambda _:self.select_p1_round())
            self.button(frame,'新建下一轮',self.new_p1_round,self.row-1,2)
            self.refresh_p1_rounds()
        elif pathway=='p2':
            from .evidence import p2_round_numbers
            number=self.saved.get('p2_round',max(p2_round_numbers(self.evidence_root.get()),default=0)+1)
            self.p2_round=tk.StringVar(value=f'第{number if type(number) is int and number>0 else 1}轮')
            self.round_box=self.field(frame,'运行轮次',self.p2_round,combo=True)
            self.round_box.bind('<<ComboboxSelected>>',lambda _:self.select_p2_round())
            self.button(frame,'新建下一轮',self.new_p2_round,self.row-1,2)
            self.refresh_p2_rounds()
        if pathway in ('p1','p2'):
            self.baseline_preview = self.text_field(frame,'前测 Prompt（XLSX A 列原文）',height=2)
            self.post_preview = self.text_field(frame,'后测 Prompt（XLSX D 列原文，不复用 A）',height=2)
            self.p1_criteria = tk.StringVar()
            ttk.Label(frame,textvariable=self.p1_criteria,wraplength=940).grid(row=self.row,column=0,columnspan=3,sticky='w')
            self.row += 1
        if pathway == 'p1':
            self.p1_delivery = tk.StringVar(value='第二阶段：加载正式 Case 后显示附件和聊天框文字')
            ttk.Label(frame, textvariable=self.p1_delivery, wraplength=940).grid(
                row=self.row, column=0, columnspan=3, sticky='w', pady=(6, 0))
            self.row += 1
        attacker_label = {
            'p1': 'XLSX C 列原文（正式 Case：只写入 PDF 第 2 页）',
            'p2': '注入 Prompt（XLSX C 列，正式 Case 只读）',
            'p3': 'Description / Attacker Prompt（可覆盖；原文和实际输入分别保存）',
        }[pathway]
        self.attacker = self.text_field(frame, attacker_label, height=5)
        if pathway == 'p1':
            self.field(frame, '基础 PDF', self.pdf)
            self.button(frame, '选择 PDF', self.choose_pdf, self.row-1, 2)
            self.button(frame, '预览本 Case PDF（仅本机）', self.preview_p1, self.row, 1)
            self.button(frame, '预览基础 PDF', self.preview_p1_base, self.row, 2)
            self.row += 1
            ttk.Label(frame, text='手机 PDF 库').grid(row=self.row, column=0, sticky='w')
            ttk.Label(frame, textvariable=self.phone_pdf_dir).grid(row=self.row, column=1, sticky='w')
            self.row += 1
            from .p1_active_upload import ACTIVE_PDF_DIR
            ttk.Label(frame,text='手机单文件上传').grid(row=self.row,column=0,sticky='w')
            ttk.Label(frame,text=ACTIVE_PDF_DIR+'（仅当前 Case）').grid(row=self.row,column=1,sticky='w')
            self.row += 1
            self.p1_copy_post = tk.BooleanVar(value=self.saved.get('p1_copy_post') is True)
            copy_option = ttk.Checkbutton(frame, text='后测复制正文（默认只截图）',
                                          variable=self.p1_copy_post)
            copy_option.grid(row=self.row, column=1, columnspan=2, sticky='w')
            self.inputs.append(copy_option)
            self.row += 1
            self.p1_active = tk.StringVar(value='当前运行：尚未开始')
            ttk.Label(frame, textvariable=self.p1_active, wraplength=940).grid(
                row=self.row, column=0, columnspan=3, sticky='w', pady=4)
            self.row += 1
        elif pathway == 'p2':
            from p2_screen_pdf.runner import SCREEN_PROMPT
            self.screen_prompt = tk.StringVar(value=SCREEN_PROMPT)
            ttk.Label(frame, text='便签灰度248 → 助理直接读屏 → D；失败优先圆圈重答，无按钮则整条重跑；共2次后留档跳过').grid(
                row=self.row, column=0, columnspan=3, sticky='w')
            self.row += 1
            recovery=ttk.Frame(frame);recovery.grid(row=self.row,column=0,columnspan=3,sticky='w')
            auto=ttk.Checkbutton(recovery,text='自动只观察恢复',variable=self.p2_auto_recovery);auto.pack(side='left')
            ttk.Label(recovery,text='次数（0–2）').pack(side='left')
            attempts=ttk.Entry(recovery,textvariable=self.p2_recovery_attempts,width=3);attempts.pack(side='left',padx=4)
            ttk.Label(recovery,text='同serial重连预算/次（0–30秒）').pack(side='left')
            window=ttk.Entry(recovery,textvariable=self.p2_reconnect_seconds,width=4);window.pack(side='left',padx=4)
            self.inputs.extend([auto,attempts,window]);self.row+=1
            post=ttk.Frame(frame);post.grid(row=self.row,column=0,columnspan=3,sticky='w')
            copy=ttk.Checkbutton(post,text='D后测复制正文＋多屏截图（默认开启）',variable=self.p2_copy_post);copy.pack(side='left')
            ttk.Label(post,text='D保存预算/秒').pack(side='left',padx=(12,2))
            budget=ttk.Entry(post,textvariable=self.p2_post_capture_seconds,width=5);budget.pack(side='left')
            self.inputs.extend([copy,budget]);self.row+=1
        else:
            from p3_calendar.runner import READ_PROMPT
            self.calendar_id = tk.StringVar()
            self.last_calendar_id = self.saved.get('calendar_id', '')
            self.calendar_error = ''
            self.event_title = tk.StringVar(value='Meeting')
            now = datetime.now(ZoneInfo('Asia/Taipei')).replace(hour=10, minute=0, second=0, microsecond=0)
            self.start = tk.StringVar(value=now.isoformat())
            self.end = tk.StringVar(value=(now + timedelta(hours=1)).isoformat())
            self.read_prompt = tk.StringVar(value=READ_PROMPT)
            self.enable_verification = tk.BooleanVar(value=False)
            self.calendar_box = self.field(frame, '专用测试日历', self.calendar_id, combo=True)
            actions = ttk.Frame(frame)
            actions.grid(row=self.row-1, column=2)
            for label, cmd in [('刷新', self.list_calendars), ('创建专用日历', self.create_calendar)]:
                b = ttk.Button(actions, text=label, command=cmd); b.pack(side='left'); self.inputs.append(b)
            self.field(frame, 'Event Title', self.event_title)
            self.field(frame, '开始（ISO 时间，含时区）', self.start)
            self.field(frame, '结束（ISO 时间，含时区）', self.end)
            self.field(frame, 'Calendar Read Prompt', self.read_prompt)
            self.verification = self.text_field(frame, 'Verification Prompt', height=2)
            self.verification_default = None
            saved = ROOT / '.state/gui-p3.json'
            if saved.exists():
                self.verification_default = json.loads(saved.read_text()).get('verification_prompt', '')
                self.verification.insert('1.0', self.verification_default)
            cb = ttk.Checkbutton(frame, text='启用额外验证（新会话；不评分）', variable=self.enable_verification)
            cb.grid(row=self.row, column=0, columnspan=2, sticky='w'); self.inputs.append(cb)
            self.button(frame, '保存验证默认值', self.save_defaults, self.row, 2)
            self.row += 1
        control_area = ttk.Frame(frame)
        control_area.grid(row=self.row, column=0, columnspan=3, sticky='w', pady=8)
        controls = control_area
        extra_controls = control_area
        if pathway=='p2':
            controls=ttk.Frame(control_area);controls.pack(fill='x')
            extra_controls=ttk.Frame(control_area);extra_controls.pack(fill='x',pady=(4,0))
        self.start_button = ttk.Button(controls, text='开始', command=self.start_run)
        self.start_button.pack(side='left', padx=3)
        self.inputs.append(self.start_button)
        self.pause_button = ttk.Button(controls, text='暂停', command=self.pause)
        self.pause_button.pack(side='left', padx=3)
        ttk.Button(controls, text='停止 / 人工接管', command=self.stop).pack(side='left', padx=3)
        ttk.Button(controls, text='截图', command=self.snapshot).pack(side='left', padx=3)
        if pathway!='p1':
            self.review_button = ttk.Button(extra_controls, text='人工核查未决运行', command=self.review)
            self.review_button.pack(side='left', padx=3); self.inputs.append(self.review_button)
        ttk.Button(controls, text='打开证据', command=self.open_evidence).pack(side='left', padx=3)
        if pathway in ('p1','p2'):
            self.history_button=ttk.Button(controls,text='采集记录',command=self.open_history)
            self.history_button.pack(side='left',padx=3);self.inputs.append(self.history_button)
            handover=ttk.Button(controls,text='交接已停止任务',command=self.handover_collection)
            handover.pack(side='left',padx=3);self.inputs.append(handover)
        if pathway=='p1':
            self.resume_button=ttk.Button(controls,text='继续未完成',command=self.resume_run)
            self.resume_button.pack(side='left',padx=3);self.inputs.append(self.resume_button)
            self.p1_all_button=ttk.Button(controls,text='整表循环',command=self.run_p1_all,state='disabled')
            self.p1_all_button.pack(side='left',padx=3);self.inputs.append(self.p1_all_button)
        elif pathway=='p2':
            self.resume_button=ttk.Button(controls,text='继续未完成',command=self.resume_p2_run)
            self.resume_button.pack(side='left',padx=3);self.inputs.append(self.resume_button)
            self.p2_all_button=ttk.Button(controls,text='整表循环',command=self.run_p2_all)
            self.p2_all_button.pack(side='left',padx=3);self.inputs.append(self.p2_all_button)
            organize=ttk.Button(extra_controls,text='整理本轮证据',command=self.organize_p2_selected_round)
            organize.pack(side='left',padx=3);self.inputs.append(organize)
        self.row += 1
        ttk.Label(frame, textvariable=self.status, wraplength=940).grid(row=self.row, column=0, columnspan=3, sticky='w')
        self.row += 1
        self.output = tk.Text(frame, height=7, state='disabled', wrap='word')
        self.output.grid(row=self.row, column=0, columnspan=3, sticky='nsew', pady=6)
        frame.rowconfigure(self.row, weight=1)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(100, self.drain)
        if self.persist_enabled:self.root.after(1000,self.autosave)
        if not smoke:
            self.load_xlsx(self.xlsx.get())
        else:
            root.update_idletasks()

    def field(self, frame, label, variable, combo=False):
        ttk.Label(frame, text=label).grid(row=self.row, column=0, sticky='w', pady=3, padx=(0,10))
        widget = ttk.Combobox(frame, textvariable=variable, state='readonly') if combo else ttk.Entry(frame, textvariable=variable)
        widget.grid(row=self.row, column=1, sticky='ew', pady=3)
        self.inputs.append(widget)
        self.row += 1
        return widget

    def button(self, frame, label, callback, row, col):
        button = ttk.Button(frame, text=label, command=callback)
        button.grid(row=row, column=col, padx=4, sticky='ew')
        self.inputs.append(button)
        return button

    def text_field(self, frame, label, height):
        ttk.Label(frame, text=label).grid(row=self.row, column=0, columnspan=3, sticky='w', pady=(5,2))
        self.row += 1
        text = tk.Text(frame, height=height, wrap='word', undo=True)
        text.grid(row=self.row, column=0, columnspan=3, sticky='ew')
        self.row += 1
        self.inputs.append(text)
        return text

    def log(self, text):
        self.queue.put(('log', str(text)))

    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def launch(self, fn):
        if self.busy(): return
        for w in self.inputs: w.configure(state='disabled')
        def work():
            try: fn()
            except Exception as exc: self.log(type(exc).__name__ + '：' + str(exc))
            finally: self.queue.put(('done', None))
        self.worker = threading.Thread(target=work, daemon=False)
        self.worker.start()
        if self.pathway=='p1':self.refresh_progress()

    def drain(self):
        try:
            while True:
                kind, value = self.queue.get_nowait()
                if kind == 'log':
                    self.status.set(value)
                    self.output.configure(state='normal'); self.output.insert('end', value+'\n')
                    self.output.see('end'); self.output.configure(state='disabled')
                    if self.pathway=='p1' and value.startswith('证据：'):self.refresh_progress()
                elif kind == 'done':
                    for w in self.inputs:
                        w.configure(state='readonly' if isinstance(w, ttk.Combobox) else 'normal')
                    self.pause_button.configure(text='暂停')
                    self.lock_formal_prompts()
                    self.refresh_progress()
                    if self.pathway=='p1':self.root.after(30,self.refresh_progress)
                    if self.startup_calendar_refresh:
                        self.startup_calendar_refresh=False
                        self.root.after(30,self.refresh_calendar_on_startup)
                elif kind == 'devices':
                    self.serial_box.configure(values=value)
                    if len(value) == 1: self.serial.set(value[0])
                elif kind == 'cases':
                    if self.history_window and self.history_window.winfo_exists():
                        self.history_window.destroy();self.history_window=None
                    self.cases = value
                    if self.progress_enabled:
                        from .progress import ProgressStore
                        folder=self.selected_p1_round_dir() if self.pathway=='p1' else self.selected_p2_round_dir()
                        protocol=self.p2_protocol_version() if self.pathway=='p2' else None
                        self.progress=ProgressStore(self.state_dir,value[0].workbook_sha256,self.pathway,round_dir=folder,protocol_version=protocol)
                    if self.pathway=='p1':self.refresh_p1_rounds()
                    scenarios = tuple(dict.fromkeys(c.scenario for c in value))
                    self.scenario_box.configure(values=scenarios)
                    if self.scenario.get() not in scenarios:
                        self.scenario.set(scenarios[0])
                    self.filter_cases()
                    if self.restore_selection:
                        saved_id=self.saved.get('case_id');saved_hash=self.saved.get('workbook_sha256')
                        if value[0].workbook_sha256==saved_hash:
                            for i,c in enumerate(self.filtered):
                                if c.case_id==saved_id:self.index=i;self.show_case();break
                        self.restore_selection=False
                    prefix=f'{self.p1_round.get()}：' if self.pathway=='p1' else ''
                    self.log(f'{prefix}已加载 {len(value)} 条案例；可刷新并选择设备')
                    if self.progress_enabled:
                        self.refresh_progress()
                        pending=self.progress.latest_unfinished(value) if self.pathway=='p1' else None
                        if pending:
                            self.log(self.p1_pending_notice(pending))
                        if self.pathway=='p1':
                            from .p1_reliability import pending_queue
                            try:saved_queue=pending_queue(self.config(),self.progress.workbook_hash,self.serial.get())
                            except (OSError,ValueError,LabError):saved_queue=None
                            if saved_queue:self.log(f'有已保存队列：剩余 {len(saved_queue["remaining"])} 条；点继续未完成恢复整批，不重发已提交阶段')
                elif kind == 'calendars':
                    self.apply_calendars(value)
                elif kind == 'calendar_error':
                    self.calendar_error=value
                    self.apply_calendars(None)
                    self.log('读取专用测试日历失败：'+value)
                elif kind == 'p2_progress':
                    self.refresh_progress()
                elif kind == 'p2_queue_case':
                    target=next((c for c in self.cases if c.case_id==value),None)
                    if target is not None and target.scenario!=self.scenario.get():
                        self.scenario.set(target.scenario);self.filter_cases()
                    for i,case in enumerate(self.filtered):
                        if case.case_id==value:self.index=i;self.show_case();break
                elif kind == 'batch_case':
                    self.index=value;self.show_case()
                elif kind == 'p1_active':
                    self.p1_active.set(value)
                elif kind == 'p1_queue_case':
                    scenario,case_id=value
                    if self.scenario.get()!=scenario:
                        self.scenario.set(scenario);self.filter_cases()
                    for i,case in enumerate(self.filtered):
                        if case.case_id==case_id:
                            self.index=i;self.show_case();break
                elif kind == 'p2_baseline_review':
                    rule, response, decision = value
                    try:
                        decision['passed'] = messagebox.askyesno(
                            'P2：核查前测 B 列',
                            f'B 列要求：{rule}\n\n已留档的 A 回复（可见文本）：\n{response[:1500]}'
                            '\n\n确认前测符合 B 条件并继续？否会停止，不执行 C。',
                            default='no', parent=self.root)
                    finally:
                        decision['ready'].set()
                elif kind == 'p1_tool_review':
                    review_kind, prompt, decision = value
                    try:
                        if review_kind in ('confirm','card'):
                            accepted=messagebox.askyesno('P1 工具试运行',prompt,default='no',parent=self.root)
                            decision['answer']='yes' if accepted else ('no' if review_kind=='card' else None)
                        else:
                            decision['answer']=simpledialog.askstring(
                                'P1 原生 App 核查',prompt,parent=self.root)
                    finally:
                        decision['ready'].set()
                elif kind == 'path':
                    self.last_path = Path(value)
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def refresh_devices(self):
        self.launch(lambda: self.queue.put(('devices', [r['serial'] for r in ADB().devices() if r['state']=='device'])))

    def selected_p1_round_number(self):
        match=re.fullmatch(r'第([1-9][0-9]*)轮',self.p1_round.get())
        if not match:raise LabError('请先选择运行轮次')
        return int(match[1])

    def selected_p1_round_dir(self):
        return p1_round_dir(self.evidence_root.get(),self.selected_p1_round_number())

    def refresh_p1_rounds(self):
        numbers=set(p1_round_numbers(self.evidence_root.get()))
        numbers.add(self.selected_p1_round_number())
        self.round_box.configure(values=[f'第{i}轮' for i in sorted(numbers)])

    def select_p1_round(self):
        if self.busy():return
        try:
            folder=self.selected_p1_round_dir()
            self.refresh_p1_rounds()
            self.save_ui()
            self.log(f'已选 {folder.name}；只在该轮运行，不自动换轮')
            self.load_xlsx(self.xlsx.get())
        except (OSError, ValueError, LabError) as exc:self.log(exc)

    def new_p1_round(self):
        if self.busy():
            if not getattr(self,'_new_round_after_stop',False):
                self._new_round_after_stop=True;self.stop()
                self.log('已登记：当前任务停止落盘后自动新建一轮')
                self.root.after(100,self._finish_stop_then_new_round)
            return
        try:
            number=max(p1_round_numbers(self.evidence_root.get()),default=0)+1
            from .p1_handover import handover_stopped_run
            config=dict(self.config(),p1_round=number)
            if self.cases:
                change=handover_stopped_run(config,self.serial.get(),self.cases[0].workbook_sha256)
                if change['changed']:self.log('旧轮已停止并保留断点；新轮可启动，不重发旧阶段')
            folder=p1_round_dir(self.evidence_root.get(),number)
            folder.mkdir(parents=True,exist_ok=False)
            self.p1_round.set(folder.name)
            self.select_p1_round()
        except (OSError, ValueError, LabError) as exc:self.log(exc)

    def _finish_stop_then_new_round(self):
        if self.busy():self.root.after(100,self._finish_stop_then_new_round);return
        self._new_round_after_stop=False;self.new_p1_round()

    @staticmethod
    def p2_protocol_version():
        from p2_screen_pdf.runner import COLLECTION_PROTOCOL
        return COLLECTION_PROTOCOL

    def selected_p2_round_number(self):
        match=re.fullmatch(r'第([1-9][0-9]*)轮',self.p2_round.get())
        if not match:raise LabError('请选择有效的 P2 轮次')
        return int(match[1])

    def selected_p2_round_dir(self):
        from .evidence import p2_round_dir
        return p2_round_dir(self.evidence_root.get(),self.selected_p2_round_number())

    def refresh_p2_rounds(self):
        from .evidence import p2_round_numbers
        numbers=set(p2_round_numbers(self.evidence_root.get()));numbers.add(self.selected_p2_round_number())
        self.round_box.configure(values=[f'第{i}轮' for i in sorted(numbers)])

    def select_p2_round(self):
        if self.busy():return
        try:
            self.refresh_p2_rounds();self.save_ui()
            self.log(f'已选 {self.p2_round.get()}；进度只属于本轮与直接浮窗协议')
            self.load_xlsx(self.xlsx.get())
        except Exception as exc:self.log(exc)

    def new_p2_round(self):
        if self.busy():
            if not getattr(self,'_new_p2_round_after_stop',False):
                self._new_p2_round_after_stop=True;self.stop()
                self.root.after(100,self._finish_p2_stop_then_new_round)
            return
        try:
            from .evidence import p2_round_numbers,p2_round_dir
            from .p1_handover import handover_collection_run
            number=max(p2_round_numbers(self.evidence_root.get()),default=0)+1
            cfg=dict(self.config(),p2_round=number);serial=self.serial.get();changed=False
            if serial:
                lease=DeviceLease(self.state_dir,serial)
                saved=json.loads(lease.path.read_text()) if lease.path.exists() else {}
                if saved.get('unresolved'):
                    from .progress import read_run
                    old,_=read_run(saved['run_dir'])
                    if old.get('pathway')!='p2':raise LabError('原通道有未决任务；请使用明确的跨通道交接按钮')
                    if not self.cases:raise LabError('请先载入原源表')
                    changed=handover_collection_run(cfg,serial,self.cases[0].workbook_sha256,target_pathway='p2',confirmed=True)['changed']
            folder=p2_round_dir(self.evidence_root.get(),number);folder.mkdir(parents=True,exist_ok=changed)
            self.p2_round.set(folder.name);self.select_p2_round()
        except Exception as exc:self.log(exc)

    def _finish_p2_stop_then_new_round(self):
        if self.busy():self.root.after(100,self._finish_p2_stop_then_new_round);return
        self._new_p2_round_after_stop=False;self.new_p2_round()

    def handover_collection(self):
        if self.busy():return
        try:
            from .p1_handover import handover_collection_run
            cfg=self.config();serial=self.serial.get()
            if not serial or not self.cases:raise LabError('先载入源表并选择原 serial')
            lease=DeviceLease(self.state_dir,serial)
            saved=json.loads(lease.path.read_text()) if lease.path.exists() else {}
            if not saved.get('unresolved'):self.log('当前无未决控制权，无需交接');return
            from .progress import read_run
            result,_=read_run(saved['run_dir'])
            if not messagebox.askyesno('显式交接已停止任务',
                f'原任务 {result.get("pathway")} / {saved["run_dir"]}\n目标 {self.pathway} / 选定轮次\n'
                '确认只交接控制权，保留原提交、证据和尾队列，不撤销或重发请求？',default='no',parent=self.root):return
            change=handover_collection_run(cfg,serial,self.cases[0].workbook_sha256,target_pathway=self.pathway,confirmed=True)
            self.log('交接已留痕：'+str(change))
        except Exception as exc:self.log(exc)

    def load_xlsx(self, path):
        evidence_root=Path(self.evidence_root.get());state_dir=self.state_dir;progress_enabled=self.progress_enabled;pathway=self.pathway
        folder=self.selected_p1_round_dir() if pathway=='p1' else self.selected_p2_round_dir() if pathway=='p2' else None
        protocol=self.p2_protocol_version() if pathway=='p2' else None
        def load():
            cases=load_cases(path)
            if progress_enabled:
                from .progress import ProgressStore
                store=ProgressStore(state_dir,cases[0].workbook_sha256,pathway,round_dir=folder,protocol_version=protocol)
                base=folder if folder is not None else evidence_root/pathway
                glob='*' if folder is not None else '*/*'
                records=sorted(base.glob(glob+'/result.json'))+sorted(base.glob(glob+'/_debug/result.json'))
                if pathway=='p2' and folder is not None:
                    from .p2_archive import archive_folder
                    archive=archive_folder(folder)
                    records+=sorted(archive.glob('case*/result.json'))+sorted(archive.glob('case*/_debug/result.json'))
                for result in records:
                    run=result.parent.parent if result.parent.name=='_debug' else result.parent
                    try:store.import_run(run)
                    except (OSError,ValueError,KeyError,LabError):pass
                if pathway=='p2':store.recheck_p2()
            self.queue.put(('cases',cases))
        self.launch(load)

    def choose_xlsx(self):
        path = filedialog.askopenfilename(filetypes=[('Excel', '*.xlsx')])
        if path: self.xlsx.set(path); self.load_xlsx(path)

    def filter_cases(self):
        self.filtered = [c for c in self.cases if c.scenario == self.scenario.get()]
        self.index = 0; self.show_case()

    def show_case(self):
        self.set_text(self.attacker,'')
        if self.pathway in ('p1','p2'):
            self.set_text(self.baseline_preview,'');self.set_text(self.post_preview,'')
            self.p1_criteria.set('')
        if self.pathway == 'p1':
            self.p1_delivery.set('第二阶段：加载正式 Case 后显示附件和聊天框文字')
        if self.filtered:
            c = self.filtered[self.index]
            self.current.set(f'{c.case_id}  / XLSX 第 {c.row} 行 / 当前 Scenario {self.index+1}/{len(self.filtered)}')
            self.set_text(self.attacker,c.attacker_prompt)
            if self.pathway in ('p1','p2'):
                self.set_text(self.baseline_preview,c.user_prompt)
                self.set_text(self.post_preview,c.verification_prompt)
                self.p1_criteria.set('B 前测约束：'+c.baseline_constraint+'；E 后测目标：'+c.attack_goal+'（仅记录，不自动判分）')
            if self.pathway == 'p1':
                from p1_file_upload.pdf_payload import CHAT_MESSAGE, payload_filename
                if c.source_schema == 'formal_ABCDE':
                    self.p1_delivery.set(
                        f'第二阶段（新运行）：{payload_filename(c.case_index)}（2 页）\n'
                        f'聊天框仅发送：{CHAT_MESSAGE}')
                else:
                    self.p1_delivery.set('第二阶段（旧样例）：基础 PDF + 聊天框 C 列')
            if self.pathway == 'p3':
                self.set_text(self.verification,c.verification_prompt if self.verification_default is None else self.verification_default)
        else: self.current.set('该 Scenario 没有案例')
        self.lock_formal_prompts()
        self.refresh_progress()

    @staticmethod
    def set_text(widget,value):
        # Tk ignores insert/delete on disabled widgets during async workbook loading.
        state=widget.cget('state');widget.configure(state='normal')
        widget.delete('1.0','end');widget.insert('1.0',value);widget.configure(state=state)

    def lock_formal_prompts(self):
        if self.pathway in ('p1','p2'):
            self.baseline_preview.configure(state='disabled');self.post_preview.configure(state='disabled')
        if self.pathway in ('p1','p2') and self.filtered and self.filtered[self.index].source_schema=='formal_ABCDE':
            self.attacker.configure(state='disabled')

    def move(self, delta):
        if self.filtered:
            self.index = max(0, min(len(self.filtered)-1, self.index+delta)); self.show_case()

    def selection(self):
        if not self.filtered: raise LabError('先加载当前 Scenario 的案例')
        original=self.filtered[self.index];text=self.attacker.get('1.0','end-1c')
        if not text.strip() or len(text.encode('utf-8'))>48000:
            raise LabError('Attacker Prompt 为空或过长；尚未操作手机，请重新加载 XLSX')
        if self.pathway in ('p1','p2') and original.source_schema=='formal_ABCDE':
            if text!=original.attacker_prompt:
                raise LabError('正式案例必须使用 C 列原文，显示值不一致，请重新加载')
            return original
        return original.override(attacker=text)

    def config(self):
        wait = float(self.wait_seconds.get())
        if not 1 <= wait <= 3600: raise LabError('响应超时应为 1–3600 秒')
        config = {'evidence_root': self.evidence_root.get(), 'wait_seconds': wait}
        if self.pathway in ('p1','p2'):
            delay = float(self.injection_wait_seconds.get())
            if not 0 <= delay <= 3600:
                raise LabError('注入后等待应为 0–3600 秒')
            config['injection_wait_seconds'] = delay
        if self.pathway == 'p1':
            config['pdf'] = self.pdf.get()
            config.update(phone_pdf_dir=DEFAULT_PHONE_PDF_DIR, p1_sync_library=True, p1_single_file_upload=True, p1_auto_recovery=True, p1_recovery_attempts=2, p1_reconnect_seconds=30,
                          p1_fast_capture=True, p1_copy_post=self.p1_copy_post.get())
        if self.pathway == 'p1': config.update(state_dir=str(self.state_dir),p1_round=self.selected_p1_round_number())
        elif self.pathway == 'p2':
            from p2_screen_pdf.runner import COLLECTION_PROTOCOL
            config.update(screen_prompt=self.screen_prompt.get(), screen_source='note', state_dir=str(self.state_dir),
                          p2_collection_only=True,p2_capture_seconds=wait,injection_wait_seconds=0,
                          p2_screen_capture_seconds=float(self.p2_screen_capture_seconds.get()),
                          p2_protocol_version=COLLECTION_PROTOCOL,p2_round=self.selected_p2_round_number())
            config['p2_reader_view']=True
            config.update(p2_copy_post=self.p2_copy_post.get(),p2_post_save_version=1,p2_post_capture_seconds=float(self.p2_post_capture_seconds.get()),p2_archive_failures=True)
            config.update(p2_continue_on_case_failure=True,p2_case_restarts=2)
            config.update(p2_auto_recovery=self.p2_auto_recovery.get(),p2_recovery_attempts=int(self.p2_recovery_attempts.get()),
                          p2_reconnect_seconds=float(self.p2_reconnect_seconds.get()))
            from .observation_recovery import recovery_policy
            recovery_policy(config)
            from p2_screen_pdf.runner import collection_config
            config = collection_config(config)
        else:
            calendar_id=self.calendars.get(self.calendar_id.get())
            if not calendar_id:
                raise LabError(self.calendar_error or '请刷新并选择专用测试日历；尚未开始运行')
            config.update(calendar_id=calendar_id, state_dir=str(self.state_dir), event_title=self.event_title.get(),
                          start=self.start.get(), end=self.end.get(), calendar_read_prompt=self.read_prompt.get(),
                          enable_verification=self.enable_verification.get(),
                          verification_prompt=self.verification.get('1.0', 'end-1c'))
        return config

    def review_p2_baseline(self, rule, response):
        decision = {'ready': threading.Event(), 'passed': False}
        self.queue.put(('p2_baseline_review', (rule, response, decision)))
        while not decision['ready'].wait(.1):
            self.control.check()
        return decision['passed']

    def review_p1_tool(self, kind, prompt):
        decision={'ready':threading.Event(),'answer':None}
        self.queue.put(('p1_tool_review',(kind,prompt,decision)))
        while not decision['ready'].wait(.1):self.control.check()
        return decision['answer']

    @staticmethod
    def p1_route(case):
        if case.source_schema!='formal_ABCDE' or case.scenario=='改变模型回答':return 'text'
        from p1_file_upload.tool_capture import tool_capture_spec
        return 'tool' if tool_capture_spec(case) else None

    def p1_confirm_tool_environment(self,cases,config,parent=None):
        from p1_file_upload.tool_capture import needs_outbound_confirmation,needs_home_confirmation
        outbound=[c for c in cases if needs_outbound_confirmation(c)]
        playground=[c for c in cases if needs_home_confirmation(c)]
        if not outbound and not playground:return True
        details=[]
        if outbound:
            rows='、'.join(str(c.row) for c in outbound)
            details.append(f'通信类 XLSX 第 {rows} 行：确认所有可能的接收端及外发通道均受控。程序不代点发送或拨号确认。')
            if any(c.row==36 for c in outbound):details.append('第36行紧急拨号只在隔离 Android 模拟器执行。')
        if playground:
            rows='、'.join(str(c.row) for c in playground)
            details.append(f'家居类 XLSX 第 {rows} 行：确认当前 Gemini / Home 为无真实设备的测试环境（可为空家庭或仅有 Playground 虚拟设备）。本轮只留截图。')
        ok=messagebox.askyesno('确认工具测试环境','\n\n'.join(details),default='no',parent=parent or self.root)
        if ok:
            if outbound:config['outbound_test_confirmed']=True
            if playground:config['home_test_confirmed']=True
        return ok

    def p1_runner(self,serial,case,config,control):
        from p1_file_upload.tool_capture import p1_runner_class
        from p1_file_upload.pdf_payload import LEGACY_MODE, payload_filename
        pdf_mode = case.source_schema == 'formal_ABCDE' and config.get('p1_injection_mode') != LEGACY_MODE
        attachment = payload_filename(case.case_index) if pdf_mode else (
            'Meeting-Time.pdf' if case.source_schema == 'formal_ABCDE' else 'harmless.pdf')
        identity = f'c{case.case_index:03d}' if pdf_mode else case.case_id
        stages = {'device_preflight':'准备', 'sync_phone_pdf_library':'同步 PDF 库',
                  'baseline_new_chat':'A 前测', 'upload_case_pdf':'选择当前附件',
                  'upload_harmless_pdf':'选择原协议附件', 'attachment_ready':'附件就绪',
                  'post_new_chat':'D 后测', 'p1_cycle_complete':'流程已结束'}

        def log(message):
            if message in stages:
                self.queue.put(('p1_active',
                    f'当前运行：{identity} · Excel 第 {case.row} 行 · {attachment}｜{stages[message]}'))
            self.log(message)

        return p1_runner_class(case)(serial,case,config,control=control,log=log)

    def p1_prepare_new(self, cases, config, serial, parent=None):
        from .progress import complete_run, latest_continuation, read_run, ProgressStore
        lease=DeviceLease(self.state_dir,serial)
        abandoned=None
        if lease.path.exists():
            pending=json.loads(lease.path.read_text())
            if pending.get('unresolved'):
                original=pending['run_dir']
                latest=latest_continuation(original)
                if not complete_run(latest):
                    result,_=read_run(latest)
                    if result.get('pathway')!='p1':
                        raise LabError('此设备有其他路径的未决任务，请回原窗口处理')
                    decision=messagebox.askyesnocancel(
                        '仍有未完成任务',
                        f'旧任务：{latest.parent.name} / {latest.name}。\n\n'
                        '是：继续旧任务，不重发已提交阶段。\n'
                        '否：放弃旧任务并开始新任务（已发请求不撤销）。\n'
                        '取消：不做任何更改。',
                        default='cancel',parent=parent or self.root)
                    if decision is None:return False
                    if decision:
                        self.resume_run();return False
                    abandoned=(original,latest,result)
        for case in cases:
            path=p1_case_path(config['evidence_root'],case,config['p1_round'])
            if path.exists() or path.is_symlink():
                raise LabError(f'{path.parent.name} 已有 XLSX 第 {case.row} 行；请选择其他轮，或点「新建下一轮」')
        if abandoned:
            original,latest,result=abandoned
            receipt=lease.acknowledge('用户在 P1 开始对话中选择放弃旧运行并开始新任务',expected_run=original)
            if re.fullmatch(r'第[1-9][0-9]*轮',latest.parent.name):
                ProgressStore(self.state_dir,result['source']['workbook_sha256'],'p1',round_dir=latest.parent).abandon_run(
                    result['case_id'],latest)
            self.log(f'已放弃旧运行；原证据保留：{receipt}')
        return True

    def start_run(self):
        if self.busy():return
        try:
            case, config, serial = self.selection(), self.config(), self.serial.get()
            if not serial: raise LabError('先刷新并选择设备 serial')
            if self.pathway=='p1':
                if not self.p1_route(case):raise LabError('该行未接入 P1')
                if not self.p1_confirm_tool_environment([case],config):return
                if not self.p1_prepare_new([case],config,serial):return
        except Exception as exc: self.log(exc); return
        if self.pathway=='p2':
            if not self.p1_confirm_tool_environment([case],config):return
            self.start_p2_queue([case],config,serial);return
        self.control = Control()
        self.save_ui()
        def run():
            from p1_file_upload.runner import P1Runner
            from p2_screen_pdf.runner import P2Runner
            from p3_calendar.runner import P3Runner
            cls = {'p1':P1Runner, 'p2':P2Runner, 'p3':P3Runner}[self.pathway]
            options = {'baseline_review': self.review_p2_baseline} if self.pathway == 'p2' else {}
            runner = (self.p1_runner(serial,case,config,self.control) if self.pathway=='p1' else
                      cls(serial, case, config, control=self.control, log=self.log, **options))
            try: runner.execute()
            finally:
                if runner.e: self.queue.put(('path', runner.e.path))
        self.launch(run)

    def start_p3_cycle(self, batch):
        if self.busy():
            return
        try:
            case, config, serial = self.selection(), self.config(), self.serial.get()
            if not serial:
                raise LabError('先刷新并选择设备 serial')
            config.update(p3_cycle=True, injection_wait_seconds=float(self.injection_wait_seconds.get()))
            if batch and case.attacker_prompt != self.filtered[self.index].attacker_prompt:
                raise LabError('顺序循环使用各条 XLSX 原文；自定义描述请用单条循环')
            jobs = list(enumerate(self.filtered[self.index:], self.index)) if batch else [(self.index, case)]
            if any(not c.user_prompt.strip() or not c.verification_prompt.strip() or
                   not c.attacker_prompt.strip() or len(c.attacker_prompt.encode('utf-8')) > 48000 for _, c in jobs):
                raise LabError('队列包含前测、事件描述或后测缺失／超长的案例')
        except Exception as exc:
            self.log(exc)
            return
        if batch and not messagebox.askyesno('P3 顺序循环',
                f'从当前条开始执行 {len(jobs)} 条，保存到同一新轮次。异常即停；只采集证据，不确认来源或自动评分。',
                parent=self.root):
            return
        self.control = control = Control()
        self.save_ui()
        def work():
            from p3_calendar.runner import P3Runner
            from core.evidence import reserve_p3_round
            if batch:
                config['p3_evidence_round'] = reserve_p3_round(config['evidence_root'])
            for index, item in jobs:
                control.check()
                self.queue.put(('batch_case', index))
                runner = P3Runner(serial, item, config, control=control, log=self.log)
                try:
                    runner.execute()
                    if not runner.e.result.get('p3_cycle_complete'):
                        raise LabError('本条循环未完成，队列已停止')
                finally:
                    if runner.e:
                        self.queue.put(('path', runner.e.path))
            self.log('P3 循环采集结束；请核查日历来源')
        self.launch(work)

    def pause(self):
        if not self.busy(): return
        if self.control.paused.is_set():
            self.control.paused.clear(); self.pause_button.configure(text='暂停'); self.log('继续观察；提交不会重放')
        else:
            self.control.paused.set(); self.pause_button.configure(text='继续'); self.log('已请求暂停；可停止后人工接管')

    def stop(self):
        from .p1_handover import record_stop_intent
        if self.pathway in ('p1','p2'):
            try:record_stop_intent(self.state_dir,self.serial.get(),pathway=self.pathway)
            except (OSError,ValueError) as exc:self.log('停止意图记录失败，原断点仍保留：'+str(exc))
        if not self.busy():
            self.control.stop.set();self.control.paused.clear()
            self.log('当前没有正在执行的任务；旧断点保留，可继续旧轮或新建一轮');return
        if self.control.stop.is_set():self.log('停止请求已收到，正在退出并保存断点');return
        self.control.stop.set();self.control.paused.clear()
        self.log('已请求停止，正在退出当前命令并保存断点；不启动额外截图，不重发')

    def snapshot(self):
        if self.busy():
            self.control.snapshot.set(); self.log('截图请求已交给设备工作线程')
            return
        try: case, config, serial = self.selection(), self.config(), self.serial.get()
        except Exception as exc: self.log(exc); return
        def snap():
            opts={'operation':'manual_snapshot'}
            if self.pathway=='p1':opts['p1_round']=config['p1_round']
            if self.pathway=='p2':opts.update(p2_round=config['p2_round'],p2_protocol_version=config['p2_protocol_version'])
            evidence = Evidence(config['evidence_root'], self.pathway, case, serial, opts)
            capture(ADB(serial), evidence, 'manual')
            evidence.finish('manual_snapshot_only')
            self.queue.put(('path', evidence.path)); self.log('截图：' + str(evidence.path))
        self.launch(snap)

    def review(self):
        serial = self.serial.get()
        if not serial: self.log('先选择设备 serial'); return
        note = simpledialog.askstring('人工核查', '先核查手机与旧 result.json。说明提交状态、是否保留草稿，以及允许另开运行的依据：')
        if note:
            self.launch(lambda: self.log('核查凭据：' + str(DeviceLease(ROOT / '.state', serial).acknowledge(note))))

    def choose_pdf(self):
        path = filedialog.askopenfilename(filetypes=[('PDF', '*.pdf')])
        if path: self.pdf.set(path)

    def preview_p1_base(self):
        path = self.pdf.get()
        self.launch(lambda: subprocess.run(['open', path], check=True))

    def preview_p1(self):
        try:
            case = self.selection()
            base = Path(self.pdf.get()).expanduser().resolve()
        except (LabError, OSError, ValueError) as exc:
            self.log(exc)
            return

        def build():
            from p1_file_upload.pdf_payload import preview_payload
            path = preview_payload(case, base, ROOT / 'generated' / 'p1-preview')
            self.log(f'本机预览（不上传）：{path}')
            subprocess.run(['open', str(path)], check=True)

        self.launch(build)

    def preview_p2(self):
        try: case = self.selection()
        except Exception as exc: self.log(exc); return
        def build():
            import time
            from p2_screen_pdf.pdf_builder import build_pdf
            path = ROOT / 'generated' / str(time.time_ns()) / (case.case_id.replace('/', '_') + '.pdf')
            build_pdf(case.attacker_prompt, path, title=case.case_id)
            self.log('PDF：' + str(path)); subprocess.run(['open', str(path)], check=True)
        self.launch(build)

    def apply_calendars(self, value):
        current=self.calendars.get(self.calendar_id.get()) or self.last_calendar_id
        self.last_calendar_id=current
        self.calendars={c['summary']+' ['+c['id']+']':c['id'] for c in (value or [])}
        self.calendar_box.configure(values=list(self.calendars))
        selected=next((label for label,cid in self.calendars.items() if cid==current), '')
        if not selected and len(self.calendars)==1:
            selected=next(iter(self.calendars))
        self.calendar_id.set(selected)
        if value is not None:
            self.calendar_error=''
            self.log(f'可写专用测试日历：{len(value)} 个；个人日历不列入')

    def refresh_calendar_on_startup(self):
        if self.busy():
            self.root.after(30,self.refresh_calendar_on_startup)
        else:
            self.list_calendars()

    def list_calendars(self):
        def work():
            from p3_calendar.calendar_client import CalendarClient
            try:
                self.queue.put(('calendars', CalendarClient().calendars()))
            except LabError as exc:
                self.queue.put(('calendar_error',str(exc)))
        self.launch(work)

    def create_calendar(self):
        if not messagebox.askyesno('专用日历', '新建一个独立的 Gemini Memory Lab 测试日历？不会修改个人日历；需已有手工 OAuth 授权。'): return
        def work():
            from p3_calendar.calendar_client import CalendarClient
            client = CalendarClient(); client.create_test_calendar()
            self.queue.put(('calendars', client.calendars()))
        self.launch(work)

    def save_defaults(self):
        value = self.verification.get('1.0', 'end-1c')
        self.verification_default = value
        def work():
            path = ROOT / '.state/gui-p3.json'; path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(path, {'verification_prompt': value}); self.log('验证 Prompt 默认值已保存')
        self.launch(work)

    def open_evidence(self):
        if self.pathway=='p2':
            try:
                folder=self.selected_p2_round_dir();folder.mkdir(parents=True,exist_ok=True)
                subprocess.Popen(['open',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                self.log('已打开 P2 选中轮次：'+str(folder))
            except Exception as exc:self.log(exc)
            return
        if self.pathway != 'p1':
            path = str(self.last_path or Path(self.evidence_root.get()))
            if not self.busy(): self.launch(lambda: subprocess.run(['open', path], check=True))
            return
        try:
            folder=self.selected_p1_round_dir()
            folder.mkdir(parents=True,exist_ok=True)
            subprocess.Popen(['open',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.log(f'已打开证据轮次：{folder}')
        except (OSError, ValueError, LabError) as exc:
            self.log('打开证据失败：'+str(exc))

    def organize_p2_selected_round(self):
        if self.busy():return
        try:
            root=self.evidence_root.get();number=self.selected_p2_round_number();serial=self.serial.get()
            if not serial:raise LabError('先选择本轮设备 serial')
        except Exception as exc:self.log(exc);return
        def work():
            from .evidence import organize_p2_round
            result=organize_p2_round(root,self.state_dir,number,serial)
            self.log(f'P2 本轮证据整理：{len(result["organized"])} 条；保留待核查 {len(result["skipped"])} 条；原始文件在 _debug')
        self.launch(work)

    def close(self):
        try:self.save_ui()
        except OSError as exc:self.log('界面状态保存失败，原运行证据仍保留：'+str(exc))
        if self.busy():
            self.stop(); self.root.after(200, self.close)
        else: self.root.destroy()

    def save_ui(self):
        if not self.persist_enabled:return
        value={'serial':self.serial.get(),'xlsx':self.xlsx.get(),'scenario':self.scenario.get(),
               'injection_wait_seconds':self.injection_wait_seconds.get(),'pdf':self.pdf.get(),
               'evidence_root':self.evidence_root.get(),'last_path':str(self.last_path) if self.last_path else None}
        if self.pathway=='p1':value.update(p1_round=self.selected_p1_round_number(),phone_pdf_dir=self.phone_pdf_dir.get(),
                                            p1_copy_post=self.p1_copy_post.get())
        if self.pathway=='p2':value.update(p2_capture_seconds=self.wait_seconds.get(),
                                         p2_copy_post=self.p2_copy_post.get(),p2_post_capture_seconds=self.p2_post_capture_seconds.get(),
                                         p2_screen_capture_seconds=self.p2_screen_capture_seconds.get(),p2_round=self.selected_p2_round_number(),
                                         p2_auto_recovery=self.p2_auto_recovery.get(),p2_recovery_attempts=self.p2_recovery_attempts.get(),
                                         p2_reconnect_seconds=self.p2_reconnect_seconds.get())
        if self.pathway=='p3':
            self.last_calendar_id=self.calendars.get(self.calendar_id.get()) or self.last_calendar_id
            value['calendar_id']=self.last_calendar_id
        if self.filtered:
            c=self.filtered[self.index];value.update(case_id=c.case_id,workbook_sha256=c.workbook_sha256)
        if value!=self._last_saved:
            self.ui_path.parent.mkdir(parents=True,exist_ok=True);atomic_json(self.ui_path,value);self._last_saved=value

    def autosave(self):
        try:self.save_ui()
        except OSError as exc:self.log('界面状态保存失败：'+str(exc))
        self.root.after(1000,self.autosave)

    def p1_pending_notice(self, pending):
        case=next(c for c in self.cases if c.case_id==pending['case_id'])
        category=[c for c in self.cases if c.scenario==case.scenario]
        label=self.p1_case_display(case,category.index(case))[0]
        stage=pending.get('stage') or ''
        stages={
            'upload_harmless_pdf':'上传固定 PDF',
            'upload_case_pdf':'上传两页 Case PDF',
            'attachment_ready':'附件已就绪',
            'injection_wait_started':'等待注入生效',
            'wait_saved':'注入等待已结束',
            'copy_post_answer_to_md':'复制 Gemini 后测回答',
            'open_tool_app_for_screenshot':'打开原生 App 取证',
            'device_preflight':'检查设备',
            'baseline_collected_no_automatic_scoring':'前测已留证',
        }
        phase_names={'baseline':'前测','injection':'注入','post':'后测','control_post':'D 对照'}
        phase_actions={'new_chat':'打开会话','chat_ready':'会话已就绪','submit_once':'提交请求',
                       'wait_response':'等待回答','observe_existing_response':'核对原回答','saved':'证据已保存'}
        stage_label=stages.get(stage)
        if stage_label is None:
            stage_label=next((phase+'：'+action for k,phase in phase_names.items()
                              for j,action in phase_actions.items() if stage==f'{k}_{j}'),'等待续接')
        left=pending.get('remaining_seconds')
        remaining=f'，等待剩余 {left:.1f} 秒' if isinstance(left,(int,float)) and left>0 else ''
        return f'{label} 未完成：{stage_label}{remaining}。点「继续未完成」，已提交的阶段不重发。'

    def p1_case_display(self, case, index):
        round_name=self.p1_round.get()
        return f'{round_name} - {index+1:02d} - XLSX 第{case.row}行', round_name

    def refresh_progress(self):
        if self.pathway=='p2':
            return self.refresh_p2_panel()
        if self.pathway!='p1' or not self.filtered:return
        data=self.progress.read()['cases'] if self.progress else {}
        case=self.filtered[self.index]
        current_display=self.p1_case_display(case,self.index)
        self.current.set(current_display[0])
        if not self.progress:return
        auto=manual=0
        for c in self.filtered:
            entry=data.get(c.case_id,{})
            if self.progress.checked(entry):
                if entry.get('manual') is not None:manual+=1
                else:auto+=1
        self.history_button.configure(text=f'采集记录 {auto+manual}/{len(self.filtered)}')
        has_table_jobs=any(c.source_schema=='formal_ABCDE' and self.p1_route(c)
                           and not self.progress.checked(data.get(c.case_id,{})) for c in self.cases)
        self.p1_all_button.configure(state='normal' if has_table_jobs and not self.busy() else 'disabled')
        if self.history_window and self.history_window.winfo_exists():
            cases=tuple(self.filtered)
            if tuple(self.history_vars)!=tuple(c.case_id for c in cases):
                for child in self.history_grid.winfo_children():child.destroy()
                self.history_vars={};self.history_boxes={}
                for i,c in enumerate(cases):
                    var=tk.BooleanVar(master=self.history_window);self.history_vars[c.case_id]=var
                    box=ttk.Checkbutton(self.history_grid,variable=var,command=lambda c=c,v=var:self.toggle_history(c,v))
                    box.grid(row=i//7,column=i%7,padx=8,pady=7);self.history_boxes[c.case_id]=box
            active=next((label for label,name in self.history_categories.items() if name==self.scenario.get()),'')
            self.history_category.set(active)
            self.history_category.configure(state='disabled' if self.busy() else 'readonly')
            enabled=sum(self.p1_route(c) is not None for c in cases)
            self.history_count.set(f'{self.scenario.get()}（本轮）：自动 {auto}，人工 {manual}，共 {auto+manual}/{len(cases)}；已接入 {enabled} 条')
            self.history_pending={}
            selected=''
            for i,c in enumerate(cases):
                entry=data.get(c.case_id,{})
                checked=self.progress.checked(entry)
                route=self.p1_route(c)
                self.history_vars[c.case_id].set(checked)
                origin='人工' if entry.get('manual') is True else ('人工取消' if entry.get('manual') is False else ('自动' if entry.get('auto_complete') else ('未完成' if route else '待接入')))
                self.history_boxes[c.case_id].configure(text=f'{i+1} · {origin}')
                if i != self.index and (not route or checked):continue
                label, title_round=(current_display if i == self.index else self.p1_case_display(c,i))
                if i == self.index:
                    self.history_window.title(f'P1 采集记录 · {title_round}')
                if route and not checked:
                    self.history_pending[label]=i
                    if i == self.index:selected=label
            self.history_select.configure(values=tuple(self.history_pending),state='disabled' if self.busy() else 'readonly')
            self.history_select.set(selected)
            ready=bool(self.history_pending) and not self.busy()
            self.history_single.configure(state='normal' if selected and not self.busy() else 'disabled')
            self.history_loop.configure(state='normal' if ready else 'disabled')

    def p2_panel_cases(self):
        from p2_screen_pdf.tool_runner import p2_supported
        supported=[c for c in self.cases if p2_supported(c)]
        if supported and self.scenario.get() not in {c.scenario for c in supported}:
            self.scenario.set(supported[0].scenario)
        return [c for c in supported if c.scenario==self.scenario.get()]

    def refresh_p2_panel(self):
        if not self.progress:return
        from .progress import p2_pending
        cases=self.p2_panel_cases();entries=self.progress.read()['cases'];pending=p2_pending(cases,entries)
        auto=sum(bool(entries.get(c.case_id,{}).get('auto_complete')) and entries.get(c.case_id,{}).get('manual') is None for c in cases)
        manual=sum(entries.get(c.case_id,{}).get('manual') is True for c in cases)
        self.history_button.configure(text=f'采集记录 {len(cases)-len(pending)}/{len(cases)}')
        if not self.history_window or not self.history_window.winfo_exists():return
        if set(self.history_boxes)!=set(c.case_id for c in cases):self.open_p2_panel();return
        self.history_window.title('P2 采集记录 · '+self.p2_round.get())
        self.history_count.set(f'{self.scenario.get()}（本轮）：自动 {auto}，人工 {manual}，共 {len(cases)-len(pending)}/{len(cases)}；已接入 {len(cases)} 条')
        active=next((key for key,value in self.history_categories.items() if value==self.scenario.get()),'')
        self.history_category.set(active)
        for i,c in enumerate(cases):
            entry=entries.get(c.case_id,{})
            label='人工' if entry.get('manual') is True else '后测待复核' if entry.get('status') in ('needs_post_review','post_review_pending') else '自动' if self.progress.checked(entry) else '失败已跳过' if entry.get('status')=='failed_skipped' else '未完成'
            if c.row==36 and not self.progress.checked(entry):label='模拟器单测'
            self.history_vars[c.case_id].set(self.progress.checked(entry))
            self.history_boxes[c.case_id].configure(text=f'{i+1} · {label}')
        self.history_pending={f'{self.p2_round.get()} - {i+1:02d} - XLSX 第{c.row}行':i for i,c in pending}
        self.history_select.configure(values=tuple(self.history_pending))
        if self.history_select.get() not in self.history_pending:self.history_select.set(next(iter(self.history_pending),''))

    def open_p2_panel(self):
        cases=self.p2_panel_cases()
        if not self.progress or not cases:self.log('请先加载正式表并选择场景');return
        if self.history_window and self.history_window.winfo_exists():self.history_window.destroy()
        w=self.history_window=tk.Toplevel(self.root);w.title('P2 采集记录 · '+self.p2_round.get());w.transient(self.root)
        body=ttk.Frame(w,padding=14);body.pack()
        from p2_screen_pdf.tool_runner import p2_supported
        from collections import Counter
        counts=Counter(c.scenario for c in self.cases if p2_supported(c))
        self.history_categories={f'{name}（{count} 条）':name for name,count in counts.items()}
        ttk.Label(body,text='运行类别').grid(row=0,column=0,sticky='w')
        self.history_category=ttk.Combobox(body,values=tuple(self.history_categories),state='readonly',width=32)
        self.history_category.grid(row=0,column=1,sticky='w');self.history_category.bind('<<ComboboxSelected>>',lambda _:self.select_history_category())
        self.history_count=tk.StringVar(master=w);ttk.Label(body,textvariable=self.history_count).grid(row=1,column=0,columnspan=2,sticky='w')
        grid=ttk.Frame(body);grid.grid(row=2,column=0,columnspan=2,sticky='w')
        self.history_vars={};self.history_boxes={}
        for i,c in enumerate(cases):
            var=tk.BooleanVar(master=w);self.history_vars[c.case_id]=var
            box=ttk.Checkbutton(grid,variable=var,command=lambda c=c,v=var:self.toggle_p2_history(c,v))
            box.grid(row=i//7,column=i%7,padx=7,pady=7);self.history_boxes[c.case_id]=box
        actions=ttk.Frame(body);actions.grid(row=3,column=0,columnspan=2,sticky='w',pady=8)
        self.history_select=ttk.Combobox(actions,state='readonly',width=34);self.history_select.pack(side='left',padx=3)
        ttk.Button(actions,text='补测选中一条',command=lambda:self.run_p2_panel(False)).pack(side='left',padx=3)
        ttk.Button(actions,text='顺序跑完剩余',command=lambda:self.run_p2_panel(True)).pack(side='left',padx=3)
        ttk.Label(body,text='六个类别分别小循环；整表大循环从主窗口启动。续接不重发；新完整试次请新建轮。').grid(row=4,column=0,columnspan=2,sticky='w')
        ttk.Button(body,text='关闭',command=w.destroy).grid(row=5,column=0,columnspan=2,pady=8)
        self.refresh_p2_panel()

    def toggle_p2_history(self,case,var):
        if self.busy():self.refresh_p2_panel();return
        checked=var.get()
        if checked and not messagebox.askyesno('人工完成登记','确认本轮该条资料已经采集？此项只记人工，不改原证据，也不代表工具执行成功。',default='no',parent=self.history_window):
            self.refresh_p2_panel();return
        store=self.progress
        self.launch(lambda:store.mark_manual(case,checked,'用户确认本轮资料已采集' if checked else '用户取消人工登记'))

    def run_p2_all(self):
        if self.busy() or not self.progress:return
        from .progress import p2_pending
        from p2_screen_pdf.tool_runner import p2_supported
        try:
            cfg=self.config();serial=self.serial.get()
            if not serial:raise LabError('先选择设备 serial')
            cases=[c for c in self.cases if p2_supported(c)]
            jobs=[c for _,c in p2_pending(cases,self.progress.read()['cases']) if c.row!=36]
            if not jobs:self.log('本轮没有待采集项');return
            cfg['p2_batch_exclusions']={'rows':[36],'reason':'emergency_case_emulator_single_only'}
            if not messagebox.askyesno('P2 整表大循环',f'本轮按原表顺序执行六类剩余 {len(jobs)} 条。第36行保留模拟器单测，不标完成；异常保留断点和尾队列。',default='no',parent=self.root):return
            if not self.p1_confirm_tool_environment(jobs,cfg):return
        except Exception as exc:self.log(exc);return
        self.start_p2_queue(jobs,cfg,serial)

    def run_p2_panel(self, all_remaining):
        if self.busy() or not self.progress:return
        from .progress import p2_pending
        store=self.progress; cases=self.p2_panel_cases()
        try:
            config,serial=self.config(),self.serial.get()
            if not serial:raise LabError('先刷新并选择设备 serial')
            selected=self.history_pending.get(self.history_select.get())
            if selected is None and not all_remaining:raise LabError('请先选择一条未完成案例')
            jobs=p2_pending(cases,store.read()['cases'],None if all_remaining else selected)
            excluded=[c.row for _,c in jobs if all_remaining and c.row==36]
            if excluded:
                jobs=[(i,c) for i,c in jobs if c.row!=36]
                config['p2_batch_exclusions']={'rows':excluded,'reason':'emergency_case_emulator_single_only'}
            if not jobs:raise LabError('没有待跑案例')
        except Exception as exc:self.log(exc);return
        if all_remaining and not messagebox.askyesno('顺序跑完剩余',
                f'按 Excel 顺序运行剩余 {len(jobs)} 条？采集A、便签读屏、D及工具App画面；不做B/E判分。'
                + ('\n本批排除第36行紧急呼叫；该行保留为模拟器单测，不标完成。' if excluded else ''),
                default='no',parent=self.history_window):return
        if not self.p1_confirm_tool_environment([case for _,case in jobs],config,self.history_window):return
        self.start_p2_queue([case for _,case in jobs],config,serial)

    def start_p2_queue(self,cases=None,config=None,serial=None,*,engine=None,resume=False):
        if self.busy():return
        from .collection_queue import P2Queue
        self.control=control=Control()
        try:
            if engine is None:
                engine,resume=P2Queue.for_jobs(serial,cases,config,control=control,log=self.log,
                               on_case=lambda cid:self.queue.put(('p2_queue_case',cid)))
            else:
                engine.control=control;engine.on_case=lambda cid:self.queue.put(('p2_queue_case',cid))
                self.p2_round.set(f'第{engine.config["p2_round"]}轮')
                self.evidence_root.set(engine.config['evidence_root'])
                self.wait_seconds.set(str(engine.config['p2_capture_seconds']))
                self.p2_screen_capture_seconds.set(str(engine.config['p2_screen_capture_seconds']))
                self.p2_auto_recovery.set(engine.config.get('p2_auto_recovery',False))
                self.p2_recovery_attempts.set(str(engine.config.get('p2_recovery_attempts',2)))
                self.p2_reconnect_seconds.set(str(engine.config.get('p2_reconnect_seconds',30)))
            engine.continuous=True
            self.p2_round.set(f'第{engine.config["p2_round"]}轮')
            self.evidence_root.set(engine.config['evidence_root'])
            self.wait_seconds.set(str(engine.config['p2_capture_seconds']))
            self.p2_screen_capture_seconds.set(str(engine.config['p2_screen_capture_seconds']))
            self.p2_copy_post.set(engine.config.get('p2_copy_post',True))
            self.p2_post_capture_seconds.set(str(engine.config.get('p2_post_capture_seconds',90)))
            self.progress=engine.store;self.save_ui()
        except Exception as exc:self.log(exc);return
        def work():
            try:engine.execute(resume=resume)
            finally:
                if engine.runner and engine.runner.e:self.queue.put(('path',engine.runner.e.path))
                self.queue.put(('p2_progress',None))
        self.launch(work)

    def select_history_category(self):
        name=self.history_categories.get(self.history_category.get())
        if self.busy() or name is None:
            self.refresh_progress();return
        self.scenario.set(name)
        self.filter_cases()
        self.save_ui()

    def select_history_case(self):
        if self.busy():return
        selected=self.history_pending.get(self.history_select.get())
        if selected is not None:
            self.index=selected
            self.show_case()
            self.save_ui()

    def open_history(self):
        if self.pathway=='p2':return self.open_p2_panel()
        if not self.progress or not self.filtered:return
        if self.history_window and self.history_window.winfo_exists():
            self.history_window.lift();self.refresh_progress();return
        w=self.history_window=tk.Toplevel(self.root);w.title('P1 采集记录');w.transient(self.root)
        body=ttk.Frame(w,padding=14);body.pack()
        counts={}
        for c in self.cases:counts[c.scenario]=counts.get(c.scenario,0)+1
        self.history_categories={f'{name}（{count} 条）':name for name,count in counts.items()}
        ttk.Label(body,text='运行类别').grid(row=0,column=0,sticky='w')
        self.history_category=ttk.Combobox(body,values=tuple(self.history_categories),state='readonly',width=32)
        self.history_category.grid(row=0,column=1,sticky='w',pady=4)
        self.history_category.bind('<<ComboboxSelected>>',lambda _:self.select_history_category())
        self.history_count=tk.StringVar(master=w)
        ttk.Label(body,textvariable=self.history_count).grid(row=1,column=0,columnspan=2,sticky='w')
        self.history_grid=ttk.Frame(body);self.history_grid.grid(row=2,column=0,columnspan=2,sticky='w')
        self.history_vars={};self.history_boxes={}
        actions=ttk.Frame(body);actions.grid(row=3,column=0,columnspan=2,sticky='w',pady=8)
        self.history_select=ttk.Combobox(actions,state='readonly',width=33)
        self.history_select.pack(side='left',padx=3)
        self.history_select.bind('<<ComboboxSelected>>',lambda _:self.select_history_case())
        self.history_single=ttk.Button(actions,text='补测选中一条',command=lambda:self.run_history(False))
        self.history_single.pack(side='left',padx=3)
        self.history_loop=ttk.Button(actions,text='顺序跑完剩余',command=lambda:self.run_history(True))
        self.history_loop.pack(side='left',padx=3)
        ttk.Label(body,text='顺序队列只跑本轮当前类别；整表循环从主窗口启动。单条异常记入待补测。补测选中一条优先续接；页面不匹配时可从头重跑一次。').grid(
            row=4,column=0,columnspan=2,sticky='w')
        ttk.Button(body,text='关闭',command=w.destroy).grid(row=5,column=0,columnspan=2,pady=8)
        self.refresh_progress()

    def run_history(self, all_remaining):
        if self.busy() or not self.progress or not self.filtered:return
        if all_remaining:
            self.run_p1_queue(tuple(self.filtered),f'{self.scenario.get()} · 顺序跑完剩余',self.history_window)
            return
        selected=self.history_pending.get(self.history_select.get())
        if selected is None:
            self.log('请先选择一条未完成案例');return
        self.run_p1_queue((self.filtered[selected],),'单条补测',self.history_window,single=True)

    def run_p1_all(self):
        if self.pathway=='p1':
            self.run_p1_queue(tuple(self.cases),'整表循环',self.root)

    def p1_queue_preflight(self,jobs,serial,config,control):
        from p1_file_upload.tool_capture import P1ToolCapture
        checked=set()
        for case in jobs:
            if case.source_schema=='formal_ABCDE' and case.row==36:continue
            control.check()
            runner=self.p1_runner(serial,case,config,control)
            runner.validate()
            if isinstance(runner,P1ToolCapture):
                key=(runner.spec,case.row==36)
                if key not in checked:
                    runner.validate_tool_device()
                    checked.add(key)

    def p1_batch_defer_pending(self, cases, config, serial, *, expected_path=None):
        """Close only the selected round's pending case, with an audit receipt."""
        from .progress import complete_run, latest_continuation, read_run
        from .evidence import p1_recovery_round
        lease=DeviceLease(config['state_dir'],serial)
        if not lease.path.exists():return
        pending=json.loads(lease.path.read_text())
        if not pending.get('unresolved'):return
        path=latest_continuation(pending['run_dir'])
        if complete_run(path):return
        if expected_path is not None and path!=Path(expected_path).resolve():
            raise LabError('未决运行已变化，暂停队列以避免两个任务争用设备')
        result,_=read_run(path)
        round_dir=p1_round_dir(config['evidence_root'],config['p1_round'])
        allowed={c.case_id:c.workbook_sha256 for c in cases}
        if (p1_recovery_round(config['evidence_root'],path)!=round_dir or result.get('pathway')!='p1' or
                result.get('case_id') not in allowed or
                result.get('source',{}).get('workbook_sha256')!=allowed[result['case_id']]):
            raise LabError('设备有其他轮次或实验范围的未决任务，保留原任务')
        lease.acknowledge('GUI 单遍队列：本条留待补测，不重发，保留原证据',expected_run=pending['run_dir'])
        self.log('未决断点留待补测：'+path.name)

    def run_p1_queue(self, scope, label, parent, *, single=False, resume_config=None):
        if self.busy() or not self.progress or not scope:return
        store=self.progress
        try:
            config,serial=dict(resume_config) if resume_config is not None else self.config(),self.serial.get()
            if not serial:raise LabError('先刷新并选择设备 serial')
            if any(c.source_schema!='formal_ABCDE' for c in scope):
                raise LabError('队列仅用于正式 XLSX；样例请在主窗口单次运行')
            from .p1_handover import handover_stopped_run
            change=handover_stopped_run(config,serial,store.workbook_hash)
            if change['changed']:self.log('已交接旧轮控制权；证据和剩余队列保留，启动当前新轮')
            data=store.read()['cases']
            excluded=[c for c in scope if c.source_schema=='formal_ABCDE' and c.row==36]
            if excluded:self.log('已排除 XLSX 第36行：不预检、不执行、不标记完成；整表可运行范围为其余102条')
            jobs=sorted((c for c in scope if not (c.source_schema=='formal_ABCDE' and c.row==36)
                         and not store.checked(data.get(c.case_id,{}))),key=lambda c:c.row)
            if not jobs:raise LabError('本轮所选范围已经完成')
            missing=[str(c.row) for c in jobs if not self.p1_route(c)]
            if single and missing:raise LabError('此 XLSX 行尚无运行适配')
            if not single and not messagebox.askyesno(
                    label,f'{self.p1_round.get()}：按 XLSX 第{jobs[0].row}行到第{jobs[-1].row}行顺序跑 {len(jobs)} 条。'
                    '\n本次每条尝试一次：旧失败重新补测，已发送阶段只续接；单条异常留档后继续，不自动换轮。',
                    default='no',parent=parent):return
            if not self.p1_confirm_tool_environment(jobs,config,parent):return
            if not single:config['gui_direct_batch']=True
            if single:
                case=jobs[0]
                recorded=data.get(case.case_id,{}).get('run_dir')
                original=p1_case_path(config['evidence_root'],case,config['p1_round'])
                if recorded or original.exists():
                    confirmed={k:config[k] for k in ('outbound_test_confirmed','home_test_confirmed') if k in config}
                    self.resume_run(selected_case=case,selected_path=recorded or original,confirmed=confirmed)
                    return
                if not self.p1_prepare_new(jobs,config,serial,parent):return
        except (OSError, ValueError, LabError) as exc:
            self.log(exc);return
        self.control=control=Control()
        def work():
            from .p1_queue_recovery import queued_run_path,pending_first,prepare_attempt
            from .progress import complete_run
            report=None;deferred={}
            folder=p1_round_dir(config['evidence_root'],config['p1_round'])
            if not single:
                report=folder/('.待补测-'+store.workbook_hash[:16]+'.json')
                if report.exists():deferred=json.loads(report.read_text())
            # A prior report records outcomes, never which jobs to skip on a new click.
            def persist():
                if report is not None:
                    report.parent.mkdir(parents=True,exist_ok=True);atomic_json(report,deferred)
            for cid,entry in store.read()['cases'].items():
                if store.checked(entry):deferred.pop(cid,None)
            for case in excluded:deferred.pop(case.case_id,None)
            persist()
            ordered,overrides=pending_first(jobs,config,serial)
            from .p1_reliability import QueueJournal
            journal=QueueJournal(config,store.workbook_hash,serial)
            config['p1_queue_journal_path']=str(journal.path)
            with journal.session([c.case_id for c in ordered],config):
                self.log(f'{label}：准备处理 {len(ordered)} 条未完成项；旧失败重新尝试，已发送阶段只续接')
                attempted=finished=failed=0
                for case in ordered:
                    control.check()
                    entry=store.read()['cases'].get(case.case_id,{})
                    if store.checked(entry):
                        journal.case_finished(case.case_id,'collection_complete',entry.get('run_dir'))
                        deferred.pop(case.case_id,None);persist();continue
                    journal.case_started(case.case_id)
                    self.queue.put(('p1_queue_case',(case.scenario,case.case_id)))
                    runner=None;evidence_path=None
                    try:
                        if not self.p1_route(case):raise LabError('此行尚无运行适配')
                        evidence_path=overrides.get(case.case_id) or queued_run_path(case,config,entry,deferred.get(case.case_id))
                        if evidence_path is not None and complete_run(evidence_path):
                            store.record(case,evidence_path,'complete','complete',allow_auto=True)
                            journal.case_finished(case.case_id,'collection_complete',evidence_path)
                            deferred.pop(case.case_id,None);persist()
                            self.log(f'XLSX 第{case.row}行：已有完整证据，已同步完成登记');continue
                        runner,kwargs,mode=prepare_attempt(self.p1_runner,serial,case,config,control,
                            path=evidence_path,log=self.log,review=self.review_p1_tool)
                        self.log(f'第{config["p1_round"]}轮 · {label}：XLSX 第{case.row}行（{case.scenario}） · {mode}')
                        attempted+=1
                        path=runner.execute(**kwargs)
                        entry=store.read()['cases'].get(case.case_id,{})
                        if not path or not entry.get('auto_complete') or entry.get('auto_run')!=str(Path(path).resolve()):
                            raise LabError('未通过采集完成登记')
                        journal.case_finished(case.case_id,'collection_complete',path)
                        finished+=1;deferred.pop(case.case_id,None);persist()
                        self.log(f'队列进度：已尝试 {attempted}/{len(ordered)}，本次完成 {finished}，本次失败 {failed}')
                    except (Stopped, DeviceDisconnected, ObservationUnavailable, NewChatBlocked) as exc:
                        if runner is not None and runner.e:evidence_path=runner.e.path
                        deferred[case.case_id]={'xlsx_row':case.row,'reason':str(exc),'evidence':str(evidence_path) if evidence_path else None}
                        persist();self.log('采集暂停/异常终止：当前断点与剩余队列已保存；点继续未完成恢复，不重发')
                        if isinstance(exc,NewChatBlocked):raise ObservationUnavailable(str(exc),'new_chat_unavailable') from exc
                        raise
                    except Exception as exc:
                        if single:raise
                        failed+=1
                        if runner is not None and runner.e:evidence_path=runner.e.path
                        deferred[case.case_id]={'xlsx_row':case.row,'reason':str(exc),
                            'evidence':str(evidence_path) if evidence_path else None}
                        journal.case_finished(case.case_id,'needs_attention',evidence_path)
                        persist();self.log(f'XLSX 第{case.row}行本次失败：{exc}；已记录，继续下一条')
                        if evidence_path is not None:
                            self.p1_batch_defer_pending((case,),config,serial,expected_path=evidence_path)
                    finally:
                        if runner is not None and runner.e:self.queue.put(('path',runner.e.path))
                final_entries=store.read()['cases']
                remaining=sum(not store.checked(final_entries.get(c.case_id,{})) for c in jobs)
                self.log(f'{label}本次队列结束：实际尝试 {attempted} 条，完成 {finished} 条，失败 {failed} 条；'
                         f'本范围仍未完成 {remaining} 条'+(f'；清单：{report}' if report else ''))
        self.launch(work)

    def toggle_history(self,case,var):
        if self.busy():self.refresh_progress();return
        checked=var.get()
        if checked and not messagebox.askyesno('人工完成登记','确认这条所需阶段与工具调用画面均已采集（不代表动作落地或实验命中）？\n此勾选记为“人工”，不改写程序验收结果。',parent=self.history_window):
            self.refresh_progress();return
        store=self.progress
        self.launch(lambda:store.mark_manual(case,checked,'用户确认全部流程完成' if checked else '用户取消登记，原证据保留'))

    def resume_p2_run(self):
        if self.busy():return
        try:
            serial=self.serial.get()
            if not serial:raise LabError('先选择原设备 serial')
            registry=DeviceLease(self.state_dir,serial).path
            pending=json.loads(registry.read_text()) if registry.exists() else {}
            path=pending.get('run_dir') if pending.get('unresolved') else self.last_path
            from .p1_reliability import QueueJournal
            from .collection_queue import P2Queue
            config=self.config()
            journal=QueueJournal(config,self.cases[0].workbook_sha256,serial,pathway='p2') if self.cases else None
            if pending.get('unresolved'):
                from .progress import read_run
                source,_=read_run(pending['run_dir'])
                saved_queue=source.get('config',{}).get('p2_queue_journal_path')
                queue_path=Path(saved_queue) if saved_queue else None
            else:queue_path=journal.path if journal else None
            if not pending.get('unresolved') and self.cases:
                from .progress import p2_pending
                category=self.p2_panel_cases()
                desired=[c for _,c in p2_pending(category,self.progress.read()['cases']) if c.row!=36]
                if not desired:
                    desired=[c for _,c in p2_pending(self.cases,self.progress.read()['cases']) if c.row!=36]
                queue_path=P2Queue.choose_resume_journal(config,serial,self.cases[0].workbook_sha256,desired)
                if queue_path is None and desired:
                    self.log('没有未结束的原队列；自动建立待采集项的补测批次，不用选文件')
                    self.start_p2_queue(desired,config,serial);return
                if queue_path is None and not desired:
                    self.log('本轮全部项目均已登记，没有需要继续的任务');return
            if queue_path and queue_path.exists():
                engine=P2Queue.from_journal(queue_path,serial,log=self.log)
                if not self.cases or engine.workbook_hash!=self.cases[0].workbook_sha256:
                    raise LabError('先载入原队列的源表')
                self.log('恢复冻结完整队列与尾部顺序，不采用当前界面新预算')
                self.start_p2_queue(engine=engine,resume=True);return
            if not path:raise LabError('没有可继续的 P2 断点')
            from .progress import latest_continuation, read_run
            from p2_screen_pdf.tool_runner import p2_from_run
            path=latest_continuation(path)
            result,_=read_run(path)
            if not self.cases or result['source']['workbook_sha256']!=self.cases[0].workbook_sha256:
                raise LabError('先加载原 P2 源表，不更换冻结案例')
            control=Control()
            runner=p2_from_run(serial,path,control=control,log=self.log,state_dir=self.state_dir)
        except Exception as exc:self.log(exc);return
        self.control=control
        def resume():
            try:runner.execute(resume_from=path)
            finally:
                if runner.e:self.queue.put(('path',runner.e.path))
        self.launch(resume)

    def resume_run(self, *, selected_case=None, selected_path=None, confirmed=None):
        if self.busy() or not self.progress:return
        if selected_case is None and selected_path is None and getattr(self,'pathway',None)=='p1':
            from .p1_reliability import pending_queue
            cfg=self.config();pending=pending_queue(cfg,self.progress.workbook_hash,self.serial.get())
            if pending:
                scope=[c for cid in pending['remaining'] for c in self.cases if c.case_id==cid]
                if scope:
                    self.log(f'恢复已保存整表队列：剩余 {len(scope)} 条，先处理未决断点')
                    self.run_p1_queue(scope,'恢复整表队列',self.root,resume_config=pending['config']);return
        entry={'run_dir':selected_path} if selected_path is not None else self.progress.latest_unfinished(self.cases)
        serial=self.serial.get()
        if serial:
            registry=DeviceLease(self.state_dir,serial).path
            if registry.exists():
                try:
                    pending=json.loads(registry.read_text())
                    if pending.get('unresolved') and selected_case is None:entry={'run_dir':pending['run_dir']}
                except (OSError,ValueError,KeyError):pass
        if not entry and selected_path is None:
            scoped=[c for c in self.cases if c.scenario==self.scenario.get()]
            entry=self.progress.retry_candidate(scoped) or self.progress.retry_candidate(self.cases)
            if entry:self.log('继续未完成：恢复本轮已归档/待补测记录，不把失败尝试当作完成')
        if not entry:
            self.log('没有可继续的未完成运行；已完成证据和勾选保留');return
        path=Path(entry['run_dir'])
        if not serial:self.log('先选择原设备 serial');return
        from .progress import read_run,latest_continuation
        try:
            path=latest_continuation(path)
            if not path.exists():raise LabError('原运行目录已不在原路径：'+str(path)+'；找回原目录后再继续，勿重复发送')
            result,_=read_run(path)
            from .evidence import interrupted_organization_sources
            if result.get('status')=='complete' and interrupted_organization_sources(path) is None:raise LabError(f'该任务已完成，证据在 {path.parent.name}；不再次续接')
            if result['source']['workbook_sha256']!=self.cases[0].workbook_sha256:raise LabError('源表版本不同，请先载入原表')
            c=next(c for c in self.cases if c.case_id==result['case_id'])
            if c.row==36:raise LabError('XLSX 第36行仍排除，不续跑')
            from .evidence import p1_recovery_round
            original_root=Path(self.evidence_root.get()).expanduser().resolve()
            folder=p1_recovery_round(original_root,path)
            if folder!=self.selected_p1_round_dir():raise LabError('断点不在当前选择轮次，保留原记录')
            if selected_case is not None and (c.case_id!=selected_case.case_id or
                                               folder!=self.selected_p1_round_dir()):
                raise LabError('所选补测与旧证据不在同一 Case 或同一轮')
            if folder is None:raise LabError('旧证据不在编号轮次内，只保留查看；不自动新建轮次')
            self.evidence_root.set(str(original_root))
            self.p1_round.set(folder.name)
            number=self.selected_p1_round_number()
            self.refresh_p1_rounds()
            from .progress import ProgressStore
            self.progress=ProgressStore(self.state_dir,c.workbook_sha256,'p1',round_dir=folder)
            self.progress.import_run(path)
            self.scenario.set(c.scenario);self.filter_cases();self.index=self.filtered.index(c);self.show_case()
            self.injection_wait_seconds.set(str(result['config'].get('injection_wait_seconds',60)))
        except Exception as exc:self.log(exc);return
        self.control=Control();control=self.control;state_dir=self.state_dir
        def resume():
            def restart(old_path, old_result, runner_config):
                config=dict(runner_config, p1_round=number, state_dir=str(state_dir),
                            evidence_root=str(original_root))
                config.setdefault('p1_injection_mode', 'chat_c_v1')
                config.pop('fast_response_budget_seconds',None)
                config.update(confirmed or {})
                config.update(p1_auto_recovery=True,p1_recovery_attempts=2,p1_reconnect_seconds=30)
                self.log(f'{c.case_id}：旧会话无法继续（{old_result.get("error","无法继续")}）；本条从 A 重新开始，仅一次')
                fresh=self.p1_runner(serial,c,config,control)
                try:fresh.execute(restart_from=old_path)
                finally:
                    if fresh.e:self.queue.put(('path',fresh.e.path))

            if not result.get('submissions') and (p1_observation_restart_eligible(result) or p1_unsubmitted_baseline_restart_eligible(result)):
                restart(path,result,result['config'])
                return
            from p1_file_upload.runner import P1Runner
            if result.get('config',{}).get('p1_tool_pilot')==1:
                from p1_file_upload.tool_pilot import P1ToolPilot
                runner=P1ToolPilot.from_run(serial,path,control=control,log=self.log,state_dir=state_dir)
                runner.review=self.review_p1_tool
            elif result.get('config',{}).get('p1_tool_capture')==1:
                from p1_file_upload.tool_capture import P1ToolCapture
                runner=P1ToolCapture.from_run(serial,path,control=control,log=self.log,state_dir=state_dir)
            else:
                runner=P1Runner.from_run(serial,path,control=control,log=self.log,state_dir=state_dir)
            runner.config.update(confirmed or {})
            runner.config.update(p1_auto_recovery=True,p1_recovery_attempts=2,p1_reconnect_seconds=30)
            runner.config['p1_round']=number
            runner.config['evidence_root']=str(original_root)
            try:
                runner.execute(resume_from=path)
            except LabError:
                if runner.e is None or runner.e.result.get('submissions') or not p1_observation_restart_eligible(runner.e.result):
                    raise
                restart(runner.e.path,runner.e.result,runner.config)
            finally:
                if runner.e and not p1_observation_restart_eligible(runner.e.result):
                    self.queue.put(('path',runner.e.path))
        self.save_ui();self.launch(resume)


def main(pathway):
    root = tk.Tk()
    window = LabWindow(root, pathway, smoke='--smoke' in sys.argv)
    if '--smoke' in sys.argv:
        print('GUI_SMOKE ' + pathway + ' controls=' + str(len(window.inputs)) + ' no_device_actions')
        root.after(200, root.destroy)
    root.mainloop()
