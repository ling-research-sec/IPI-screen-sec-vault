#!/usr/bin/env python3
"""Offline behavior tests. All Android I/O is fake; CLI guard uses a nonexistent serial."""
import binascii,contextlib,io,json,struct,subprocess,sys,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
import pipeline as p


def png(width=2,height=3,colour=0):
    def chunk(k,b):return struct.pack('>I',len(b))+k+b+struct.pack('>I',binascii.crc32(k+b)&0xffffffff)
    data=b''.join(b'\0'+bytes([colour,colour,colour])*width for _ in range(height))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(data))+chunk(b'IEND',b'')


def node(**kw):
    return ET.Element('node',{'class':'android.widget.FrameLayout','text':'','content-desc':'','bounds':'[0,0][2,3]',**kw})


class FakeDevice:
    def __init__(self,c,response='ABC',thinking_polls=0,bad_prompt=False,timeout=False):
        self.c=c;self.response=response;self.thinking_polls=thinking_polls;self.bad_prompt=bad_prompt;self.timeout=timeout
        self.commands=[];self.sent=0;self.answer_polls=0;self.current={'mode':1,'value':80}
    def preflight(self):return {'assistant':self.c.app,'brightness':self.brightness()}
    def brightness(self):return dict(self.current)
    def shell(self,*args,**kwargs):
        self.commands.append(args)
        if args[:3]==('settings','put','system'):
            if args[3]=='screen_brightness_mode':self.current['mode']=int(args[4])
            else:self.current['value']=int(args[4])
        if args[0]=='sha256sum':return p.file_hash(self.c.image(1))+'  '+args[1]
        if args[:2]==('content','query'):return 'Row: 0 _id=12, _display_name=grey-1.png, relative_path=Pictures/T/\n'
        return 'ok'
    def check_component(self,expected):pass
    def tap(self,point):self.commands.append(('tap',*point))
    def tap_node(self,n):self.sent+=1
    def shot(self,path):Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(png())
    def dump(self,path):
        name=Path(path).name
        if name in ('source-initial.xml','source-clean.xml'):nodes=[node(package='org.lineageos.glimpse')]
        elif name=='input.xml':nodes=[node(**{'class':'android.widget.EditText'})]
        elif name=='prompt.xml':nodes=[node(**{'class':'android.widget.EditText','text':'乱码' if self.bad_prompt else self.c.prompt}),node(**{'content-desc':'发送'})]
        else:
            self.answer_polls+=1
            nodes=[node(**{'class':'android.widget.TextView','text':'' if self.timeout else self.response})]
            if not self.timeout:nodes.append(node(**{'content-desc':'复制'}))
            if self.answer_polls<=self.thinking_polls:nodes.append(node(**{'content-desc':'助手正在思考。点击停止提问。'}))
        root=ET.Element('hierarchy');root.extend(nodes);Path(path).write_bytes(ET.tostring(root,encoding='utf-8'))
        return nodes


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        (self.base/'reference.txt').write_text('ABC');(self.base/'prompt.txt').write_text('Transcribe every character.\n\nOutput only text.')
        (self.base/'grey-1.png').write_bytes(png())
        self.data={'version':1,'experiment_dir':str(self.base/'experiment'),
            'reference_file':str(self.base/'reference.txt'),'prompt_file':str(self.base/'prompt.txt'),
            'image_pattern':str(self.base/'grey-{value}.png'),'phone_image_pattern':'/sdcard/Pictures/T/grey-{value}.png',
            'values':[1],'rounds':[1],'serial':'TEST_DEVICE','adapter':'perplexity-default-assistant-v1',
            'gallery_component':'org.lineageos.glimpse/.ViewActivity','image_size':[2,3],
            'brightness':{'action':'manual','value':255},'poll_s':0,'response_timeout_s':0.02,
            'ui':{'screen_size':[2,3],'validated_version_code':260665,
                  'assistant_activity':p.APP+'/.assistant.AssistantActivity','keyboard_tap':[1,2],'gallery_tap':[1,1],
                  'assistant_settle_s':0,'send_desc':'发送','copy_desc':'复制','thinking_contains':['正在思考']}}
        self.path=self.base/'config.json';self.write_config()
        self.sleep=patch.object(p.time,'sleep',return_value=None);self.sleep.start()
    def tearDown(self):self.sleep.stop();self.temp.cleanup()
    def write_config(self):self.path.write_text(json.dumps(self.data));self.c=p.Config(self.path);return self.c
    def run_fake(self,fake=None):
        with contextlib.redirect_stdout(io.StringIO()):return p.run(self.c,fake or FakeDevice(self.c))

    def test_plan_is_read_only_and_does_not_touch_device(self):
        before=sorted(str(x.relative_to(self.base)) for x in self.base.rglob('*'))
        with patch.object(p.Device,'adb',side_effect=AssertionError('No ADB')):result=p.plan(self.c)
        self.assertEqual(result['pending'],1);self.assertEqual(before,sorted(str(x.relative_to(self.base)) for x in self.base.rglob('*')))

    def test_cli_run_requires_execute(self):
        r=subprocess.run([sys.executable,str(Path(p.__file__)),'run',str(self.path)],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertIn('--execute',r.stderr);self.assertFalse(self.c.work.exists())

    def test_readonly_preflight_checks_phone_hash_and_reports_brightness_change(self):
        f=FakeDevice(self.c);result=p.preflight(self.c,f)
        self.assertTrue(result['settings_change_required']);self.assertTrue(result['phone_inputs'][0]['hash_match'])
        self.assertEqual(f.current,{'mode':1,'value':80});self.assertFalse(self.c.work.exists());self.assertEqual(f.sent,0)

    def test_successful_capture_and_resume_without_resubmission(self):
        f=FakeDevice(self.c);self.run_fake(f);d=p.read_json(self.c.record(1,1))
        self.assertEqual(f.sent,1);self.assertEqual(d['correct'],3);self.assertEqual(d['screen_brightness'],255)
        self.assertEqual(d['source_sha256'],d['phone_source_sha256']);self.assertTrue((self.c.evidence(1)/d['screenshot']).is_file())
        self.run_fake(f);self.assertEqual(f.sent,1)
        before=len(f.commands);self.run_fake(f);self.assertEqual(len(f.commands),before)

    def test_repeated_rounds_keep_independent_results(self):
        self.data['rounds']=[1,2];self.write_config();f=FakeDevice(self.c);self.run_fake(f)
        self.assertEqual(f.sent,2)
        self.assertEqual(p.read_json(self.c.record(1,1))['round'],1)
        self.assertEqual(p.read_json(self.c.record(2,1))['round'],2)

    def test_append_only_runs_new_parameter_level(self):
        f=FakeDevice(self.c);self.run_fake(f);old=self.c.record(1,1).read_bytes()
        (self.base/'grey-2.png').write_bytes(png());self.data['values']=[1,2];self.write_config();self.run_fake(f)
        self.assertEqual(f.sent,2);self.assertEqual(self.c.record(1,1).read_bytes(),old)
        self.assertTrue(self.c.record(1,2).exists())

    def test_copy_action_while_thinking_is_not_completion(self):
        f=FakeDevice(self.c,thinking_polls=3);self.run_fake(f);self.assertGreaterEqual(f.answer_polls,4)

    def test_timeout_is_not_unreadable_or_success(self):
        f=FakeDevice(self.c,timeout=True)
        with self.assertRaises(p.PipelineError):self.run_fake(f)
        self.assertEqual(f.sent,1);self.assertFalse(self.c.record(1,1).exists())
        state=p.read_json(self.c.work/'round01/g1/state.json');self.assertTrue(state['submitted']);self.assertEqual(state['phase'],'timeout')

    def test_submitted_pending_attempt_never_blindly_retries(self):
        f=FakeDevice(self.c,timeout=True)
        with self.assertRaises(p.PipelineError):self.run_fake(f)
        with self.assertRaises(p.PipelineError):self.run_fake(f)
        self.assertEqual(f.sent,1)

    def test_ime_mismatch_is_not_submitted(self):
        f=FakeDevice(self.c,bad_prompt=True)
        with self.assertRaises(p.PipelineError):self.run_fake(f)
        self.assertEqual(f.sent,0);self.assertFalse(p.read_json(self.c.work/'round01/g1/state.json')['submitted'])

    def test_unfinished_setup_is_not_erased_on_resume(self):
        f=FakeDevice(self.c,bad_prompt=True)
        with self.assertRaises(p.PipelineError):self.run_fake(f)
        state=(self.c.work/'round01/g1/state.json').read_bytes()
        with self.assertRaises(p.PipelineError):self.run_fake(FakeDevice(self.c))
        self.assertEqual(state,(self.c.work/'round01/g1/state.json').read_bytes())

    def test_model_output_is_data_not_a_shell_instruction(self):
        payload='ABC; touch /tmp/SHOULD_NOT_EXIST';f=FakeDevice(self.c,response=payload);self.run_fake(f)
        self.assertEqual(p.read_json(self.c.record(1,1))['response'],payload)
        self.assertFalse(any(payload in map(str,cmd) for cmd in f.commands))

    def test_raw_trailing_newline_is_preserved(self):
        f=FakeDevice(self.c,response='ABC\n');self.run_fake(f)
        d=p.read_json(self.c.record(1,1));self.assertEqual(p.raw_response(self.c,1,'1',d),'ABC\n')

    def test_changed_source_does_not_overwrite_old_trial(self):
        self.run_fake();old=self.c.record(1,1).read_bytes();self.c.image(1).write_bytes(png(colour=1))
        with self.assertRaises(p.PipelineError):p.plan(self.c)
        self.assertEqual(old,self.c.record(1,1).read_bytes())

    def test_changed_reference_is_not_silently_rescored(self):
        self.run_fake();(self.base/'reference.txt').write_text('XYZ');self.write_config()
        with self.assertRaises(p.PipelineError):p.scored_data(self.c)

    def test_append_does_not_mix_parameter_types(self):
        self.run_fake();(self.base/'grey-2.png').write_bytes(png());self.data.update(values=[2],parameter_key='font_px');self.write_config()
        f=FakeDevice(self.c)
        with self.assertRaises(p.PipelineError):self.run_fake(f)
        self.assertEqual(f.sent,0)

    def test_append_does_not_silently_change_prompt(self):
        self.run_fake();(self.base/'grey-2.png').write_bytes(png());self.data['values']=[2]
        (self.base/'prompt.txt').write_text('A different experiment prompt.');self.write_config()
        with self.assertRaises(p.PipelineError):p.plan(self.c)

    def test_foreign_work_folder_is_not_reused_or_deleted(self):
        self.c.work.mkdir(parents=True);f=self.c.work/'private.txt';f.write_text('keep')
        with self.assertRaises(p.PipelineError):p.work_dir(self.c)
        self.assertEqual(f.read_text(),'keep')

    def test_real_exclusive_lock(self):
        with p.locked(self.c):
            with self.assertRaises(p.PipelineError):
                with p.locked(self.c):pass

    def test_archive_restores_and_keeps_external_dependency(self):
        p.work_dir(self.c);target=self.base/'external';target.mkdir();(target/'keep').write_text('do not remove')
        (self.c.work/'node_modules').symlink_to(target,target_is_directory=True)
        (self.c.work/'evidence.xml').write_text('<hierarchy/>')
        with patch.object(p,'verify_reports',return_value={'status':'PASS'}):r=p.archive(self.c)
        self.assertFalse(self.c.work.exists());self.assertTrue((target/'keep').exists());self.assertTrue(Path(r['archive']).exists())

    def test_archive_blocks_unfinished_attempt(self):
        p.work_dir(self.c);p.save_json(self.c.work/'round01/g1/state.json',{'submitted':True,'phase':'awaiting-answer'})
        with patch.object(p,'verify_reports',return_value={'status':'PASS'}):
            with self.assertRaises(p.PipelineError):p.archive(self.c)
        self.assertTrue(self.c.work.exists())

    def test_unknown_app_is_not_replaced_with_perplexity(self):
        self.data['assistant_package']='other.assistant'
        with self.assertRaises(p.PipelineError):self.write_config()

    def test_non_ascii_prompt_stops_before_device_io(self):
        (self.base/'prompt.txt').write_text('请转写')
        with self.assertRaises(p.PipelineError):self.write_config()

    def test_unsafe_case_id_rejected(self):
        self.data['values']=['../escape']
        with self.assertRaises(p.PipelineError):self.write_config()

    def test_numeric_duplicate_levels_rejected(self):
        self.data['values']=[1,1.0]
        with self.assertRaises(p.PipelineError):self.write_config()

    def test_device_preflight_mismatch_is_read_only(self):
        d=p.Device(self.c);calls=[]
        def shell(*args,**kw):
            calls.append(args)
            if args[:2]==('cmd','role'):return p.APP
            if args[:2]==('wm','size'):return 'Physical size: 1080x2400'
            return ''
        with patch.object(d,'adb',return_value=b'device'),patch.object(d,'shell',side_effect=shell):
            with self.assertRaises(p.PipelineError):d.preflight()
        self.assertFalse(any('put' in cmd for cmd in calls))

    def test_shell_quotes_text_as_one_argument(self):
        d=p.Device(self.c);payload='x; touch /tmp/NO'
        with patch.object(d,'adb',return_value=b'') as adb:d.shell('input','text',payload)
        import shlex
        self.assertEqual(shlex.split(adb.call_args.args[1]),['input','text',payload])

    def test_foreground_parser_and_canonical_activity_match(self):
        d=p.Device(self.c)
        line='  topResumedActivity=ActivityRecord{123 u0 '+p.APP+'/'+p.APP+'.assistant.AssistantActivity t12}'
        with patch.object(d,'shell',return_value=line):
            self.assertEqual(d.foreground(),p.APP+'/'+p.APP+'.assistant.AssistantActivity')
            d.check_component(p.APP+'/.assistant.AssistantActivity')

    def test_unexpected_foreground_activity_is_not_tapped(self):
        d=p.Device(self.c)
        with patch.object(d,'foreground',return_value='com.android.launcher3/.Launcher'),patch.object(d,'tap') as tap:
            with self.assertRaises(p.PipelineError):d.check_component(p.APP+'/.assistant.AssistantActivity')
        tap.assert_not_called()


class Scores(unittest.TestCase):
    def test_alignment_operations(self):
        self.assertEqual(p.score('ABC','ABC')['correct'],3)
        self.assertEqual(p.score('ABC','AXC')['substitutions'],1)
        self.assertEqual(p.score('ABC','AC')['deletions'],1)
        self.assertEqual(p.score('ABC','ABXC')['insertions'],1)
    def test_markers(self):
        self.assertEqual(p.score('ABC','[UNREADABLE]')['deletions'],3)
        self.assertEqual(p.score('ABC','A[UNK]C')['correct'],2)
        self.assertEqual(p.score('\ufffd','[UNK]')['correct'],0)
    def test_unicode_and_whitespace(self):
        self.assertEqual(p.score('甲乙\n丙','甲乙丙')['correct'],3)
        self.assertEqual(p.score('A B','AB','preserve')['deletions'],1)
        self.assertEqual(p.score('A B\nC','A BC','linebreaks-only')['correct'],4)
    def test_tie_maximizes_matches(self):self.assertEqual(p.score('ABA','AA')['correct'],2)
    def test_empty_reference_rejected(self):
        with self.assertRaises(p.PipelineError):p.score(' \n','X')
    def test_png_crc_and_dimensions(self):
        self.assertEqual(p.png_size(png()),(2,3));bad=bytearray(png());bad[20]^=1
        with self.assertRaises(p.PipelineError):p.png_size(bytes(bad))


if __name__=='__main__':unittest.main(verbosity=2)
