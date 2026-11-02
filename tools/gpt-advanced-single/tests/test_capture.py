import unittest,sys,zlib,struct,hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from capture import *
from android import Screen
import xml.etree.ElementTree as E

def page(text,voice=False):
    root=E.Element('hierarchy')
    E.SubElement(root,'node',{'package':GPT,'class':'android.widget.TextView','text':text,'content-desc':'语音设置' if voice else ''})
    return Screen(root)
def png():
    def chunk(k,b):return struct.pack('>I',len(b))+k+b+struct.pack('>I',zlib.crc32(k+b))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00'*4))+chunk(b'IEND',b'')
class CaptureTest(unittest.TestCase):
    def test_capture_without_text_or_polling(self):
        d=Mock();d.chat.return_value=page('',True);d.shell.return_value='1080x2400'
        d.foreground.return_value=(GPT,'main','22');d.adb='adb';d.serial='fixture'
        with TemporaryDirectory() as tmp,patch('capture.subprocess.run') as run:
            run.return_value.stdout=png();result=capture_answer(d,3.5,tmp,'097_f40-g01.png',lambda _:None)
            self.assertEqual([c.args for c in d.delay.call_args_list],[(3.5,),(.25,)])
            d.wait.assert_called_once();d.tap.assert_called_once_with(GPT,(216,1200))
            self.assertTrue(Path(result['screenshot']).name.startswith('g01_097_f40-g01_'))
            self.assertEqual(Path(result['screenshot']).read_bytes(),png())
            self.assertEqual(result['sha256'],sha256(png()).hexdigest())
    def test_invalid_png_and_waits(self):
        self.assertTrue(png_ok(png()))
        for data in (b'',png()[:-1],png()[:-8]+b'x'*8):self.assertFalse(png_ok(data))
        for value in ('nan',-1,'',3601,'inf'):
            with self.assertRaises(Problem):seconds(value)

    def test_side_whitespace_not_controls(self):
        p=page('',True)
        p.nodes[0].set('bounds','[0,1000][350,1400]')
        self.assertEqual(beside_orb(p,1080,2400),(864,1200))
        p.nodes[0].set('bounds','[0,1000][1080,1400]')
        with self.assertRaises(Problem):beside_orb(p,1080,2400)

    def test_toolbar_only(self):
        r=E.Element('hierarchy')
        for i,label in enumerate(('复制','回复优秀','回复不佳','分享')):
            self.assertFalse(finished_row(Screen(r)))
            n=E.SubElement(r,'node',{'package':GPT,'content-desc':label,'bounds':f'[{i*100},600][{i*100+90},690]'})
        self.assertTrue(finished_row(Screen(r)))
        n.set('bounds','[300,800][390,890]')
        self.assertFalse(finished_row(Screen(r)))
