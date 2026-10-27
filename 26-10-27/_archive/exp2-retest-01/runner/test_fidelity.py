import unittest
from pathlib import Path
import test_pipeline as t
import pipeline as p

class GateTests(t.Fixture):
    def prepare(self):
        (self.base/'grey-1.png').write_bytes(t.png(colour=7))
        self.data['source_fidelity_gate']={'roi':[0,0,2,3],'required_consecutive':2,'max_checks':3,'poll_s':0}
        self.write_config()
    def test_exact_source_passes_twice_then_sends_once(self):
        self.prepare()
        class Exact(t.FakeDevice):
            def shot(self,path):Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(t.png(colour=7))
        fake=Exact(self.c);self.run_fake(fake);r=p.read_json(self.c.record(1,1))
        self.assertEqual(fake.sent,1);self.assertEqual(r['source_fidelity']['status'],'PASS');self.assertEqual(r['source_fidelity']['consecutive_exact'],2)
    def test_lossy_source_blocks_before_assistant_or_send(self):
        self.prepare();fake=t.FakeDevice(self.c)
        with self.assertRaisesRegex(p.PipelineError,'stopped before assistant'):self.run_fake(fake)
        self.assertEqual(fake.sent,0);self.assertNotIn(('input','keyevent','219'),fake.commands);self.assertFalse(self.c.record(1,1).exists())
    def test_one_exact_frame_is_not_enough(self):
        self.prepare()
        class Changing(t.FakeDevice):
            count=0
            def shot(self,path):
                self.count+=1;Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(t.png(colour=7 if self.count==1 else 0))
        fake=Changing(self.c)
        with self.assertRaises(p.PipelineError):self.run_fake(fake)
        self.assertEqual(fake.sent,0)

if __name__=='__main__':unittest.main(verbosity=2)
