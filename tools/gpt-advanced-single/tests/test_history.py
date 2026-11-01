import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from catalog import Progress,Problem

class RegistrationTest(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup)
        self.path=Path(t.name)/'progress.json'
        self.legacy={'font':16,'next':{'16':3},'done':[[16,1],[16,2]],'pending':[40,4]}
        self.path.write_text(json.dumps({'a':self.legacy,'b':{'font':24,'next':{},'done':[], 'registered':[[24,1]]}}))
        self.p=Progress(self.path,'a')
    def test_reading_legacy_keeps_bytes_and_starts_without_manual_marks(self):
        old=self.path.read_bytes();self.assertEqual(Progress(self.path,'a').registered(),set())
        self.assertEqual(self.path.read_bytes(),old)
        self.p.set_registered(40,6,True);self.p.set_registered(40,6,True)
        self.assertEqual(self.p.registered(),{(40,6)})
        self.assertEqual({k:v for k,v in self.p.state.items() if k!='registered'},self.legacy)
        self.assertEqual(Progress(self.path,'b').registered(),{(24,1)})
    def test_no_mark_from_run(self):
        self.p.set_registered(40,7,True);self.p.started(16,3);self.p.completed(16,3)
        self.assertEqual(self.p.registered(),{(40,7)})
    def test_invalid_mark_and_corrupt_record_do_not_overwrite(self):
        old=self.path.read_bytes()
        for x in [(16,0,True),(999,32,False),(16,True,True),(16,2,1)]:
            with self.assertRaises(ValueError):self.p.set_registered(*x)
        self.assertEqual(self.path.read_bytes(),old)
        bad={'a':dict(self.legacy,registered=[[16,1],[16,1]])}
        self.path.write_text(json.dumps(bad))
        with self.assertRaises(Problem):Progress(self.path,'a')
        self.assertEqual(json.loads(self.path.read_text()),bad)
    def test_io_failure_keeps_existing_state_and_file(self):
        old=self.path.read_bytes()
        with patch('catalog.os.replace',side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):self.p.set_registered(40,1,True)
        self.assertEqual(self.p.state,self.legacy);self.assertEqual(self.path.read_bytes(),old)

    def test_clear_is_scoped_to_catalogue_and_manual_records(self):
        for f,g in ((16,6),(64,32)):self.p.set_registered(f,g,True)
        self.p.clear_history()
        self.assertEqual(Progress(self.path,'a').registered(),set())
        self.assertEqual({k:v for k,v in self.p.state.items() if k!='registered'},self.legacy)
        self.assertEqual(Progress(self.path,'b').registered(),{(24,1)})
