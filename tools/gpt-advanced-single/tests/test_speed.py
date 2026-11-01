"""Do not trade state checks or manual single-shot behavior for fewer UI dumps."""
from test_flow import Phone
from android import GPT, SYS, Problem
from round_flow import Flow, DRAWER, VOICE
import unittest
from unittest.mock import patch

class SpeedTests(unittest.TestCase):
    def test_same_complete_round_uses_at_most_eleven_snapshots(self):
        d=Phone();status=[]
        with patch.object(d,'tree',wraps=d.tree) as tree:
            result=Flow(d,d.cat,16,1,status.append).run()
        self.assertLessEqual(tree.call_count,11)
        self.assertEqual(d.delays[0],0.5)
        self.assertEqual(status[0],'等待 0.5 秒')
        self.assertEqual(result['image'],'001_f16-g01.png')
        self.assertEqual(d.state,'final')
        self.assertEqual(len(d.sent),9)
        self.assertNotIn('核对图片信息',status)
        self.assertFalse(any(s in ('more','info') for s,_ in d.sent))

    def test_missing_control_fetches_fresh_page(self):
        d=Phone();d.state='chat';old=d.tree()
        d.state='composer'
        with patch.object(d,'tree',wraps=d.tree) as tree:
            d.press(GPT,VOICE,'missing',first_page=old)
        tree.assert_called_once()
        self.assertEqual(d.state,'voice')

    def test_app_switch_prevents_tap_from_first_page(self):
        d=Phone();d.state='chat';old=d.tree()
        d.state='files'
        with self.assertRaisesRegex(Problem,'前台已变化'):
            d.press(GPT,DRAWER,'missing',first_page=old)
        self.assertEqual(d.sent,[])

    def test_rechecks_wrong_share_mode_before_next_becomes_available(self):
        d=Phone();d.state='permission';a=d.tree();b=d.tree()
        for n in a.nodes:
            if n.get('text')=='下一步':n.set('enabled','false')
        for n in b.nodes:
            if n.get('text')=='共享一个应用':n.set('text','整个屏幕')
        def retry(fn,why):
            self.assertFalse(fn())
            return fn()
        f=Flow(d,d.cat,16,1,lambda _:None)
        with patch.object(d,'page',side_effect=[a,b]),patch.object(d,'wait',side_effect=retry):
            with self.assertRaisesRegex(Problem,'共享模式'):f.share_file_task()
        self.assertEqual(d.sent,[])
