from pathlib import Path
import json,hashlib,zipfile,subprocess
ROOT=Path.cwd();W=ROOT/'26-10-27/_archive/exp2-commit-rounds02-03';E=ROOT/'26-10-27/exp2-perplexity';ARCH=ROOT/'26-10-27/_archive/exp2-perplexity-pipeline-20261027T060204Z-a66186.zip'
sha=lambda data:hashlib.sha256(data).hexdigest()
def save(file,data):file.parent.mkdir(parents=True,exist_ok=True);file.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
archive_hash=sha(ARCH.read_bytes());results=[]
with zipfile.ZipFile(ARCH) as z:
 manifest_bytes=z.read('manifest.json');manifest=json.loads(manifest_bytes)
 for n in [2,3]:
  ev=E/f'evidence-{n:02d}';entries=[];used_members={};protocols=set();case_ids=[]
  def extract(member,dest,kind,case=None):
   data=z.read(member);assert sha(data)==manifest['files'][member]
   assert not dest.exists();dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
   entry=dict(kind=kind,file=str(dest.relative_to(ev)),sha256=sha(data),source_archive=ARCH.name,source_archive_sha256=archive_hash,source_member=member)
   if case:entry['case_id']=case
   entries.append(entry);used_members[member]=sha(data)
  for record in sorted((ev/'records').glob('exp2-result-*.json')):
   r=json.loads(record.read_text());case=r['case_id'];assert r['round']==n;case_ids.append(case);protocols.add(r['protocol_archive_member'])
   prefix=f'round{n:02d}/g{case}/'
   members=[m for m in manifest['files'] if m.startswith(prefix)]
   assert {r['answer_xml_archive_member'],r['prompt_xml_archive_member'],prefix+'state.json'}.issubset(members)
   for member in sorted(members):extract(member,ev/'ui'/case/member.removeprefix(prefix),'formal/'+member.removeprefix(prefix),case)
  for state in (ev/'excluded').rglob('state.json'):
   d=json.loads(state.read_text())
   if d.get('protocol_archive_member'):protocols.add(d['protocol_archive_member'])
  for member in sorted(protocols):extract(member,ev/'ui/protocols'/Path(member).name,'protocol')
  for f in sorted((ev/'excluded').rglob('*')):
   if f.is_file():entries.append(dict(kind='excluded-original',file=str(f.relative_to(ev)),sha256=sha(f.read_bytes()),source_path=str(f.relative_to(E))))
  scoped=ev/'ui/archive-manifests'/f'{ARCH.stem}-round{n:02d}.json'
  save(scoped,dict(source_archive=ARCH.name,source_archive_sha256=archive_hash,source_manifest_sha256=sha(manifest_bytes),说明='按本轮提取成员筛选的清单，不是对原归档manifest字节的改写；原归档仅作来源记录。',round=n,files=used_members))
  entries.append(dict(kind='source-archive-manifest-filtered',file=str(scoped.relative_to(ev)),sha256=sha(scoped.read_bytes()),source_archive=ARCH.name,source_archive_sha256=archive_hash))
  save(ev/'UI证据索引.json',dict(round=n,说明='file相对本证据目录；原始记录的ui_archive与成员名保留采集历史。本索引指向逐字节提取并校验、可在仓库内独立查看的UI、协议和源屏门禁证据；不依赖本地_archive下载。',formal_cases=len(case_ids),entries=entries))
  assert len(case_ids)==160
  for entry in entries:assert sha((ev/entry['file']).read_bytes())==entry['sha256']
  results.append(dict(round=n,formal_cases=160,ui_archive_members=len(used_members),indexed_files=len(entries),protocols=len(protocols)))
# Keep the actual fixed random sample and its checks inspectable in the round03 commit.
audit=ROOT/'26-10-27/_archive/exp2-random100-audit-02-03'
manifest_sample=json.loads((audit/'sample-manifest.json').read_text());summary=json.loads((audit/'audit-summary.json').read_text());checks=json.loads((audit/'checks.json').read_text());portable=[]
for row in checks:
 item=dict(row);item['original_png']=str(Path(item['original_png']).relative_to('26-10-27/exp2-perplexity'));item['source_screen']=str(Path(item['source_screen']).relative_to('26-10-27/exp2-perplexity'));item['reply_screenshot']=str(Path(item['reply_screenshot']).relative_to('26-10-27/exp2-perplexity'))
 item['reply_crop_local_process_member']=item.pop('reply_crop');item['board_local_process_member']=item.pop('board');item['visual_review']=dict(item['visual_review']);item['visual_review']['board_local_process_member']=item['visual_review'].pop('board');portable.append(item)
save(E/'evidence-03/records/audit-random100-02-03.json',dict(说明='新增02/03轮320条有效试次中的一次固定随机100抽检；2条额外定向检查不计入随机100。图片路径相对exp2-perplexity根目录；对照板和OCR过程材料留在本地_archive，原始图片/UI/协议可由每轮UI证据索引独立定位。',sample=manifest_sample,summary=summary,checks=portable,visual_review=json.loads((audit/'visual-review.json').read_text()),audit_summary_source_sha256=sha((audit/'audit-summary.json').read_bytes()),sample_source_sha256=sha((audit/'sample-manifest.json').read_bytes())))
# Local-only process directory follows the existing previous-day ignore convention.
gitignore=ROOT/'.gitignore';ignore=gitignore.read_text();assert '/26-10-27/_archive/' not in ignore;gitignore.write_text(ignore.rstrip()+'\n/26-10-27/_archive/\n')
# Prepare a round02-only description for the first commit; leave the final text in the working tree.
base=subprocess.check_output(['git','show','HEAD:26-10-27/exp2-perplexity/实验说明.md'],text=True)
intro='''## 第02轮完成情况（2026-10-27）

- 本轮160/160条有效结果：16、24、32、40、64px各覆盖Δg1–32，每条件1次。固定字符、原PNG、排版、Prompt、默认助手、最大亮度和确定性评分沿用01轮；48px仍只读引用实验一历史3轮。
- 采集时间14:05:36–16:07:43（Asia/Taipei），正确5652/16000字符，跨160条件平均正确率35.32500%；无未完成条件。原PNG、完整回复、截图、源屏与评分记录全部齐全。
- [实验结果-02.xlsx](实验结果-02.xlsx)含“实验结果”“完整回复”两页签，各160条；条件ID显示px前缀，可按字号、Δg、轮次筛选。未增加复测结论，不修改01结果或实验一历史文件。
- 4次发送前准备中断（锁屏1次、源屏保真门禁未通过2次、初选Python缺少Pillow1次）均未发起助手请求，已保存在evidence-02/excluded/，不计分。正式试次发送前均连续2帧文字区RGB与原PNG逐像素一致，不把流程中断记为识别0分。
- [第02轮UI证据索引](evidence-02/UI证据索引.json)直接指向仓库内逐字节提取并校验的原始XML、输入／提示词截图、源屏门禁帧、状态、素材查询及协议。原JSON的ui_archive及成员名保留采集历史，不作为仓库下载入口；来源清单按本轮筛选并明确标注。
- Skill report／verify、XLSX两页签、源屏像素及归档恢复核验通过。脚本、日志、预览和本地归档留在上一级_archive/，不纳入提交；第01轮原数据和证据保持不变。

以下为第01轮已提交说明及历史统计。

'''
first,rest=base.split('\n',1);doc02=first.replace('第01轮','第01–02轮')+'\n\n'+intro+rest.lstrip();(W/'notes-round02.md').write_text(doc02)
# Add portable repository links for final state, rather than linking to ignored process HTML.
md=E/'实验说明.md';final=md.read_text();final=final.replace('[100条抽检对照页](../_archive/exp2-random100-audit-02-03/index.html)','本机抽检对照页`../_archive/exp2-random100-audit-02-03/index.html`（本地过程文件，不纳入提交）')
needle='### 随机100条图片—回答证据抽检（2026-10-27）'
addition='''### 仓库内独立证据入口

- [第02轮UI证据索引](evidence-02/UI证据索引.json)、[第03轮UI证据索引](evidence-03/UI证据索引.json)提供各轮160条正式试次的原始XML、提示词截图、源屏门禁帧、素材查询、完成状态与协议；均从已验证归档逐字节提取并再次核对SHA-256。
- 原JSON中的ui_archive与成员路径保持采集历史，不改写记录或分数；仓库内查看以本轮索引的相对路径为准。来源归档清单按轮次筛选，明确保留原归档及原manifest哈希。
- [随机100条抽检清单与逐项结果](evidence-03/records/audit-random100-02-03.json)随第03轮保存，覆盖已提交的第02轮及本轮；原图、源屏和回复截图路径相对本实验目录。预览板、临时脚本、日志及ZIP仍只保留在本地_archive/。

'''
assert needle in final;md.write_text(final.replace(needle,addition+needle,1));(W/'notes-final.md').write_text(md.read_text())
save(W/'prepare-verification.json',dict(status='PASS',rounds=results,raw_data_workbooks_modified=False,audit_rows=102,random_sample_size=100))
print(json.dumps(results,ensure_ascii=False))
