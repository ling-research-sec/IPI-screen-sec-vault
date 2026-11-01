"""Replay the parent-list false positive and off-screen item without an Android device."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
import xml.etree.ElementTree as ET
from test_flow import Phone
from android import FILES,Screen,Problem
from round_flow import Flow

class FolderPhone(Phone):
    def __init__(self,offscreen=False):
        super().__init__();self.offscreen=offscreen;self.left=False;self.frozen=False
        self.trace=[]
    def start(self,*a):
        self.state='parent'
    def foreground(self):
        if self.state in ('parent','search','scrolled','outside'):
            return FILES,'main','42'
        return super().foreground()
    def tree(self,windows=False):
        if self.state not in ('parent','search','scrolled','outside'):return super().tree(windows)
        root=ET.Element('hierarchy')
        def n(rid,text='',bounds='[10,10][86,55]',parent=root):
            return ET.SubElement(parent,'node',{'package':FILES,'resource-id':rid,'text':text,
                'class':'android.widget.TextView','bounds':bounds,'clickable':'true','enabled':'true'})
        if self.state!='scrolled':
            n(FILES+':id/breadcrumb_text','Other' if self.state=='outside' else 'Pictures')
        else:n(FILES+':id/header_title','GPT_Advanced 中的文件')
        panel=n(FILES+':id/dir_list',bounds='[0,80][600,1000]')
        if self.state=='scrolled':
            n('android:id/title','007_f16-g07.png','[120,150][220,200]',panel)
            n('android:id/title','008_f16-g08.png','[120,270][220,330]',panel)
        else:n('android:id/title','GPT_Advanced','[120,150][220,200]',panel)
        n(FILES+':id/option_menu_search','搜索','[550,3][599,55]')
        return Screen(root)
    def shell(self,*a):
        if a[0]=='input' and self.state in ('parent','scrolled','outside'):
            if a[1]=='swipe':
                assert self.state=='scrolled'
                self.trace.append('scroll');self.state='outside' if self.left else 'scrolled' if self.frozen else 'files'
            elif int(a[2])>540:self.trace.append('search');self.state='search'
            else:
                assert self.state=='parent' and int(a[2])==170
                self.trace.append('open-folder');self.state='scrolled' if self.offscreen else 'files'
            return ''
        return super().shell(*a)

def run(d):
    f=Flow(d,d.cat,16,1,lambda s:None);f.open_file()
    return f.viewer

class FolderCases(unittest.TestCase):
    def test_parent_is_not_target(self):
        d=FolderPhone();self.assertEqual(run(d)[0],'org.lineageos.glimpse')
        self.assertEqual(d.trace,['open-folder'])
    def test_offscreen_no_search(self):
        d=FolderPhone(True);run(d)
        self.assertEqual(d.trace,['open-folder','scroll'])
    def test_aborts_if_directory_changes(self):
        d=FolderPhone(True);d.left=True
        with self.assertRaises(Problem):run(d)
        self.assertEqual(d.trace,['open-folder','scroll'])
    def test_bounded_when_no_motion(self):
        d=FolderPhone(True);d.frozen=True
        with self.assertRaises(Problem):run(d)
        self.assertEqual(d.trace,['open-folder','scroll','scroll'])
    def test_unrelated_folder_name_row_is_not_authority(self):
        class Elsewhere(FolderPhone):
            def start(self,*a):self.state='outside'
        d=Elsewhere()
        with self.assertRaisesRegex(Problem,'未显示目标目录'):run(d)
        self.assertEqual(d.trace,[])
