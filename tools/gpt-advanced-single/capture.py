"""Post-audio capture. All phone actions are downstream of a manual session start."""
from datetime import datetime
from hashlib import sha256
import math, os, re, struct, subprocess, uuid, zlib
from pathlib import Path
from android import GPT, Problem

def seconds(value):
    try: n=float(value)
    except (TypeError,ValueError): raise Problem('等待时间请输入秒数。')
    if not math.isfinite(n) or not 0<=n<=3600: raise Problem('等待时间范围：0–3600 秒。')
    return n

def png_ok(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):return False
    p=8;idat=False
    while p+12<=len(data):
        size=struct.unpack_from('>I',data,p)[0];end=p+8+size
        if end+4>len(data):return False
        chunk=data[p+4:end];kind=chunk[:4]
        if zlib.crc32(chunk)!=struct.unpack_from('>I',data,end)[0]:return False
        if p==8 and (kind!=b'IHDR' or size!=13 or not all(struct.unpack_from('>II',chunk,4))):return False
        if kind==b'IDAT' and size:idat=True
        p=end+4
        if kind==b'IEND':return idat and size==0 and p==len(data)
    return False

def beside_orb(page,w,h):
    # Portrait voice layout: use lateral whitespace, not the central orb.
    if w>=h or w<=0:raise Problem('请将手机保持竖屏后再采集。')
    for x in (w//5,4*w//5):
        y=h//2
        blocked=False
        for n in page.nodes:
            if n.get('package')!=GPT:continue
            b=list(map(int,re.findall(r'-?\d+',n.get('bounds',''))))
            if len(b)!=4 or not (b[0]<=x<b[2] and b[1]<=y<b[3]):continue
            if n.get('text') or n.get('content-desc') or (n.get('clickable')=='true' and b[2]-b[0]<w*0.9):
                blocked=True;break
        if not blocked:return (x,y)
    raise Problem('圆圈两侧均有控件，已停止，不盲点。')

def finished_row(page):
    if not page:return False
    labels=(('复制','复制回复','Copy','Copy response'),('回复优秀','赞','Good response'),
            ('回复不佳','踩','Bad response'),('分享','Share'))
    groups=[[] for _ in labels]
    for n in page.nodes:
        if n.get('package')!=GPT:continue
        for i,aliases in enumerate(labels):
            if n.get('content-desc') not in aliases:continue
            v=list(map(int,re.findall(r'-?\d+',n.get('bounds',''))))
            if len(v)==4 and 0<=v[0]<v[2] and 0<=v[1]<v[3]:
                groups[i].append(v)
    from itertools import product
    for row in product(*groups):
        if all(a[0]<b[0] for a,b in zip(row,row[1:])) and max(b[1] for b in row)<min(b[3] for b in row):
            return True
    return False

def capture_answer(d,wait,folder,name,status):
    from live_wait import LiveWait
    if isinstance(wait,LiveWait):wait.run(d,status)
    else:status(f'等待回答 {wait:g} 秒');d.delay(wait)
    status('回到 ChatGPT，显示回答')
    p=d.chat()
    if not finished_row(p) and (p.has('语音设置',GPT) or p.has('关闭麦克风',GPT) or p.has('结束通话',GPT)):
        vals=re.findall(r'(\d+)x(\d+)',d.shell('wm','size'))
        if not vals:raise Problem('未取得屏幕尺寸。')
        w,h=map(int,vals[-1])
        status('轻点语音圆圈旁的空白')
        d.tap(GPT,beside_orb(p,w,h))
        d.delay(.25)  # Let the reveal animation draw; never inspect the reply.
    status('等待回答下方的完成图标')
    d.wait(lambda:finished_row(d.page(GPT)),'等待完成图标超时，未保存、未推进。',timeout=120)
    status('保存回答截图')
    fg=d.foreground()
    if fg[0]!=GPT:raise Problem('前台已改变。')
    data=subprocess.run([d.adb,'-s',d.serial,'exec-out','screencap','-p'],capture_output=True,check=True,timeout=15).stdout
    d.check()
    if d.foreground()!=fg or not png_ok(data):raise Problem('截图或前台校验失败。')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    gray=int(re.search(r'-g(\d+)\.png$',name,re.I)[1])
    path=folder/(f'g{gray:02d}_'+Path(name).stem+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:8]+'.png')
    tmp=path.with_suffix('.part')
    try:
        with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
    return {'screenshot':str(path),'sha256':sha256(data).hexdigest()}
