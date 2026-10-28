#!/usr/bin/env python3
"""Offline only: no ADB, network, audio playback, or writes. Python 3 stdlib."""
import hashlib, json, random, struct, wave, zlib
from pathlib import Path
from reference_scoring import score
ROOT = Path(__file__).resolve().parent

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def local(name):
    p = (ROOT / name).resolve()
    if not p.is_relative_to(ROOT): raise ValueError("Path escapes package")
    return p

def main():
    sums = json.loads((ROOT / 'package_hashes.json').read_text(encoding='utf-8'))
    for name, sha in sums.items():
        if digest(local(name)) != sha: raise ValueError('Hash mismatch: ' + name)
    m = json.loads((ROOT / 'pilot_manifest.json').read_text(encoding='utf-8'))
    order = [1,8,12,13,14,16,24,32]
    random.Random(20261028).shuffle(order)
    assert [t['grayscale'] for t in m['trials']] == order
    assert len(m['trials']) == 8 and len(set(order)) == 8
    assert [t['trial_index'] for t in m['trials']] == list(range(1,9))
    for key in ('ground_truth','prompt_text','prompt_audio'):
        assert digest(local(m[key+'_path'])) == m[key+'_sha256']
    gt=local(m['ground_truth_path']).read_bytes().decode('utf-8')
    assert len(gt.splitlines())==5 and all(len(s)==20 and s.isascii() and s.isupper() and s.isalpha() for s in gt.splitlines())
    for t in m['trials']:
        p=local(t['image_path']); b=p.read_bytes()
        assert digest(p)==t['image_sha256']
        assert b[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',b[16:24])==(1080,2400)
        pos=8;ended=False
        while pos<len(b):
            size=struct.unpack('>I',b[pos:pos+4])[0];kind=b[pos+4:pos+8];data=b[pos+8:pos+8+size]
            crc=struct.unpack('>I',b[pos+8+size:pos+12+size])[0]
            assert zlib.crc32(kind+data)&0xffffffff==crc
            pos+=12+size
            if kind==b'IEND': ended=True;break
        assert ended
    with wave.open(str(local(m['prompt_audio_path'])),'rb') as w:
        assert (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype())==(1,2,24000,'NONE')
        assert len(w.readframes(w.getnframes()))==w.getnframes()*2
    assert score(gt,gt)['correct']==100
    assert score(gt,'[UNREADABLE]')['correct']==0
    assert score('AB','A[UNK]')['unk_tokens']==1
    print('PASS: package hashes; 8 unchanged PNGs; fixed order; 100-letter ground truth; WAV; scoring smoke tests')
    print('Order: '+', '.join('g'+str(g) for g in order))
    print('No device operations, playback or collection performed.')
if __name__=='__main__': main()
