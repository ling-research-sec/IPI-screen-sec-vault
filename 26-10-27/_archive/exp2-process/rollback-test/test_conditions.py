import json, unittest, zipfile
import test_pipeline as t
import pipeline as p

class Conditions(t.Fixture):
    def test_two_fonts_same_gray_keep_separate_records_and_resume(self):
        self.data.update(values=[1,2],conditions={'1':{'font_px':16,'delta_g':1},'2':{'font_px':24,'delta_g':1}})
        (self.base/'grey-2.png').write_bytes(t.png())
        self.write_config();fake=t.FakeDevice(self.c);self.run_fake(fake)
        records=[p.read_json(self.c.record(1,v)) for v in [1,2]]
        self.assertEqual([(x['font_px'],x['delta_g']) for x in records],[(16,1),(24,1)])
        self.assertEqual([x['correct'] for x in records],[3,3])
        rows=p.scored_data(self.c)['rounds'][0]['rows']
        self.assertEqual([(x['font_px'],x['delta_g'],x['round']) for x in rows],[(16,1,1),(24,1,1)])
        self.run_fake(fake);self.assertEqual(fake.sent,2)
        self.data['conditions']['1']['font_px']=32;self.write_config()
        with self.assertRaisesRegex(p.PipelineError,'condition changed'):self.run_fake(fake)
        self.assertEqual(fake.sent,2)

    def test_duplicate_conditions_rejected(self):
        self.data.update(values=[1,2],conditions={'1':{'font_px':16,'delta_g':1},'2':{'font_px':16,'delta_g':1}})
        with self.assertRaisesRegex(p.PipelineError,'Duplicate font/gray'):self.write_config()

    def test_missing_condition_rejected(self):
        self.data.update(values=[1,2],conditions={'1':{'font_px':16,'delta_g':1}})
        with self.assertRaisesRegex(p.PipelineError,'Missing two-dimensional'):self.write_config()

if __name__=='__main__':unittest.main(verbosity=2)
