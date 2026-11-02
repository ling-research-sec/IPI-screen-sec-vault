#!/usr/bin/env python3
"""Desktop entrypoint. --preflight never starts a round."""
import argparse
import json
from pathlib import Path
import os
import queue
import threading
import subprocess
from time import monotonic
from android import connect, Device, Problem, Stopped
from catalog import SIZES, GRAYS, Progress
from round_flow import Flow
from live_wait import LiveWait
from capture import capture_answer,seconds
from playback import play_after_success

HOME=Path(os.environ.get('GPT_SINGLE_HOME',Path.home()/'Library'/'Application Support'/'GPT-Advanced-Single'))

def audit(**item):
    from datetime import datetime, timezone
    HOME.mkdir(parents=True,exist_ok=True)
    with (HOME/'rounds.jsonl').open('a') as f:
        f.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),**item),ensure_ascii=False)+'\n')

def summary(cat):
    return {'folder':cat.folder,'device':cat.serial,'images':len(cat.files),
            'sizes_px':list(SIZES),'gray_count_per_size':len(GRAYS),
            'first':cat.files[SIZES[0],1],'last':cat.files[SIZES[-1],32]}

def round_plan(font,gray,loop,full):
    sizes=SIZES[SIZES.index(font):] if full else (font,)
    return [(f,g) for f in sizes for g in
            range(gray if f==font else 1,33 if (loop or full) else gray+1)]

class Window:
    def __init__(self,root):
        import tkinter as tk
        from tkinter import ttk
        self.r=root
        root.title('GPT Advanced · 单张执行')
        root.resizable(False,False)
        self.q=queue.Queue()
        self.worker=None
        self.cancel=threading.Event()
        self.mode='loading'; self.cat=None; self.progress=None
        self.closing=False; self.armed=0; self.history=None
        panel=ttk.Frame(root,padding=20)
        panel.grid()
        self.f=tk.StringVar(value='16 px');self.g=tk.StringVar(value='g1')
        self.file=tk.StringVar();self.message=tk.StringVar(value='正在预检…')
        self.boxes=[]
        for i,(title,var,vals) in enumerate((('字号',self.f,[f'{x} px' for x in SIZES]),('灰度',self.g,[f'g{x}' for x in GRAYS]))):
            ttk.Label(panel,text=title).grid(row=0,column=i,sticky='w',padx=(0,12))
            box=ttk.Combobox(panel,textvariable=var,values=vals,width=14,state='disabled')
            box.grid(row=1,column=i,sticky='ew',padx=(0,8*i))
            box.bind('<<ComboboxSelected>>',lambda e,i=i:self.selection(i))
            self.boxes.append(box)
        ttk.Label(panel,textvariable=self.file).grid(row=2,column=0,sticky='w',pady=(10,8))
        self.history_btn=ttk.Button(panel,text='实验记录',command=self.open_history,state='disabled')
        self.history_btn.grid(row=2,column=1,sticky='e',pady=(10,8))
        self.btn=ttk.Button(panel,text='预检中…',command=self.click,state='disabled')
        self.btn.grid(row=3,column=0,columnspan=2,sticky='ew')
        ttk.Label(panel,textvariable=self.message,wraplength=335).grid(row=4,column=0,columnspan=2,sticky='w',pady=(10,0))
        self.loop=tk.BooleanVar(value=False);self.wait_seconds=tk.StringVar(value='12')
        options=ttk.Frame(panel);options.grid(row=5,column=0,columnspan=2,sticky='ew',pady=(9,0))
        ttk.Label(options,text='播完后等（秒）').pack(side='left')
        self.wait_box=ttk.Entry(options,width=6,textvariable=self.wait_seconds)
        self.wait_box.pack(side='left',padx=4)
        self.live_wait=LiveWait(12)
        ttk.Label(options,text='↵ 应用').pack(side='left')
        self.wait_box.bind('<Return>',self.apply_wait)
        self.wait_box.bind('<FocusOut>',self.apply_wait)
        self.loop_box=ttk.Checkbutton(options,text='循环至 g32',variable=self.loop)
        self.loop_box.pack(side='right')
        self.full=tk.BooleanVar(value=False)
        self.full_box=ttk.Checkbutton(options,text='全循环',variable=self.full,command=self.sync_modes)
        self.full_box.pack(side='right')
        ttk.Button(panel,text='打开截图目录',command=self.open_captures).grid(row=6,columnspan=2,sticky='ew',pady=(8,0))
        self.r.protocol('WM_DELETE_WINDOW',self.close)
        self.r.after(70,self.pump)
        self.preflight()

    def open_captures(self):
        folder=HOME/'captures'
        if self.cat:folder=folder/self.cat.key/(self.f.get().split()[0]+'px')
        folder.mkdir(parents=True,exist_ok=True)
        subprocess.Popen(['/usr/bin/open',str(folder)])

    def launch(self,fn):
        def work():
            try: fn()
            except Exception as e:
                self.q.put(('error',str(e)))
        self.worker=threading.Thread(target=work,daemon=True)
        self.worker.start()

    def preflight(self):
        self.mode='loading'
        self.btn.configure(state='disabled',text='预检中…')
        self.message.set('只读核对手机和图片目录…')
        def fn():
            cat=connect(self.cancel).inspect()
            self.q.put(('ready',(cat,Progress(HOME/'progress.json',cat.key))))
        self.launch(fn)

    def open_history(self):
        if self.mode!='idle' or self.closing:return
        if self.history is not None:
            self.history.window.lift()
            return
        from history import History
        self.history=History(self.r,self.progress,int(self.f.get().split()[0]),
                             self.refresh_from_history,self.history_closed)

    def refresh_from_history(self):
        self.selection(1)

    def history_closed(self):
        self.history=None

    def selection(self,i):
        if self.mode!='idle':return
        f=int(self.f.get().split()[0])
        g=self.progress.next(f) if i==0 else int(self.g.get().split()[0][1:])
        marks=self.progress.registered()
        labels=[f'g{x} ✓' if (f,x) in marks else f'g{x}' for x in GRAYS]
        self.boxes[1].configure(values=labels)
        self.g.set(labels[g-1])
        self.history_btn.configure(text=f'实验记录 · {len(marks)}/192',state='normal')
        self.file.set(self.cat.files[f,g])
        done=[f,g] in self.progress.state['done']
        self.btn.configure(text=f'{"再次执行" if done else "执行"}  {f} px · g{g}',state='normal')
        if self.progress.state.get('pending')==[f,g]:
            self.message.set('上次此张未确认完成；请核实手机后再手工执行。')
            return
        self.message.set('此张已执行到共享终点；再次点击会重做本张。' if done else '就绪 · 点击执行开始采集')

    def apply_wait(self,event=None):
        try:value=seconds(self.wait_seconds.get())
        except Problem as e:
            self.message.set(f'{e} 仍使用 {self.live_wait.value:g} 秒。')
            return False
        self.live_wait.set(value)
        self.message.set(f'播完后等待：{value:g} 秒')
        return True

    def sync_modes(self):
        if self.full.get():self.loop.set(True)
        self.loop_box.configure(state='disabled' if self.full.get() else 'normal')

    def click(self):
        if self.history is not None or self.closing:return
        if self.mode=='error':
            self.preflight()
            return
        if self.mode=='running':
            if monotonic()>self.armed:
                self.cancel.set()
                self.btn.configure(text='正在停止…',state='disabled')
            return
        if self.mode!='idle' or monotonic()<self.armed:return
        if not self.apply_wait():return
        looping=self.loop.get();full=self.full.get()
        self.full_box.configure(state='disabled')
        self.loop_box.configure(state='disabled')
        # Ignore an immediate double click, but allow Stop during the 0.5 s countdown.
        self.mode='running';self.cancel.clear();self.armed=monotonic()+.20
        f=int(self.f.get().split()[0]);g=int(self.g.get().split()[0][1:])
        for b in self.boxes:b.configure(state='disabled')
        self.history_btn.configure(state='disabled')
        self.btn.configure(text='停止本轮')
        plan=round_plan(f,g,looping,full)
        def work():
            d=Device(self.cat.serial,self.cancel)
            for i,(f,current) in enumerate(plan):
                if self.cancel.is_set():raise Stopped('已停止。')
                step='开始';name=self.cat.files[f,current]
                self.q.put(('current',(f,current)))
                def update(s):
                    nonlocal step
                    step=s
                    audit(event='step',font=f,gray=current,step=s)
                    self.q.put(('step',f'{f} px · g{current}：'+s))
                self.progress.started(f,current)
                audit(event='manual_start' if i==0 else 'loop_start',font=f,gray=current,file=name)
                try:
                    result=Flow(d,self.cat,f,current,update).run()
                    play_after_success(self.cancel,update)
                    evidence=capture_answer(d,self.live_wait,HOME/'captures'/self.cat.key/f'{f}px',name,update)
                    self.progress.completed(f,current,captured=True)
                    audit(event='completed',font=f,gray=current,file=name,verification=result,**evidence)
                except Exception as e:
                    audit(event='not_completed',font=f,gray=current,step=step,error=str(e))
                    raise
                if i+1==len(plan):
                    self.q.put(('done',(f,current)));return
                self.q.put(('current',plan[i+1]))
                update('截图已保存，2 秒后继续')
                if self.cancel.wait(2):raise Stopped('循环已停止；上一张截图已保存。')
        self.launch(work)

    def pump(self):
        while not self.q.empty():
            kind,data=self.q.get()
            if kind=='current':
                f,g=data;self.f.set(f'{f} px');self.g.set(f'g{g}');self.file.set(self.cat.files[f,g])
            elif kind=='step': self.message.set(data+'…')
            elif kind=='ready':
                self.cat,self.progress=data
                self.f.set(f"{self.progress.state['font']} px")
                self.mode='idle'
                for b in self.boxes:b.configure(state='readonly')
                self.selection(0)
            elif kind in ('done','error'):
                if self.mode=='loading':
                    self.mode='error';self.btn.configure(text='重新预检',state='normal')
                    self.message.set(data)
                    continue
                self.wait_box.configure(state='normal');self.full_box.configure(state='normal');self.sync_modes()
                self.mode='idle';self.armed=monotonic()+.65
                for b in self.boxes:b.configure(state='readonly')
                if kind=='done':
                    f,g=data;self.g.set(f'g{min(32,g+1)}')
                self.selection(1)
                self.message.set((f'g{g} 完成 · '+('本字号末档，已停。' if g==32 else f'下次点击才执行 g{g+1}')) if kind=='done' else data)
        if self.closing and (self.worker is None or not self.worker.is_alive()):
            self.r.destroy();return
        self.r.after(70,self.pump)

    def close(self):
        self.closing=True;self.cancel.set()
        if self.history is not None:self.history.close()
        self.history_btn.configure(state='disabled')
        self.btn.configure(text='正在关闭…',state='disabled')
        for b in self.boxes:b.configure(state='disabled')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--preflight',action='store_true',help='只读检查手机，不执行任何一轮')
    args=parser.parse_args()
    if args.preflight:
        print(json.dumps(summary(connect().inspect()),ensure_ascii=False,indent=2))
        return
    import fcntl
    import tkinter as tk
    from tkinter import messagebox
    HOME.mkdir(exist_ok=True,parents=True)
    with (HOME/'window.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            r=tk.Tk();r.withdraw();messagebox.showinfo('单张执行','窗口已经打开。');r.destroy();return
        r=tk.Tk();Window(r);r.mainloop()

if __name__=='__main__':
    try:main()
    except Problem as e:raise SystemExit(str(e))
