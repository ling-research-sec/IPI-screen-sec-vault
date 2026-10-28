#!/usr/bin/env python3
from ui_smoke import *
import hashlib

guard()
results=[]
def check(name, condition, detail=None):
    assert condition, name
    results.append({'test':name,'status':'PASS','detail':detail})
    print(name,'PASS',detail or '')
def current_result(action):
    for _ in range(20):
        row=logs()[-1]
        if row.get('action')==action:return row
        time.sleep(.2)
    raise AssertionError(f'Missing {action}')
def back(): adb('shell','input','keyevent','4');time.sleep(.4)
try:
    launch();screenshot('home-final.png');click('新 Run');click('保存 Payload')
    saved=adb('shell','run-as','lab.ipi.surface','cat','files/experiments/drafts.json')
    oldlogs=adb('shell','run-as','lab.ipi.surface','cat','files/experiments/operations.jsonl')
    launch()
    check('force-stop/restart persistence', saved==adb('shell','run-as','lab.ipi.surface','cat','files/experiments/drafts.json') and oldlogs==adb('shell','run-as','lab.ipi.surface','cat','files/experiments/operations.jsonl'))
    for p in ['READ_CONTACTS','WRITE_CONTACTS']:
        adb('shell','pm','revoke','lab.ipi.surface','android.permission.'+p)
        adb('shell','pm','clear-permission-flags','lab.ipi.surface','android.permission.'+p,'user-set','user-fixed')
    launch();click('A · Contacts Injection');click('直接创建联系人')
    row=current_result('create');check('real revoked contacts permissions',row['status']=='PERMISSION_DENIED',row['error']);screenshot('permission-denied.png')
    launch();click('A · Contacts Injection');click('检查 / 申请权限')
    nodes=list(dump().iter('node'))
    deny=next(n for n in nodes if n.get('resource-id','').endswith('permission_deny_button'))
    b=list(map(int,re.findall(r'\d+',deny.get('bounds'))));adb('shell','input','tap',str((b[0]+b[2])//2),str((b[1]+b[3])//2));time.sleep(.5)
    row=current_result('permission_result');check('runtime permission dialog denied',row['status']=='PERMISSION_DENIED')
    for p in ['READ_CONTACTS','WRITE_CONTACTS']:adb('shell','pm','grant','lab.ipi.surface','android.permission.'+p)
    launch();click('A · Contacts Injection');click('ACTION_INSERT 用户确认')
    row=current_result('insert_request');check('Contacts ACTION_INSERT dispatch',row['status']=='PENDING_USER_ACTION');screenshot('contacts-insert.png');back();back()
    launch();click('C · Calendar Injection');click('ACTION_INSERT 用户确认')
    row=current_result('insert_request');check('Calendar ACTION_INSERT dispatch',row['module']=='Calendar' and row['status']=='PENDING_USER_ACTION');screenshot('calendar-insert.png');back()
    launch();click('D · Alarm / Timer Injection');click('Set Alarm · 系统流程')
    row=current_result('set_alarm');check('SET_ALARM dispatch',row['status']=='PENDING_USER_ACTION');screenshot('alarm-intent.png');back()
    launch();click('D · Alarm / Timer Injection');click('Set Timer · 系统流程')
    row=current_result('set_timer');check('SET_TIMER dispatch',row['status']=='PENDING_USER_ACTION');screenshot('timer-intent.png');back()
    launch();click('E · File Injection');click('生成 PDF')
    row=current_result('create_pdf');check('PDF UI create',row['status']=='VERIFIED')
    file_id=row['objectId'];(ROOT/'evidence'/'sample-two-pages.pdf').write_bytes(adb('exec-out','run-as','lab.ipi.surface','cat','files/documents/'+file_id,binary=True))
    click('SAF 导出所选文件');click('SAVE',False)
    row=current_result('export_write');check('PDF SAF readback',row['status']=='VERIFIED',row['verification'])
    launch();click('E · File Injection');click('ACTION_SEND 分享');screenshot('share-chooser.png')
    row=current_result('share');check('file share chooser dispatch',row['status']=='PENDING_USER_ACTION');back()
    launch();click('Export JSON');click('SAVE',False)
    row=current_result('export_write');check('JSON SAF readback',row['status']=='VERIFIED',row['verification'])
    launch();click('Export CSV');click('SAVE',False)
    row=current_result('export_write');check('CSV SAF readback',row['status']=='VERIFIED',row['verification'])
finally:
    # These permissions were granted by the instrumentation baseline on this disposable emulator.
    for p in ['READ_CONTACTS','WRITE_CONTACTS']:adb('shell','pm','grant','lab.ipi.surface','android.permission.'+p)
    # No personal clock data exists in this newly-created AVD. Remove the two clock fixtures.
    print('test clock cleanup:',adb('shell','pm','clear','com.google.android.deskclock').strip())
    (ROOT/'evidence'/'ui-smoke-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
