"""A single, finite sequence. There is deliberately no batch runner."""
from pathlib import PurePosixPath
from urllib.parse import quote
import re
from android import FILES,GPT,SYS,VIEW,Problem

START_DELAY = 0.5

NEW=('开始新聊天','新聊天','新建聊天','新建对话','New chat','Start new chat')
DRAWER=('菜单','打开侧边栏','打开边栏','打开导航菜单','打开菜单','Open sidebar','Open navigation menu')
VOICE=('开始语音对话','开始语音聊天','开始语音','使用语音','语音模式','Start voice mode','Start voice conversation','Use voice')
END=('结束','结束通话','结束语音聊天','结束语音对话','End call','End voice conversation')
PLUS=('添加附件','添加文件和更多内容','添加照片和文件','附件','添加','打开附件菜单','Add attachments','Add files and more','Add','更多选项')
MORE=('更多选项','更多','More options','More')
MODE=('共享一个应用','共享单个应用','A single app','Share one app','One app')
SHARE=('共享屏幕','Share screen','Share Screen')

class Flow:
    def __init__(self,device,cat,f,g,status):
        self.d,self.cat,self.f,self.g,self.status=device,cat,f,g,status
        self.name=cat.files[f,g]
        self.viewer=None
    def run(self):
        self.status(f'等待 {START_DELAY:g} 秒')
        self.d.delay(START_DELAY)
        self.status('核对手机和所选图片')
        self.d.usable()
        if self.d.inspect().key!=self.cat.key:raise Problem('图片目录已变化，请重新预检。')
        self.status('打开 ChatGPT 新对话')
        self.new_chat()
        self.status('文件：'+self.name)
        self.open_file()
        self.status('进入 ChatGPT 语音')
        self.voice()
        self.status('仅共享「文件」应用')
        self.share_file_task()
        self.status('核对最终图片界面')
        self.verify_end()
        return {'image':self.name,'task_id':self.viewer[2],'projection':'single_file_task_verified'}

    def new_chat(self):
        d=self.d
        s=d.chat()
        end=s.point(GPT,END)
        if end and (s.has('语音设置',GPT) or s.has('关闭麦克风',GPT) or d.projection()=='gpt'):
            d.tap(GPT,end)
            s=d.wait(lambda:(d.projection()=='none' and
                (p:=d.page(GPT)) and not p.point(GPT,END) and p),'请先在手机结束上一轮语音。')
        elif d.projection()!='none':
            raise Problem('上一轮共享仍在使用，请结束上一轮语音后再点执行。')
        new=s.point(GPT,NEW)
        if not new:
            d.press(GPT,DRAWER,'未找到 ChatGPT 的新聊天或侧栏入口。',first_page=s)
            d.press(GPT,('聊天',)+NEW,'侧栏中未找到新聊天。')
        else:d.tap(GPT,new)
        def composer():
            p=d.page(GPT)
            return (p and any(n.get('package')==GPT and n.get('class')=='android.widget.EditText'
                              for n in p.nodes) and p.point(GPT,VOICE))
        d.wait(composer,'新对话输入框或语音按钮未就绪。')

    def open_file(self):
        d=self.d
        directory=PurePosixPath(self.cat.folder)
        uri='content://com.android.externalstorage.documents/document/'+quote(
            'primary:'+str(directory.relative_to('/sdcard')),safe='')
        d.start('-a','android.intent.action.VIEW','-n',FILES+'/.files.FilesActivity',
                '-d',uri,'-t','vnd.android.document/directory')
        # The directory launch supplies a Files-owned task, not a scroll position.
        files_task=d.wait(lambda:(fg:=d.foreground())[0]==FILES and fg[2],
                          '文件应用未就绪。')
        rel=str(directory.relative_to('/sdcard'))+'/'
        sql=lambda value:"'"+value.replace("'","''")+"'"
        rows=d.shell('content','query','--uri','content://media/external_primary/images/media',
                     '--projection','_id','--where',
                     'relative_path='+sql(rel)+' AND _display_name='+sql(self.name))
        match=re.fullmatch(r'Row: 0 _id=(\d+)',rows.strip())
        if not match:
            raise Problem('系统媒体索引中没有唯一匹配的图片：'+self.name)
        self.status('直接打开 '+self.name)
        d.start('--task',files_task,'-a','android.intent.action.VIEW','-t','image/png',
                '-d','content://media/external_primary/images/media/'+match[1],
                '--grant-read-uri-permission','-n',VIEW+'/.ViewActivity')
        def viewer_ready(*, chrome_hidden=False):
            p=d.page(VIEW)
            if not p:return None
            viewer=d.foreground()
            if viewer[0]!=VIEW or viewer[2]!=files_task:
                raise Problem('图片未在「文件」的同一个任务中打开，已停止。')
            boxes={tuple(map(int,re.findall(r'-?\d+',n.get('bounds','')))) for n in p.nodes
                   if n.get('package')==VIEW and n.get('resource-id')==VIEW+':id/imageView'}
            visible=[r for r in boxes if len(r)==4 and r[0]>=0 and r[1]>=0 and r[2]>r[0] and r[3]>r[1]]
            if len(visible)!=1:return None
            chrome=p.point(VIEW,MORE,rids=(VIEW+':id/shareButton',))
            if chrome_hidden and chrome:return None
            return viewer,visible[0],bool(chrome)

        self.viewer,rect,has_chrome=d.wait(viewer_ready,'目标图片未进入查看器。')
        if has_chrome:
            # Tap the image surface, not the menu. Already fullscreen: zero taps.
            l,t,r,b=rect
            d.tap(VIEW,((l+r)//2,(t+b)//2))
            settled=d.wait(lambda:viewer_ready(chrome_hidden=True),'图片工具栏未收起。')
            if settled[0]!=self.viewer:raise Problem('图片查看任务已改变。')

    def voice(self):
        d=self.d
        chat_page=d.chat()
        d.press(GPT,VOICE,'未找到语音入口。',first_page=chat_page)
        voice_page=d.wait(lambda:(p:=d.page(GPT)) and
                          (p.point(GPT,END) or p.has('ChatGPT 语音',GPT)) and p,
                          '语音未就绪；请检查网络和首次使用提示。',30)
        d.press(GPT,PLUS,'未找到语音界面的附件菜单。',first_page=voice_page)
        self.tap_share_menu()

    def tap_share_menu(self):
        # On this phone the attachment popup is visible but not the focused window.
        def item():
            if self.d.foreground()[0]!=GPT:return None
            p=self.d.tree(windows=True)
            if not any(p.has(x,GPT) for x in ('实时视频','拍照','Take photo','Live video')):return None
            return p.point(GPT,SHARE)
        self.d.tap(GPT,self.d.wait(item,'附件菜单没有共享屏幕。'))

    def share_file_task(self):
        d=self.d
        def confirmed_next():
            p=d.page(SYS)
            if not p:return None
            if not any(p.has(x,SYS) for x in MODE):
                raise Problem('共享模式不是「一个应用」，未确认或共享整个屏幕。')
            if not any('ChatGPT' in n.get('text','') or 'ChatGPT' in n.get('content-desc','') for n in p.nodes):
                raise Problem('共享确认框未标明 ChatGPT。')
            # Validate the mode, recipient and button on the same dialog.
            return p.point(SYS,('下一步','Next'))
        d.tap(SYS,d.wait(confirmed_next,'未找到单应用共享的下一步。'))
        self.pick_file_task()

    def pick_file_task(self):
        d=self.d
        p=d.expect(SYS)
        if not any(p.has(x,SYS) for x in ('选择要分享的应用','选择要共享的应用','Choose an app to share','Choose an app')):
            raise Problem('未识别系统单应用选择器。')
        # The app drawer starts a new task. Only the *recent task* card is valid.
        # Multiple Files cards have the same label: check the actual MRU task ID
        # as well as the first thumbnail's accessibility identity before tapping.
        recent=d.shell('dumpsys','activity','recents')
        m=re.findall(r'Recent #\d+: Task\{[^\n]*? #(\d+) type=standard A=\d+:([\w.]+)',recent)
        other=next(((t,pkg) for t,pkg in m if pkg!=GPT),None)
        if other!=(self.viewer[2],FILES):raise Problem('最近的文件任务不是刚才核对的图片。')
        cards=[n for n in p.nodes if n.get('package')==SYS and n.get('clickable')=='true'
               and any(v.get('resource-id')==SYS+':id/task_thumbnail' for v in n.iter('node'))
               and n.get('class')=='android.widget.LinearLayout']
        if not cards or cards[0].get('index')!='0' or cards[0].get('content-desc') not in ('文件','Files'):
            raise Problem('共享选择器第一张最近任务卡不是文件应用。')
        bounds=list(map(int,re.findall(r'\d+',cards[0].get('bounds',''))))
        if len(bounds)!=4 or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:
            raise Problem('文件任务预览不可见。')
        d.tap(SYS,((bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2))

    def verify_end(self):
        def end():
            return self.d.foreground()==self.viewer and self.d.sharing_task(self.viewer[2])
        self.d.wait(end,'未确认 ChatGPT 共享及原图片任务同时就绪。')
        self.d.delay(.5)
        if not end():raise Problem('最终界面未稳定。')
