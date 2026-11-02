"""Real Tk widgets; a fake phone. These tests never execute adb or touch a phone."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gc
import queue
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch, Mock
import app
from test_single import names
from catalog import Catalog

def setUpModule():
    # Multiple temporary Tk roots: never let a background test worker collect
    # Tcl-owned cycles from an earlier window.
    global gc_was_enabled
    gc_was_enabled=gc.isenabled()
    gc.collect();gc.disable()

def tearDownModule():
    gc.collect()
    if gc_was_enabled:gc.enable()

class WindowTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.cat=Catalog.parse('fake','/test',names())
        def patcher(*args,**kwargs):
            p=patch(*args,**kwargs);v=p.start();self.addCleanup(p.stop);return v
        patcher('app.HOME',Path(self.temp.name))
        patcher('app.connect').return_value.inspect.return_value=self.cat
        self.capture=patcher('app.capture_answer');self.capture.return_value={'screenshot':'fixture.png'}
        self.audio=patcher('app.play_after_success')
        self.flow=patcher('app.Flow')
        self.flow.return_value.run.return_value={'projection':'simulated'}
        self.device=patcher('app.Device')
        self.root=tk.Tk();self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.window=app.Window(self.root)
        self.until(lambda:self.window.mode=='idle')
    def until(self,predicate):
        until=time.monotonic()+5
        while not predicate():
            self.root.update()
            if time.monotonic()>until:self.fail('timed out')
            time.sleep(.01)
    def test_two_choices_one_start_no_chain(self):
        w=self.window; release=threading.Event();self.addCleanup(release.set)
        self.flow.return_value.run.side_effect=lambda:release.wait(3)
        self.assertEqual(tuple(w.boxes[0]['values']),tuple(f'{v} px' for v in app.SIZES))
        self.assertEqual(tuple(w.boxes[1]['values']),tuple(f'g{v}' for v in app.GRAYS))
        self.flow.assert_not_called()
        w.f.set('40 px');w.selection(0)
        self.assertEqual(w.file.get(),'097_f40-g01.png')
        w.btn.invoke();w.btn.invoke()
        self.until(lambda:self.flow.call_count==1)
        self.assertFalse(w.cancel.is_set())
        self.assertEqual(str(w.boxes[1]['state']),'disabled')
        release.set();self.until(lambda:w.mode=='idle')
        self.assertEqual(w.g.get(),'g2')
        self.audio.assert_called_once()
        self.assertEqual(self.capture.call_args.args[2],app.HOME/'captures'/w.cat.key/'40px')
        self.assertEqual(self.flow.call_count,1)
        self.assertEqual(self.flow.call_args.args[2:4],(40,1))
    def test_failure_does_not_advance(self):
        self.flow.return_value.run.side_effect=app.Problem('未确认终点')
        w=self.window;w.g.set('g12');w.selection(1);w.btn.invoke()
        self.until(lambda:w.mode=='idle')
        self.assertEqual(w.g.get(),'g12');self.assertIn('未确认',w.message.get())
        self.audio.assert_not_called()
        self.assertEqual(w.progress.state['done'],[])
    def test_cancel_retains_selected(self):
        w=self.window
        def until_stop():
            if w.cancel.wait(3):raise app.Stopped('已停止')
        self.flow.return_value.run.side_effect=until_stop
        with patch('app.monotonic',return_value=10.0) as clock:
            w.btn.invoke()
            clock.return_value=10.35  # After double-click guard, still before start.
            w.btn.invoke()
            self.assertTrue(w.cancel.is_set())
        self.until(lambda:w.mode=='idle')
        self.assertEqual(w.progress.state['done'],[])
        self.assertEqual(w.g.get(),'g1')
    def test_last_never_wraps_or_changes_size(self):
        w=self.window;w.f.set('64 px');w.selection(0);w.g.set('g32');w.selection(1);w.btn.invoke()
        self.until(lambda:w.mode=='idle')
        self.assertEqual((w.f.get(),w.g.get()),('64 px','g32 ✓'))
        self.assertIn('末档',w.message.get())
    def test_manual_marks_across_fonts_immediate_persistence_and_recall(self):
        w=self.window;w.progress.completed(16,1);w.selection(0)
        w.history_btn.invoke();h=w.history
        self.assertFalse(h.variables[1].get())
        h.cells[2].invoke()
        h.font.set('64 px');h.refresh();self.assertFalse(h.variables[2].get())
        h.cells[32].invoke()
        self.assertEqual(w.progress.registered(),{(16,2),(64,32)})
        self.assertEqual(app.Progress(w.progress.path,'not-this-catalogue').registered(),set())
        self.assertEqual(app.Progress(w.progress.path,w.cat.key).registered(),{(16,2),(64,32)})
        w.click();self.flow.assert_not_called()
        h.close()
        self.assertIn('g2 ✓',w.boxes[1]['values'])
        w.g.set('g2 ✓');w.selection(1)
        self.assertEqual(w.file.get(),'002_f16-g02.png')
        self.assertEqual(w.progress.next(16),2);self.flow.assert_not_called()
        w.btn.invoke();self.until(lambda:w.mode=='idle')
        self.assertEqual(self.flow.call_args.args[2:4],(16,2))
        self.assertEqual(w.g.get(),'g3')
        self.assertEqual(w.progress.registered(),{(16,2),(64,32)})

    def test_uncheck_is_not_a_phone_action(self):
        w=self.window;w.open_history();h=w.history
        h.cells[1].invoke();h.cells[1].invoke();h.close()
        self.assertEqual(w.progress.registered(),set())
        self.assertEqual(w.progress.state['done'],[])
        self.flow.assert_not_called()

    def test_failure_to_save_does_not_show_an_unsaved_mark(self):
        w=self.window;w.open_history();h=w.history
        with patch.object(w.progress,'save',side_effect=OSError('disk full')),patch('history.messagebox.showerror') as err:
            h.cells[3].invoke()
            err.assert_called_once()
        self.assertFalse(h.variables[3].get());h.close()
        self.assertFalse(w.progress.registered())

    def test_history_is_locked_during_run(self):
        w=self.window;release=threading.Event();self.addCleanup(release.set)
        self.flow.return_value.run.side_effect=lambda:release.wait(3)
        w.btn.invoke();w.history_btn.invoke();w.open_history()
        self.assertIsNone(w.history);self.assertEqual(str(w.history_btn['state']),'disabled')
        release.set();self.until(lambda:w.mode=='idle')
        self.assertEqual(str(w.history_btn['state']),'normal')
        self.assertEqual(w.progress.registered(),{(16,1)})

    def test_clear_confirmation_and_scope(self):
        w=self.window;p=w.progress
        p.completed(16,1)
        for f,g in ((16,3),(64,32)):p.set_registered(f,g,True)
        w.open_history();h=w.history
        with patch('history.messagebox.askyesno',return_value=False) as ask:
            h.clear_button.invoke()
            ask.assert_called_once()
        self.assertEqual(p.registered(),{(16,3),(64,32)})
        with patch('history.messagebox.askyesno',return_value=True):
            h.clear_button.invoke()
        self.assertEqual(p.registered(),set())
        self.assertEqual(p.next(16),2);self.assertEqual(p.state['done'],[[16,1]])
        self.assertEqual(str(h.clear_button['state']),'normal')
        h.close();self.assertNotIn('✓',' '.join(w.boxes[1]['values']))
        self.flow.assert_not_called()

    def test_loop_waits_two_seconds_between_saved_frames_and_stops_at_32(self):
        w=self.window;w.g.set('g31');w.selection(1);w.loop.set(True);w.wait_seconds.set('3.5')
        w.btn.invoke();self.until(lambda:w.mode=='idle')
        self.assertEqual([c.args[3] for c in self.flow.call_args_list],[31,32])
        self.assertEqual([c.args[1].value for c in self.capture.call_args_list],[3.5,3.5])
        self.assertEqual(w.progress.next(16),32)
    def test_capture_failure_does_not_advance_or_continue(self):
        w=self.window;w.loop.set(True);self.capture.side_effect=app.Problem('截图失败')
        w.btn.invoke();self.until(lambda:w.mode=='idle')
        self.flow.assert_called_once();self.assertEqual(w.progress.state['done'],[])
        self.assertEqual(w.g.get(),'g1')
    def test_stop_during_two_second_gap(self):
        w=self.window;w.loop.set(True);w.btn.invoke()
        self.until(lambda:'2 秒后继续' in w.message.get())
        w.armed=0;w.btn.invoke();self.until(lambda:w.mode=='idle')
        self.flow.assert_called_once();self.assertEqual(w.progress.state['done'],[[16,1]])
        self.assertEqual(w.g.get(),'g2')
    def test_invalid_wait_never_starts(self):
        w=self.window;w.wait_seconds.set('nan');w.btn.invoke();self.flow.assert_not_called();self.assertEqual(w.mode,'idle')

    def test_full_loop_crosses_font_boundary(self):
        w=self.window;w.f.set('48 px');w.selection(0);w.g.set('g32')
        w.full_box.invoke();self.assertTrue(w.loop.get())
        self.assertEqual(str(w.loop_box['state']),'disabled')
        with patch.object(w.cancel,'wait',return_value=False) as gap:
            w.btn.invoke();self.until(lambda:w.mode=='idle')
        self.assertEqual([c.args[2:4] for c in self.flow.call_args_list],
                         [(48,32)]+[(64,g) for g in range(1,33)])
        self.assertEqual(gap.call_count,32)
        self.assertEqual(w.f.get(),'64 px')
        w.full_box.invoke();self.assertEqual(str(w.loop_box['state']),'normal')
        self.assertTrue(w.loop.get())
