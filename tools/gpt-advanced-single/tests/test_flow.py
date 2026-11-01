"""Drive the real single-round controller through the observed Chinese UI states, offline."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from android import Device,Screen,FILES,GPT,VIEW,SYS,Problem
from catalog import Catalog
from round_flow import Flow
from test_single import names

class Phone(Device):
    def __init__(self,gray=1):
        self.serial='fixture';self.stop=None;self.state='before';self.gray=gray
        self.cat=Catalog.parse(self.serial,'/sdcard/Pictures/GPT_Advanced',names())
        self.name=self.cat.files[16,gray];self.sent=[];self.delays=[];self.menu_seen=False
    def usable(self): pass
    def inspect(self):return self.cat
    def delay(self,t):self.delays.append(t)
    def foreground(self):
        pkg={'files':FILES,'viewer':VIEW,'more':VIEW,'info':VIEW,'hidden':VIEW,
             'permission':SYS,'picker':SYS,'final':VIEW}.get(self.state,GPT)
        return pkg,'ViewActivity' if pkg==VIEW else 'main','42' if pkg in (VIEW,FILES) else '33'
    def start(self,*args):
        if FILES+'/.files.FilesActivity' in args:self.state='files'
        elif self.state=='hidden':self.state='composer'
        else:self.state='chat'
    def tree(self,windows=False):
        pkg=self.foreground()[0];root=ET.Element('hierarchy')
        def node(label='',cd='',rid='',cls='android.view.View',click=True,i=0,parent=root):
            return ET.SubElement(parent,'node',{'package':pkg,'text':label,'content-desc':cd,'resource-id':rid,
                'index':str(i),'class':cls,'clickable':str(click).lower(),'enabled':'true','bounds':f'[{100*i},20][{100*i+80},100]'})
        if self.state=='chat':node(cd='菜单')
        elif self.state=='sidebar':node('聊天')
        elif self.state=='composer':node(cls='android.widget.EditText');node(cd='开始语音对话',i=1)
        elif self.state=='files':
            node('GPT_Advanced',rid=FILES+':id/breadcrumb_text')
            listing=node(rid=FILES+':id/dir_list',click=False)
            listing.set('bounds','[0,10][600,600]')
            node(self.name,rid='android:id/title',i=1,parent=listing)
        elif self.state=='viewer':
            node(rid=VIEW+':id/imageView',click=False).set('bounds','[0,98][1080,2302]')
            node(cd='更多选项')
        elif self.state=='hidden':node(rid=VIEW+':id/imageView',click=False)
        elif self.state=='more':node('信息')
        elif self.state=='info':node(self.name)
        elif self.state=='voice':node(cd='结束');node(cd='附件',i=1);node(cd='语音设置',i=2)
        elif self.state=='popup':
            if windows:node('拍照');node('共享屏幕',i=1);self.menu_seen=True
        elif self.state=='permission':
            node('要与“ChatGPT”共享屏幕吗？');node('共享一个应用',i=1);node('下一步',i=2)
        elif self.state=='picker':
            node('选择要分享的应用',click=False)
            a=node(cd='文件',cls='android.widget.LinearLayout');node(rid=SYS+':id/task_thumbnail',parent=a,click=False)
            node('文件',i=3)
        return Screen(root)
    def shell(self,*args):
        if args==('wm','size'):return 'Physical size: 1080x2400'
        if args[:2]==('dumpsys','activity'):return 'Recent #0: Task{x #33 type=standard A=1:com.openai.chatgpt}\nRecent #1: Task{x #42 type=standard A=2:com.android.documentsui}'
        if args[0]=='input':
            self.sent.append((self.state,args))
            if args[1]=='keyevent':
                assert self.state=='info' and args[2]=='KEYCODE_BACK';self.state='viewer';return ''
            x=int(args[2]); routes={'chat':(40,'sidebar'),'sidebar':(40,'composer'),'composer':(140,'voice'),
                'files':(140,'viewer'),'viewer':(40,'more'),'more':(40,'info'),'voice':(140,'popup'),
                'popup':(140,'permission'),'permission':(240,'picker'),'picker':(40,'final')}
            if self.state=='viewer' and x==540:self.state='hidden';return ''
            expected,target=routes[self.state];assert x==expected,(self.state,x)
            self.state=target;return ''
        raise AssertionError(args)
    def projection(self):return 'none'
    def sharing_task(self,tid):return self.state=='final' and tid=='42'
    def wait(self,fn,why,timeout=18):
        value=fn()
        if not value:raise Problem(why)
        return value

class WholeRound(unittest.TestCase):
    def test_real_controller_one_target_then_returns(self):
        for gray in (1,10,32):
            d=Phone(gray)
            result=Flow(d,d.cat,16,gray,lambda s:None).run()
            self.assertEqual(result['image'],d.name);self.assertTrue(d.menu_seen)
            self.assertEqual(d.delays[0],0.5);self.assertEqual(d.state,'final')
            self.assertEqual([a[0] for a in d.sent].count('picker'),1)
