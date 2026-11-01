"""Manual experiment registration; this window neither connects to nor commands a phone."""
import tkinter as tk
from tkinter import ttk,messagebox
from catalog import SIZES,GRAYS

class History:
    def __init__(self,parent,progress,font,on_change,on_close):
        self.progress,self.on_change,self.on_close=progress,on_change,on_close
        w=self.window=tk.Toplevel(parent)
        w.title('实验记录');w.transient(parent);w.resizable(False,False)
        body=ttk.Frame(w,padding=16);body.grid()
        self.font=tk.StringVar(w,value=f'{font} px')
        self.count=tk.StringVar(w)
        header=ttk.Frame(body);header.grid(row=0,column=0,columnspan=8,sticky='ew')
        ttk.Label(header,text='字号').pack(side='left')
        self.sizes=ttk.Combobox(header,textvariable=self.font,state='readonly',width=7,
                                values=[f'{x} px' for x in SIZES])
        self.sizes.pack(side='left',padx=(5,14))
        self.sizes.bind('<<ComboboxSelected>>',lambda _:self.refresh())
        ttk.Label(header,textvariable=self.count).pack(side='right')
        ttk.Label(body,text='只勾选你已经登记结果的档位。勾选即保存，不启动手机。').grid(
            row=1,column=0,columnspan=8,sticky='w',pady=(10,6))
        self.variables={};self.cells={}
        for i,g in enumerate(GRAYS):
            v=self.variables[g]=tk.BooleanVar(w)
            box=self.cells[g]=ttk.Checkbutton(body,text=f'g{g}',variable=v,command=lambda g=g:self.toggle(g))
            box.grid(row=2+i//8,column=i%8,sticky='w',padx=(0,7),pady=4)
        foot=ttk.Frame(body);foot.grid(row=6,column=0,columnspan=8,sticky='ew',pady=(12,0))
        self.clear_button=ttk.Button(foot,text='清空登记…',command=self.clear)
        self.clear_button.pack(side='left')
        ttk.Button(foot,text='完成',command=self.close).pack(side='right')
        w.protocol('WM_DELETE_WINDOW',self.close)
        w.bind('<Escape>',lambda _:self.close())
        self.refresh()
        w.grab_set()
    def refresh(self):
        f=int(self.font.get().split()[0]);marks=self.progress.registered()
        for g,v in self.variables.items():v.set((f,g) in marks)
        self.count.set(f'本字号 {sum(ff==f for ff,_ in marks)} / 32   ·   共 {len(marks)} / 192')
        self.clear_button.configure(state='normal' if marks else 'disabled')
    def toggle(self,g):
        f=int(self.font.get().split()[0])
        try:self.progress.set_registered(f,g,self.variables[g].get())
        except OSError as e:messagebox.showerror('未保存',str(e),parent=self.window)
        self.refresh();self.on_change()
    def clear(self):
        n=len(self.progress.registered())
        if not n:return
        ok=messagebox.askyesno('清空登记',f'清空当前设备和素材目录下 6 个字号的全部 {n} 个勾选？\n已执行记录、下次档位和运行日志都会保留。',
                               parent=self.window,default='no',icon='warning')
        if not ok:return
        try:self.progress.clear_history()
        except OSError as e:messagebox.showerror('未清空',str(e),parent=self.window)
        self.refresh();self.on_change()
    def close(self):
        self.window.grab_release();self.window.destroy();self.on_close()
