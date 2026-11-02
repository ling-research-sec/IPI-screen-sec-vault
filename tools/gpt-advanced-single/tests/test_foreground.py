import unittest
from unittest.mock import Mock,patch
from android import Device,Problem,Stopped
class ForegroundTest(unittest.TestCase):
    def device(self):
        d=Mock();d.foreground=lambda:Device.foreground(d);return d
    def test_transition_empty_then_real_task(self):
        d=self.device();d.shell.side_effect=['topResumedActivity=null','', 'topResumedActivity=ActivityRecord{abc u0 com.android.documentsui/.files.FilesActivity t4333}']
        self.assertEqual(d.foreground(),('com.android.documentsui','.files.FilesActivity','4333'))
        self.assertEqual(d.shell.call_count,3)
        self.assertEqual(d.delay.call_count,2)
    def test_does_not_use_stale_focused_activity(self):
        d=self.device();d.shell.return_value='mFocusedApp=ActivityRecord{abc u0 com.android.documentsui/.files.FilesActivity t4333}'
        with patch('android.time.monotonic',side_effect=[0,4]),self.assertRaises(Problem):d.foreground()
    def test_cancel_and_connection_failure_propagate(self):
        d=self.device();d.check.side_effect=Stopped('stop')
        with self.assertRaises(Stopped):d.foreground()
        d.shell.assert_not_called()
