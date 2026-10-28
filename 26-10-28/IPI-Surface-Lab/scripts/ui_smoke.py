#!/usr/bin/env python3
"""UI helpers for the disposable emulator only (no physical-device mutation)."""
import subprocess, time, re, json, pathlib, xml.etree.ElementTree as ET
SERIAL='emulator-5580'
ROOT=pathlib.Path(__file__).resolve().parents[1]
(ROOT/'evidence').mkdir(exist_ok=True)
def adb(*args, binary=False):
    result=subprocess.run(['adb','-s',SERIAL,*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    return result.stdout if binary else result.stdout.decode()
def guard():
    assert adb('shell','getprop','ro.kernel.qemu').strip()=='1'
    assert adb('emu','avd','name').splitlines()[0]=='IPI_Surface_Lab_API35', 'Use only the task-created disposable AVD'
def dump():
    adb('shell','uiautomator','dump','/sdcard/ipi-window.xml')
    return ET.fromstring(adb('shell','cat','/sdcard/ipi-window.xml'))
def click(text, scroll=True):
    for i in range(12 if scroll else 1):
        root=dump()
        for n in root.iter('node'):
            if n.get('text')==text or n.get('content-desc')==text:
                b=list(map(int,re.findall(r'\d+',n.get('bounds'))))
                if b[3] > b[1] and b[1] < 2260:
                    adb('shell','input','tap',str((b[0]+b[2])//2),str((b[1]+b[3])//2));time.sleep(.7);return
        if scroll: adb('shell','input','swipe','540','2000','540','1500','600');time.sleep(.4)
    raise AssertionError(f'UI text not found: {text}')
def screenshot(name):
    (ROOT/'evidence'/name).write_bytes(adb('exec-out','screencap','-p',binary=True))
def launch():
    adb('shell','am','force-stop','lab.ipi.surface');adb('shell','am','start','-W','-n','lab.ipi.surface/.MainActivity');time.sleep(.6)
def logs():
    return [json.loads(x) for x in adb('shell','run-as','lab.ipi.surface','cat','files/experiments/operations.jsonl').splitlines() if x.strip()]
if __name__=='__main__':
    guard(); launch(); click('Export JSON'); screenshot('saf-picker.png')
    root=dump()
    for n in root.iter('node'):
        if n.get('text') or n.get('content-desc'): print(n.get('text'),n.get('content-desc'),n.get('resource-id'),n.get('bounds'))
