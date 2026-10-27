#!/usr/bin/env python3
"""Prepare byte-exact evidence extractions without changing formal files."""
import difflib
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
WORK = Path(__file__).resolve().parent
BASE = REPO / '26-10-27/exp2-perplexity'
EVIDENCE = BASE / 'evidence-01'
ARCHIVES = REPO / '26-10-27/_archive'
STAGE = WORK / 'staging'
STAGED_EVIDENCE = STAGE / 'evidence-01'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if STAGE.exists():
        raise RuntimeError('staging already exists; refusing to overwrite')
    STAGED_EVIDENCE.mkdir(parents=True)
    baseline = json.loads((WORK / 'baseline/formal-sha256.json').read_text(encoding='utf-8'))
    current = {str(p.relative_to(BASE)): digest(p.read_bytes()) for p in BASE.rglob('*') if p.is_file() and p.name != '.DS_Store'}
    if current != baseline['files']:
        raise RuntimeError('formal files changed after baseline; stop')
    entries, written, archives = [], {}, {}

    def archive(name):
        if name not in archives:
            p = ARCHIVES / name
            if digest(p.read_bytes()) != baseline['archives'][name]:
                raise RuntimeError(f'archive hash changed: {name}')
            z = zipfile.ZipFile(p)
            archives[name] = (z, json.loads(z.read('manifest.json'))['files'])
        return archives[name]

    def add_bytes(rel, data, *, kind, case=None, source_archive=None, source_member=None, source_path=None):
        if rel in written:
            if written[rel] != digest(data):
                raise RuntimeError(f'conflicting extraction: {rel}')
            return
        dest = STAGED_EVIDENCE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        item = {'kind': kind, 'file': rel, 'sha256': digest(data)}
        if case is not None:
            item['case_id'] = case
        if source_archive is not None:
            item['source_archive'] = source_archive
            item['source_member'] = source_member
        if source_path is not None:
            item['source_path'] = source_path
        entries.append(item)
        written[rel] = digest(data)

    def extract(name, member, rel, *, kind, case=None, manifest_required=True):
        z, manifest = archive(name)
        data = z.read(member)
        if manifest_required and manifest.get(member) != digest(data):
            raise RuntimeError(f'archive member hash mismatch: {name}/{member}')
        add_bytes(rel, data, kind=kind, case=case, source_archive=name, source_member=member)

    def extract_case(record, destination, category):
        case = record['case_id']
        name = Path(record['ui_archive']).name
        prefix = f'round01/g{case}/'
        for member in ('answer.xml', 'input.xml', 'prompt.xml', 'source-clean.xml',
                       'source-initial.xml', 'source-query.txt', 'state.json'):
            extract(name, prefix + member, f'{destination}/{member}', kind=f'{category}/{member}', case=case)
        member = record['protocol_archive_member']
        extract(name, member, f'ui/protocols/{Path(member).name}', kind='protocol')

    records = sorted((EVIDENCE / 'records').glob('exp2-result-*.json'))
    if len(records) != 160:
        raise RuntimeError('expected exactly 160 formal records')
    retested = []
    for path in records:
        record = json.loads(path.read_text(encoding='utf-8'))
        case = record['case_id']
        extract_case(record, f'ui/{case}', 'formal')
        if 'quality_retest' in record:
            retested.append(case)
            name = Path(record['ui_archive']).name
            for member in ('source-fidelity.json', 'source-fidelity/01.png', 'source-fidelity/02.png'):
                extract(name, f'round01/g{case}/{member}', f'ui/{case}/{member}', kind='retest-fidelity', case=case)
    if sorted(retested) != ['f16-g01', 'f24-g16', 'f32-g19', 'f40-g31']:
        raise RuntimeError('unexpected retest set')
    for case in retested:
        old = EVIDENCE / 'excluded/fidelity-superseded-20261027' / case / 'records' / f'exp2-result-{case}.json'
        old_record = json.loads(old.read_text(encoding='utf-8'))
        extract_case(old_record, f'excluded/fidelity-superseded-20261027/{case}/ui', 'superseded')

    original_attempt = ARCHIVES / 'exp2-process/interrupted-attempt-01'
    for p in sorted(original_attempt.rglob('*')):
        if p.is_file():
            sub = str(p.relative_to(original_attempt))
            add_bytes(f'excluded/attempt-01-f16-g01-interrupted/{sub}', p.read_bytes(), kind='interrupted-attempt-01',
                      case='f16-g01', source_path=f'exp2-process/interrupted-attempt-01/{sub}')

    retest_name = Path(json.loads((EVIDENCE / 'records/exp2-result-f16-g01.json').read_text(encoding='utf-8'))['ui_archive']).name
    z, _ = archive(retest_name)
    prefix = 'migration/pre-send-excluded/pre-send-f16-g01-cached-preview/'
    names = [n for n in z.namelist() if n.startswith(prefix) and not n.endswith('/')]
    if len(names) != 24:
        raise RuntimeError('unexpected pre-send excluded evidence count')
    for member in sorted(names):
        extract(retest_name, member, 'excluded/fidelity-pre-send-f16-g01/' + member[len(prefix):],
                kind='fidelity-pre-send-excluded', case='f16-g01')

    for name in sorted(archives):
        extract(name, 'manifest.json', f'ui/archive-manifests/{name}.manifest.json',
                kind='source-archive-manifest', manifest_required=False)
    for z, _ in archives.values():
        z.close()
    index = {'round': 1, '说明': 'file相对本证据目录；原始记录中的归档路径保留采集历史，本索引指向逐字节提取并校验的当前证据。',
             'entries': sorted(entries, key=lambda x: x['file'])}
    (STAGED_EVIDENCE / 'UI证据索引.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    before = (WORK / 'baseline/实验说明.md').read_text(encoding='utf-8')
    old = '- case ID为f16-g01等，字号、Δg和轮次独立记录。同一灰度的不同字号不互相覆盖。'
    new = '- 原始记录的case ID为f16-g01等；结果表显示px16-g01等，`px`与原始记录中的`f`按字号和Δg一一对应。字号、Δg和轮次独立记录，同一灰度的不同字号不互相覆盖。'
    if before.count(old) != 1:
        raise RuntimeError('case ID note anchor changed')
    after = before.replace(old, new)
    old_attempt = '../_archive/exp2-process/interrupted-attempt-01/'
    new_attempt = 'evidence-01/excluded/attempt-01-f16-g01-interrupted/'
    if after.count(old_attempt) != 1:
        raise RuntimeError('first attempt anchor changed')
    after = after.replace(old_attempt, new_attempt)
    failed_gate_old = '复测准备期间有1次未通过显示门禁，未唤醒或发送助手请求；修正素材加载路径后4次真实复测全部完成。'
    failed_gate_new = '复测准备期间有1次未通过显示门禁，未唤醒或发送助手请求；[该次门禁证据](evidence-01/excluded/fidelity-pre-send-f16-g01/)单独保留。修正素材加载路径后4次真实复测全部完成。'
    if after.count(failed_gate_old) != 1:
        raise RuntimeError('failed fidelity gate anchor changed')
    after = after.replace(failed_gate_old, failed_gate_new)
    start = '## 文件、验证与归档\n'
    end = '## 使用边界与后续\n'
    if after.count(start) != 1 or after.count(end) != 1:
        raise RuntimeError('closeout section anchor changed')
    lead, remainder = after.split(start, 1)
    _, tail = remainder.split(end, 1)
    section = '''## 文件、验证与归档

- 正式目录保留本说明、实验结果-01.xlsx及evidence-01/。结果表中的`px16-g01`等是原始case ID `f16-g01`等的显示别名，不改变正式记录、素材文件名或分数。
- evidence-01/source-images/：160张原PNG；records/image-manifest.json逐图记录字号、Δg、原参考字符、布局、相对路径和SHA-256。
- evidence-01/records/exp2-result-*.json、responses/、screenshots/、source-screens/：各160份正式评分记录、完整回复、助手截图和源屏；baseline48-reference.json为历史数据只读引用。
- [UI证据索引](evidence-01/UI证据索引.json)指向各正式条件独立保留的原始输入框、提示词、回复和源屏XML、素材查询、状态、协议与复测门禁证据；索引记录当前路径、原归档成员及SHA-256。4条被替代记录的原始UI证据、5次异常尝试和1次复测前门禁失败证据在excluded/中保留，不计入正式结果。
- 原始JSON中的`ui_archive`及归档成员路径保留采集历史，不作为仓库内下载入口；可通过UI证据索引定位独立提取的文件。两份原归档的manifest也保留在ui/archive-manifests/中。
- 提交前以当前结果表复核160条记录、原文、评分、源屏文字区及48px历史引用；源屏文字区是唤醒前画面，不等于直接截获模型内部输入。4条复测替换及旧记录哈希见[替换清单](evidence-01/records/quality-retest-20261027.json)。
- 配置、脚本、日志、测试证据和复测前后ZIP快照保留在本机上一级_archive/，不纳入本轮提交。Skill原件和实验一原文件未改写。复测后快照记录当时状态；其后结果表调整了条件显示标识、格式和说明文字，故当前表格文件哈希与快照不同，分数及完整回复未变。
- 新字号每个条件仅一次有效测量；已完成本轮采集与证据整理，后续新增轮次和曲线绘制不属于本轮未完成项。

'''
    after = lead + section + end + tail
    (STAGE / '实验说明.md').write_text(after, encoding='utf-8')
    diff = ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile='实验说明.md (baseline)', tofile='实验说明.md (delivery)'))
    (WORK / '实验说明.diff').write_text(diff, encoding='utf-8')
    added = {str(p.relative_to(STAGE)): digest(p.read_bytes()) for p in sorted(STAGE.rglob('*'))
             if p.is_file() and p != STAGE / '实验说明.md'}
    plan = {'added_files': added, 'modified_notes_sha256': digest((STAGE / '实验说明.md').read_bytes()),
            'original_notes_sha256': baseline['files']['实验说明.md'], 'formal_files_before': len(baseline['files']),
            'indexed_files': len(entries), 'retested_cases': sorted(retested)}
    (WORK / 'delivery-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PREPARE: indexed_files={len(entries)} added_files={len(added)} retests={len(retested)}')
    print('PREPARE: baseline_notes_and_workbook_preserved')
    print('PREPARE: PASS')


if __name__ == '__main__':
    main()
