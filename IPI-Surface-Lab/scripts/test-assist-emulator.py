#!/usr/bin/env python3
"""Temporary default-assistant test harness; restores the emulator setting even on failure."""
from ui_smoke import *
guard()
original=adb('shell','settings','get','secure','voice_interaction_service').strip()
# Recovery if an earlier interrupted run left this exact test receiver selected.
if original.startswith('lab.ipi.surface.test/'):
    original=(ROOT/'evidence'/'emulator-original-assistant.txt').read_text().strip()
else:
    (ROOT/'evidence'/'emulator-original-assistant.txt').write_text(original+'\n')
try:
    adb('shell','settings','put','secure','voice_interaction_service','lab.ipi.surface.test/lab.ipi.surface.TestVoiceService')
    time.sleep(1)
    launch();click('F · Screen / Assist Context');click('打开原生 Assist 测试页');screenshot('assist-native.png')
    before=len(logs())
    print(adb('shell','am','broadcast','-n','lab.ipi.surface.test/lab.ipi.surface.TestShowReceiver','-a','lab.ipi.surface.test.SHOW'))
    time.sleep(2)
    capture=adb('shell','run-as','lab.ipi.surface.test','cat','files/assist-capture.json')
    (ROOT/'evidence'/'assist-receiver.json').write_text(capture)
    callbacks=logs()[before:]
    (ROOT/'evidence'/'assist-system-callbacks.json').write_text(json.dumps(callbacks,ensure_ascii=False,indent=2))
    assert any(x.get('action')=='onProvideAssistData' for x in callbacks)
    assert any(x.get('action')=='onProvideAssistContent' for x in callbacks)
    assert any(x.get('action')=='View.onProvideStructure' for x in callbacks)
    assert 'IPI_ASSIST_B_' in capture and 'IPI_STRUCTURED_C_' in capture and 'IPI_VISIBLE_A_' in capture
    print(capture)
    print('SYSTEM_ASSIST_RECEIPT_PASS (test receiver; not Gemini/PICO)')
finally:
    adb('shell','settings','put','secure','voice_interaction_service',original)
    assert adb('shell','settings','get','secure','voice_interaction_service').strip()==original
    print('EMULATOR_ASSISTANT_RESTORED')
