from unittest import TestCase
from unittest.mock import Mock,patch
from live_wait import LiveWait
class Timing(TestCase):
    def test_edit_mid_wait_uses_original_origin(self):
        for old,new,elapsed,expected in [(12,3,5,0),(6,15,5,10)]:
            w=LiveWait(old);now=[0.];remaining=[]
            def advance(dt):
                if now[0]==0:
                    now[0]=elapsed;w.set(new)
                else:
                    remaining.append(dt);now[0]=new
            with patch('live_wait.monotonic',side_effect=lambda:now[0]),patch.object(w.cv,'wait',side_effect=advance):
                w.run(Mock(),Mock())
            self.assertEqual(bool(remaining),bool(expected))
