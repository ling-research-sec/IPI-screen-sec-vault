"""Read-only preflight, and Android UI primitives used only after a manual start."""
import os
from pathlib import PurePosixPath
import re
import shlex
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from catalog import Catalog, Problem

GPT = 'com.openai.chatgpt'
FILES = 'com.android.documentsui'
SYS = 'com.android.systemui'
VIEW = 'org.lineageos.glimpse'
ADIR = re.compile(r'GPT[-_ ]Advanced(?:[-_ ][\w.-]+)*',re.I)

class Stopped(Problem):
    pass

class Device:
    def __init__(self, serial='', stop=None):
        self.serial,self.stop = serial,stop
        self.adb = os.environ.get('ADB') or shutil.which('adb')
        if not self.adb:
            raise Problem('未找到 adb，请安装 Android Platform Tools。')

    def check(self):
        if self.stop and self.stop.is_set():
            raise Stopped('已停止；编号保持不变。')

    def delay(self, t):
        if self.stop is None:
            time.sleep(t)
        elif self.stop.wait(t):
            self.check()

    def call(self, *args, timeout=10):
        self.check()
        try:
            p=subprocess.run([self.adb,*(['-s',self.serial] if self.serial else []),*args],
                             capture_output=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired) as e:
            raise Problem('ADB 无响应，请检查 USB 连接。') from e
        self.check()
        if p.returncode:
            raise Problem('ADB 命令失败：'+' '.join(args[:1])+'；请检查连接和手机界面。')
        return p.stdout.decode('utf-8','replace').strip()

    def shell(self,*words):
        return self.call('shell',shlex.join(words))

    def foreground(self):
        # Activity transitions briefly expose no resumed activity. Retry fresh
        # snapshots, never substitute a cached/paused/focused activity.
        until=time.monotonic()+3
        while True:
            self.check()
            s=self.shell('dumpsys','activity','activities')
            m=re.search(r'topResumedActivity=ActivityRecord\{[^\n]*?\bu\d+ ([\w.$]+)/([\w.$]+) t(\d+)',s)
            if m:return m.groups()
            if time.monotonic()>=until:
                raise Problem('前台页面在切换后仍未就绪，请确认手机已解锁。')
            self.delay(.15)

    def projection(self):
        s=self.shell('dumpsys','media_projection')
        if re.search(r'Media Projection:\s*null\b',s): return 'none'
        if re.search(r'(?m)^\s*packageName:\s*com\.openai\.chatgpt\s*$',s): return 'gpt'
        return 'unknown'

    def sharing_task(self, task_id):
        s=self.shell('dumpsys','media_projection')
        return (bool(re.search(r'(?m)^\s*packageName:\s*com\.openai\.chatgpt\s*$',s))
                and bool(re.search(r'(?m)^\s*taskId to mirror:\s*'+re.escape(task_id)+r'\s*$',s))
                and 'contentToRecord = RECORD_CONTENT_TASK' in s and 'waitingForConsent = false' in s)

    def inspect(self):
        names=self.shell('ls','-1','/sdcard/Pictures').splitlines()
        dirs=[n for n in names if ADIR.fullmatch(n)]
        if len(dirs)!=1: raise Problem('Pictures 中应有唯一的 GPT-Advanced 图片目录。')
        folder='/sdcard/Pictures/'+dirs[0]
        names=[PurePosixPath(p).name for p in self.shell('find',folder,'-maxdepth','1','-type','f').splitlines()]
        for pkg in (GPT,FILES,VIEW):
            if 'package:' not in self.shell('pm','path',pkg): raise Problem('手机缺少所需应用：'+pkg)
        return Catalog.parse(self.serial,folder,names)

    def usable(self):
        if 'mWakefulness=Awake' not in self.shell('dumpsys','power'):
            raise Problem('请点亮并解锁手机。')
        if re.search(r'\bshowing=true\b',self.shell('dumpsys','window','policy')):
            raise Problem('请先解锁手机。')
        if self.projection()=='unknown': raise Problem('检测到其他或未知屏幕共享，请先结束。')

    def tree(self,windows=False):
        data=self.call('exec-out','uiautomator','dump',*(['--windows'] if windows else []),'/dev/tty',timeout=12)
        start=data.find('<?xml')
        closing='</displays>' if windows else '</hierarchy>'
        end=data.rfind(closing)
        if start<0 or end<0: raise Problem('手机界面尚未稳定。')
        try: return Screen(ET.fromstring(data[start:end+len(closing)]))
        except ET.ParseError as e: raise Problem('页面结构未读完整。') from e

    def wait(self,fn,why,timeout=18):
        until=time.monotonic()+timeout
        while True:
            self.check()
            v=fn()
            if v: return v
            if time.monotonic()>=until: raise Problem(why)
            self.delay(.25)

    def page(self,pkg):
        if self.foreground()[0]!=pkg: return None
        try: s=self.tree()
        except Stopped: raise
        except Problem as e:
            if '界面尚未稳定' in str(e): return None
            raise
        return s if pkg in s.packages else None

    def expect(self,pkg):
        return self.wait(lambda:self.page(pkg),'未到达预期页面：'+pkg)

    def checked_input(self,pkg,*action):
        if self.foreground()[0]!=pkg: raise Problem('前台已变化，停止发送动作。')
        self.shell('input',*map(str,action))

    def tap(self,pkg,target):
        self.checked_input(pkg,'tap',*target)

    def press(self,pkg,labels,why,rids=(),area=None,*,first_page=None):
        def probe():
            screen=self.page(pkg)
            return screen.point(pkg,labels,rids,area) if screen else None
        # Only callers with a just-read, unchanged page supply it. Never cache
        # across a tap or navigation; a missing control still gets a fresh wait.
        point=first_page.point(pkg,labels,rids,area) if first_page is not None else None
        self.tap(pkg,point if point is not None else self.wait(probe,why))

    def start(self,*args):
        out=self.shell('am','start',*args)
        if re.search(r'(Error|Exception|Permission Denial)',out):
            raise Problem('Android 打开指定页面失败。')
        # The caller waits for the destination UI; no unconditional post-launch sleep.

    def chat(self):
        self.start('-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER',
                   '-f','0x10200000','-n',GPT+'/.MainActivity')
        return self.expect(GPT)

class Screen:
    def __init__(self,root):
        self.nodes=list(root.iter('node'))
        self.parent={c:p for p in root.iter() for c in p}
        self.packages={n.get('package') for n in self.nodes}
    def has(self,label,pkg=None):
        return any((pkg is None or n.get('package')==pkg) and label in
                   (n.get('text'),n.get('content-desc')) for n in self.nodes)
    def point(self,pkg,labels=(),rids=(),area=None):
        # Prefer exact control labels, require a clickable ancestor, reject ambiguity.
        for value in (*rids,*labels):
            found=set()
            for n in self.nodes:
                if n.get('package')!=pkg or value not in (n.get('resource-id'),n.get('text'),n.get('content-desc')):continue
                a=n
                while a is not None and a.get('clickable')!='true': a=self.parent.get(a)
                if a is None or a.get('package')!=pkg or a.get('enabled')!='true':continue
                bounds=list(map(int,re.findall(r'-?\d+',n.get('bounds',''))))
                if len(bounds)!=4:continue
                l,t,r,b=bounds
                if l>=r or t>=b: continue
                xy=((l+r)//2,(t+b)//2)
                if not area or area(*xy): found.add(xy)
            if len(found)==1:return found.pop()
            if len(found)>1: raise Problem('同名控件不唯一，已停止：'+value)
        return None

def connect(stop=None):
    probe=Device(stop=stop)
    rows=[s.split() for s in probe.call('devices').splitlines()[1:] if s.strip()]
    if len(rows)!=1 or len(rows[0])<2 or rows[0][1]!='device':
        raise Problem('请只连接一台已授权的 Android 手机，然后重试预检。')
    probe.serial=rows[0][0]
    return probe
