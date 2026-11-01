import json
import sys
import threading
import unittest
import xml.etree.ElementTree as ET
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalog import Catalog,SIZES,GRAYS,Progress,Problem
from android import Device,Screen,Stopped,GPT
from round_flow import Flow

def names():
    return [f'{i*32+g:03d}_f{f}-g{g:02d}.png' for i,f in enumerate(SIZES) for g in GRAYS]

class TestCatalog(unittest.TestCase):
    def table(self,n):return Catalog.parse('device','/sdcard/Pictures/GPT_Advanced',n)
    def test_every_pair(self):
        c=self.table(reversed(names()))
        self.assertEqual(len(c.files),192)
        for i,f in enumerate(SIZES):
            for g in GRAYS:self.assertEqual(c.files[f,g],names()[32*i+g-1])
    def test_missing(self):
        with self.assertRaisesRegex(Problem,'缺 1 张'):self.table(names()[:-1])
    def test_duplicate_name_or_pair(self):
        with self.assertRaisesRegex(Problem,'重复'):self.table(names()+['777_f16-g1.png'])
    def test_wrong_format(self):
        with self.assertRaisesRegex(Problem,'文件名'):self.table(names()+['mystery.png'])
    def test_unknown_size_or_gray(self):
        for s in ('999_f72-g01.png','999_f16-g00.png','999_f16-g33.png'):
            with self.assertRaisesRegex(Problem,'超出'):self.table(names()+[s])
    def test_progress_per_size_restores(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'progress.json'; p=Progress(path,'dev')
            p.completed(40,1)
            self.assertEqual(Progress(path,'dev').next(40),2)
            self.assertEqual(p.next(16),1)
            p.completed(40,32)
            self.assertEqual(p.next(40),32)
            self.assertEqual(Progress(path,'other').next(40),1)
    def test_corrupt_progress(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'p';p.write_text('[]')
            with self.assertRaises(Problem):Progress(p,'x')

class TestControls(unittest.TestCase):
    def screen(self,labels):
        root=ET.Element('hierarchy')
        for i,label in enumerate(labels):
            ET.SubElement(root,'node',{'package':GPT,'content-desc':label,'bounds':f'[{10*i},0][{10*i+10},10]','enabled':'true','clickable':'true'})
        return Screen(root)
    def test_exact(self):
        p=self.screen(['g1','g10'])
        self.assertEqual(p.point(GPT,['g1']),(5,5))
        self.assertIsNone(p.point('wrong',['g1']))
    def test_ambiguous(self):
        with self.assertRaises(Problem):self.screen(['g1','g1']).point(GPT,['g1'])
    def test_cancel_before_any_input(self):
        ev=threading.Event();ev.set()
        with patch('android.shutil.which',return_value='adb'):
            d=Device('test',ev)
        with patch('android.subprocess.run') as proc,self.assertRaises(Stopped):
            try:d.checked_input(GPT,'tap',0,0)
            finally:proc.assert_not_called()
    def test_finite_round_and_no_advance_from_flow(self):
        from unittest.mock import Mock
        cat=Catalog.parse('dev','dir',names()); d=Mock();d.inspect.return_value=cat
        flow=Flow(d,cat,16,1,lambda s:None);flow.viewer=('viewer','activity','42')
        with patch.multiple(flow,**{k:lambda:None for k in ['new_chat','open_file','voice','share_file_task','verify_end']}):
            flow.run()
        d.delay.assert_called_once_with(0.5)
        d.inspect.assert_called_once()
    def test_end_requires_projection_and_original_task(self):
        from unittest.mock import Mock
        cat=Catalog.parse('dev','dir',names());d=Mock()
        def check(fn,why):self.assertTrue(fn())
        d.wait.side_effect=check
        flow=Flow(d,cat,16,1,lambda s:None);flow.viewer=('view','activity','42')
        d.foreground.return_value=flow.viewer;d.sharing_task.return_value=True
        flow.verify_end()
        for focus,owner in [(('view','activity','43'),'gpt'),(flow.viewer,'none')]:
            d.foreground.return_value=focus;d.sharing_task.return_value=owner=='gpt'
            with self.assertRaises(AssertionError):flow.verify_end()

class TestSharing(unittest.TestCase):
    def test_exact_grantee_mode_and_task(self):
        from unittest.mock import patch
        report='packageName: com.openai.chatgpt\ntaskId to mirror: 4297\ncontentToRecord = RECORD_CONTENT_TASK, waitingForConsent = false'
        with patch('android.shutil.which',return_value='adb'):
            d=Device('fixture')
        for data,expected in [(report,True),(report.replace('4297','42970'),False),
            (report.replace('RECORD_CONTENT_TASK','RECORD_CONTENT_DISPLAY'),False),
            (report.replace('false','true'),False),(report.replace('chatgpt','chatgpt.fake'),False),
            ('Media Projection: null',False)]:
            with patch.object(d,'shell',return_value=data):self.assertEqual(d.sharing_task('4297'),expected)

    def test_task_card_not_drawer_or_other_recent(self):
        from android import SYS,FILES
        from unittest.mock import Mock
        root=ET.Element('hierarchy')
        ET.SubElement(root,'node',{'package':SYS,'text':'选择要分享的应用'})
        for i in (0,1):
            card=ET.SubElement(root,'node',{'index':str(i),'package':SYS,'clickable':'true',
                'content-desc':'文件','class':'android.widget.LinearLayout','bounds':f'[{88+358*i},458][{358+358*i},1168]'})
            ET.SubElement(card,'node',{'resource-id':SYS+':id/task_thumbnail'})
        d=Mock(); d.expect.return_value=Screen(root)
        flow=Flow(d,Catalog.parse('dev','dir',names()),16,1,lambda s:None)
        flow.viewer=('org.lineageos.glimpse','.ViewActivity','4297')
        recents='Recent #0: Task{x #4293 type=standard A=123:com.openai.chatgpt}\nRecent #1: Task{x #4297 type=standard A=52:com.android.documentsui}'
        d.shell.return_value=recents;flow.pick_file_task();d.tap.assert_called_once_with(SYS,(223,813))
        d.tap.reset_mock();d.shell.return_value=recents.replace('#4297','#4285')
        with self.assertRaises(Problem):flow.pick_file_task()
        d.tap.assert_not_called()

    def test_failure_survives_restart_without_marking_done(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'p'
            Progress(path,'x').started(64,10)
            recovered=Progress(path,'x')
            self.assertEqual(recovered.next(64),10)
            self.assertEqual(recovered.state['pending'],[64,10])
            self.assertEqual(recovered.state['done'],[])
