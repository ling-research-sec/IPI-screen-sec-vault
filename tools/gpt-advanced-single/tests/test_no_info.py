from unittest.mock import patch
import unittest
from test_flow import Phone
from android import VIEW, Device, Problem
from round_flow import Flow

class ImagePresentation(unittest.TestCase):
    def flow(self,d):
        return Flow(d,d.cat,16,1,lambda _:None)

    def test_fullscreen_image_is_not_tapped_or_opened_in_details(self):
        class Fullscreen(Phone):
            def shell(self,*args):
                out=super().shell(*args)
                if self.state=='viewer':self.state='hidden'
                return out
        d=Fullscreen()
        self.flow(d).run()
        self.assertEqual(d.state,'final')
        self.assertFalse(any(a[0] in ('viewer','hidden','more','info') for a in d.sent))
        self.assertEqual(len(d.sent),8)

    def test_image_surface_must_exist_before_leaving_viewer(self):
        class Empty(Phone):
            def tree(self,windows=False):
                p=super().tree(windows)
                if self.state=='viewer':
                    for n in p.nodes:
                        if n.get('resource-id')==VIEW+':id/imageView':n.set('bounds','[0,0][0,0]')
                return p
        d=Empty()
        with self.assertRaisesRegex(Problem,'未进入查看器'):self.flow(d).run()
        self.assertEqual(d.sent[-1][0],'files')

    def test_same_viewer_package_but_different_task_stops(self):
        class WrongTask(Phone):
            def foreground(self):
                pkg,activity,task=super().foreground()
                return pkg,activity,'99' if pkg==VIEW else task
        d=WrongTask()
        with self.assertRaisesRegex(Problem,'同一个任务'):self.flow(d).run()
        self.assertEqual(d.sent[-1][0],'files')

    def test_after_launch_waits_for_visible_image_instead_of_fixed_sleep(self):
        class Late(Phone):
            frames=0
            wait=Device.wait
            def tree(self,windows=False):
                p=super().tree(windows)
                if self.state=='viewer' and self.frames<2:
                    self.frames+=1
                    for n in p.nodes:
                        if n.get('resource-id')==VIEW+':id/imageView':n.set('bounds','[0,0][0,0]')
                return p
        d=Late()
        self.flow(d).run()
        self.assertEqual(d.frames,2);self.assertEqual(d.state,'final')
        self.assertEqual(len(d.sent),9)

    def test_android_launcher_has_no_fixed_sleep_and_still_reports_errors(self):
        from unittest.mock import Mock
        d=Mock();d.shell.return_value='Starting: Intent'
        Device.start(d,'-n','package/activity')
        d.delay.assert_not_called()
        d.shell.return_value='Error: Activity not started'
        with self.assertRaises(Problem):Device.start(d,'-n','package/activity')
