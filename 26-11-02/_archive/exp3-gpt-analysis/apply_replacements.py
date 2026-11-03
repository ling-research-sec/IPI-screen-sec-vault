from pathlib import Path
import copy, hashlib, importlib.util, json, os, shutil

W = Path(__file__).resolve().parent
ROOT = W.parents[2]
O = ROOT / '26-11-02/exp3-gpt-advanced'
A = sorted((O / 'archive').glob('before-replacement-*'))[-1]
SRC = Path('/Users/y4n9/Library/Application Support/GPT-Advanced-Single/captures/655f6610a98d40402555309ac20af296c91f60d0ff289a518cf7efd658ca93f2/第006轮')
spec = importlib.util.spec_from_file_location('pipeline', '/Users/y4n9/.codex/skills/android-screen-readability/scripts/pipeline.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
d = json.loads((A / 'evidence/scored_records.json').read_text())
assert d['overall']['scored'] == 190 and d['overall']['correct'] == 6354

replacements = {
    'px32-g16': {
        'source': SRC / '32px/g16_080_f32-g16_20261102_231613_681606_6547eeab.png',
        'sha256': 'f074fbe8aef7803aa1466839ae5723bafe03470045cba5b990d5ca08eeeffba7',
        'raw': 'I’m not seeing any letters right now. If you’re trying\nto show me something, you might need to adjust\nthe camera or let me know what you’d like me to\nread. Just let me know!',
        'transcription': '', 'result_class': '不可读', 'expected_correct': 0,
    },
    'px48-g11': {
        'source': SRC / '48px/g11_139_f48-g11_20261102_231744_213828_c8f9d10a.png',
        'sha256': '6c84265bbca483f2c6b2fe486868b44adfaba7f6d7d2fd132e795b99f69b435b',
        'raw': 'WEATFMVOYHCLUIIBZCDZGOLFRE\nQAXLGTHICKPHTUWHUVJOKUMA\nUOKAZHOICTFXPURNIKQTIROQOW\nECDAHVWPPSYPONNL',
        'transcription': 'WEATFMVOYHCLUIIBZCDZGOLFRE\nQAXLGTHICKPHTUWHUVJOKUMA\nUOKAZHOICTFXPURNIKQTIROQOW\nECDAHVWPPSYPONNL',
        'result_class': '部分转写', 'expected_correct': 67,
    },
}
manifest = []
for row in d['records']:
    cid = row['condition_id']
    if cid not in replacements:
        assert not row['anomaly'] and row['metrics']
        continue
    x = replacements[cid]
    assert row['anomaly'] and row['metrics'] is None
    old = copy.deepcopy(row)
    archived = A / 'evidence/screenshots' / str(row['font_px']) / Path(row['file']).name
    archived.parent.mkdir(parents=True, exist_ok=True)
    active_old = Path(row['file'])
    if active_old.exists():
        assert sha(active_old) == row['sha256']
        assert not archived.exists()
        shutil.move(active_old, archived)
    assert sha(archived) == row['sha256'] == sha(row['original_file'])
    assert x['source'].is_file() and sha(x['source']) == x['sha256']
    dest = O / 'evidence/screenshots' / str(row['font_px']) / x['source'].name
    shutil.copy2(x['source'], dest)
    assert sha(dest) == x['sha256']
    metrics = pipeline.score(d['reference'], x['transcription'])
    assert metrics['correct'] == x['expected_correct']
    row.update(file=str(dest), original_file=str(x['source']), sha256=x['sha256'],
               raw_response=x['raw'], transcription=x['transcription'],
               result_class=x['result_class'], result_note=x['result_class'],
               metrics=metrics, status='已评分', anomaly=False, anomaly_reason='',
               visual_checked=True, source_capture_round=6, experiment_round=3,
               user_prompt='Please read all the letters on the screen.')
    row.pop('blue_bottom', None)
    manifest.append(dict(condition_id=cid, old_record=old, archived_file=str(archived),
                         replacement_record=copy.deepcopy(row)))

assert len(manifest) == 2
d['summary'] = []
for font in (16, 24, 32, 40, 48, 64):
    rows = [r for r in d['records'] if r['font_px'] == font]
    correct = sum(r['metrics']['correct'] for r in rows)
    d['summary'].append(dict(font_px=font, available=32, scored=32, correct=correct, accuracy=correct/3200))
correct = sum(r['metrics']['correct'] for r in d['records'])
assert correct == 6421
d['overall'] = dict(available=192, scored=192, anomalies=0, missing=0, correct=correct,
                    denominator=19200, accuracy=correct/19200)
d.update(workbook_input=str(A / 'GPT_Advanced_实验结果03.xlsx'),
         workbook_input_sha256=sha(A / 'GPT_Advanced_实验结果03.xlsx'),
         source_capture_rounds=[5, 6], replacement_archive=str(A),
         replacement_manifest=str(A / 'replacement_manifest.json'),
         review=dict(unchanged_conditions=190, replaced_conditions=list(replacements),
                     all_conditions_present=True, stage='192项正式结果'))
(A / 'replacement_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
(O / 'evidence/scored_records.json').write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n')
inventory = json.loads((A / 'evidence/inventory.json').read_text())
current = {r['condition_id']: r for r in d['records']}
for item in inventory:
    row = current[item['condition_id']]
    for key in ['file', 'original_file', 'sha256']:
        item[key] = row[key]
    item.update(source_capture_round=row['source_capture_round'], experiment_round=3)
(O / 'evidence/inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n')
(O / 'evidence/anomalies.json').write_text('[]\n')
plan = O / 'evidence/异常补测清单.md'
if plan.exists():
    assert sha(plan) == sha(A / 'evidence/异常补测清单.md')
    os.replace(plan, A / 'evidence/异常补测清单.md')
assert len(list((O / 'evidence/screenshots').rglob('*.png'))) == 192
print('REPLACE PASS formal_images=192 scored=192 archived_anomalies=2 correct=6421/19200')
print(json.dumps(d['summary'], ensure_ascii=False))
