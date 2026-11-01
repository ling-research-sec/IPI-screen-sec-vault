#!/usr/bin/env python3
"""Desktop entrypoint. --preflight never starts a round."""
import argparse
import json
from pathlib import Path
import os
import queue
import threading
from time import monotonic
from android import connect, Device, Problem, Stopped
from catalog import SIZES, GRAYS, Progress
from round_flow import Flow

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
        self.r.protocol('WM_DELETE_WINDOW',self.close)
        self.r.after(70,self.pump)
        self.preflight()

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
        self.message.set('此张已执行到共享终点；再次点击会重做本张。' if done else '就绪 · 每次只执行一张')

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
        # Ignore an immediate double click, but allow Stop during the 0.5 s countdown.
        self.mode='running';self.cancel.clear();self.armed=monotonic()+.20
        f=int(self.f.get().split()[0]);g=int(self.g.get().split()[0][1:])
        for b in self.boxes:b.configure(state='disabled')
        self.history_btn.configure(state='disabled')
        self.btn.configure(text='停止本轮')
        def work():
            step='开始'; name=self.cat.files[f,g]
            def update(s):
                nonlocal step
                step=s
                audit(event='step',font=f,gray=g,step=s)
                self.q.put(('step',s))
            self.progress.started(f,g)
            audit(event='manual_start',font=f,gray=g,file=name)
            try:
                result=Flow(Device(self.cat.serial,self.cancel),self.cat,f,g,update).run()
            except Exception as e:
                audit(event='not_completed',font=f,gray=g,step=step,error=str(e))
                raise
            self.progress.completed(f,g)
            audit(event='completed',font=f,gray=g,file=name,verification=result)
            self.q.put(('done',(f,g)))
        self.launch(work)

    def pump(self):
        while not self.q.empty():
            kind,data=self.q.get()
            if kind=='step': self.message.set(data+'…')
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
