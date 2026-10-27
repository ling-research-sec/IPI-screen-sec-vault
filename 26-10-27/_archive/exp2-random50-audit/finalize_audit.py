from pathlib import Path
import json,re,hashlib,difflib,html,datetime
W=Path(__file__).resolve().parent;E=W.parent.parent/'exp2-perplexity'
read=lambda name:json.loads((W/name).read_text())
write=lambda name,value:(W/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
sample=read('sample-manifest.json');rows=read('checks.json');ocr={x['case_id']:x for x in read('ocr-results.json')}
followup=read('source-pixel-followup-160.json');changed=[x for x in followup['cases'] if not x['pixel_exact']];jpeg=read('source-pixel-jpeg-diagnostic.json')
assert len(rows)==len(ocr)==50 and [r['case_id'] for r in rows]==sample['draw_order']
assert len(changed)==4 and all(any(t['quality']==90 and t['exact'] for t in x['jpeg_roundtrip_tests']) for x in jpeg)
special={
 'f32-g30':'OCR将0识为O，并输出同形的西里尔字母；截图与保存文字未见内容冲突，字符编码以原UI XML交叉核对。',
 'f40-g10':'截图存在UI软换行，部分[UNK]跨显示行；逐行连接后内容对应。OCR误认方括号，不改原文的显式换行。',
 'f32-g25':'OCR在[UNK]后紧邻J处误识括号；截图可见[UNK]JC，保存原文及XML一致。'
}
for r in rows:
 expected=re.sub(r'\s+','',r['response']);actual=re.sub(r'\s+','',ocr[r['case_id']]['text']);exact=expected==actual
 diffs=[]
 for tag,a,b,c,d in difflib.SequenceMatcher(None,expected,actual,autojunk=False).get_opcodes():
  if tag!='equal':diffs.append({'kind':tag,'expected':expected[a:b],'ocr':actual[c:d],'expected_codepoints':[f'U+{ord(x):04X}' for x in expected[a:b]],'ocr_codepoints':[f'U+{ord(x):04X}' for x in actual[c:d]]})
 r['ocr_review']={'engine':'Apple Vision VNRecognizeTextRequest accurate/en-US; language correction disabled; no reference-text hints','exact_ignoring_whitespace':exact,'text':ocr[r['case_id']]['text'],'differences':diffs,'assessment':'独立OCR与原文一致（忽略空白）' if exact else special.get(r['case_id'],'OCR输出西里尔/拉丁同形字符差异；截图未见字形内容不符，UI XML与TXT字符编码一致。')}
 # This records the actual completed review of all25 two-case boards in this chat.
 r['visual_review']={'status':'NO_VISIBLE_REPLY_MISMATCH','reviewer':'assistant visual inspection, not a separate human sign-off','board':f'boards/pair-{(r["draw_index"]+1)//2:02d}.png','coverage':'reply region cropped from original screenshot, compared to raw TXT; input and source-screen text region also viewed','source_result':'PIXEL_EXACT' if r['source_pixels']['pixel_exact'] else 'SAME_TEXT_AND_POSITION_WITH_LOSSY_PIXEL_DIFFERENCE','note':special.get(r['case_id'],'已核对截图回复文字和保存原文；未见漏存、错配或显示区截断。')}
before=read('experiment2-before-sha256.json');after={str(p.relative_to(E)):hashlib.sha256(p.read_bytes()).hexdigest() for p in E.rglob('*') if p.is_file()};assert before==after
summary={'status':'PAIRING_PASS_WITH_INPUT_FIDELITY_EXCEPTIONS','date':'2026-10-27','population':160,'random_sample_size':50,'sampling_without_replacement':True,'sample_manifest_sha256':hashlib.sha256((W/'sample-manifest.json').read_bytes()).hexdigest(),'sample_seed_hex':sample['seed_hex'],'file_xml_table_score_checks_pass':50,'visual_reply_regions_reviewed':50,'visible_reply_mismatches_observed':0,'ocr_exact_ignoring_whitespace':sum(r['ocr_review']['exact_ignoring_whitespace'] for r in rows),'ocr_differences_visually_reviewed':sum(not r['ocr_review']['exact_ignoring_whitespace'] for r in rows),'unreadable_replies_in_sample':sum(r['response']=='[UNREADABLE]' for r in rows),'transcription_replies_in_sample':sum(r['response']!='[UNREADABLE]' for r in rows),'sample_source_pixel_exact':sum(r['source_pixels']['pixel_exact'] for r in rows),'sample_source_pixel_exceptions':[r['case_id'] for r in rows if not r['source_pixels']['pixel_exact']],'supplemental_source_pixel_scope':160,'supplemental_source_pixel_exact':156,'supplemental_exceptions':[x['case_id'] for x in changed],'jpeg_quality90_roundtrip_matches_all_four_in_roi':True,'specific_lossy_processing_stage':'not established','effect_on_model_answer':'not measured','formal_dataset_files_unchanged':len(before),'original_files_or_scores_modified':False,'new_device_or_assistant_requests':0,'limits':['Only50 reply screenshot regions were visually audited; the160-case follow-up checked source-screen pixels only.','31 sampled replies are the identical [UNREADABLE] string; response wording alone does not uniquely identify those cases.','Source-screen evidence does not directly reveal the model internal image input.','A matching hash is an integrity check, not an independent content verification; screenshot comparison was performed separately.']}
write('checks.json',rows);write('audit-summary.json',summary)
table=['| 抽样序号 | 条件 | 回答配对 | 源屏像素 | 独立OCR | 对照图 |','| ---: | --- | --- | --- | --- | --- |']
for r in rows:table.append(f'| {r["draw_index"]} | {r["case_id"]} | 未见错配 | {"逐像素一致" if r["source_pixels"]["pixel_exact"] else "有损差异，待复核"} | {"一致" if r["ocr_review"]["exact_ignoring_whitespace"] else "差异已目视/原XML复核"} | [查看]({r["visual_review"]["board"]}) |')
issue_table=['| 条件 | 在随机50条中 | 原PNG最大灰度 | 源屏文字区最大值 | 最大逐像素差 | JPEG90诊断 |','| --- | --- | ---: | ---: | ---: | --- |']
for r in changed:issue_table.append(f'| {r["case_id"]} | {"是" if r["case_id"] in sample["draw_order"] else "否，补充检查发现"} | {r["input_max"]} | {r["source_screen_max"]} | {r["max_abs_difference"]} | 文字区像素完全相同 |')
report=f'''# 实验二：随机50条图片—回答证据抽检

## 结论

**回答配对：50条均未观察到截图回复与保存原文错配、漏存或回复显示区截断。输入图像保真：存在例外，不能据此给整批数据无保留的“完全通过”。**

本次核对的是“截图中模型实际回答的文字是否被原样保存”，不是要求模型回答与参考字符完全相同。识读错字按原规则计分，不等于证据配对错误。

- 50条文件、条件、哈希、归档UI XML、TXT、JSON、XLSX原文及确定性评分全部相符；另逐张目视核对了50张回复截图的答复区域。
- 样本包括31条[UNREADABLE]、19条有转写内容的回复。独立OCR禁用语言纠错：39/50忽略空白后完全一致；11条OCR差异另行目视并与原UI XML交叉核对，涉及O/0、方括号、UI软换行和Unicode同形字，未修改任何原文。
- 随机样本的原PNG与源屏文字区域48/50逐像素一致；f32-g19、f40-g31字形内容/位置对应，但存在有损像素差异。
- 针对该现象补查全部160条**源屏像素**，发现4条例外，其余156条完全一致。该补查不是“160张回复截图都已目视审查”。
- 正式实验目录原有{len(before)}个文件的哈希和文件集合均不变；未改分、未排除已有正式记录、未重跑实验、未调用手机或助手。

## 抽样方法

总体为实验二第01轮160条正式记录，不含48px历史基线和被排除的失败尝试。按case ID排序，使用一次性随机种子，不放回随机抽取50条；先锁定[抽样清单](sample-manifest.json)再执行检查。会话中断后沿用同一份清单，没有为了结果重新抽样。

- 随机种子：`{sample['seed_hex']}`。
- 字号分布：16px=7、24px=14、32px=8、40px=12、64px=9；非人为等额分层。
- 抽样比例50/160=31.25%。[结构化检查结果](checks.json)逐条保存检查项、像素指标、OCR输出及目视结论。

复现抽样（只读）：

```python
random.Random(int(seed_hex,16)).sample(sorted_population,50)
```

## 图片与回答如何对应

1. 原PNG的SHA-256与素材manifest、记录source_sha256及采集时记录的phone_source_sha256核对；核对字号、Δg、轮次与case ID。
2. 源屏截图的文字区与对应原PNG比较；归档source-query核对MediaStore显示文件名及目录。
3. 从原回复截图裁取UI XML指示的答复区域，进行独立Apple Vision OCR和逐张目视对照；OCR未输入参考答案/正确转写提示。
4. 回复截图↔原TXT↔记录response↔原answer.xml↔XLSX“完整回复”交叉核对，同时检查复制控件、无思考状态和归档完成状态。
5. 使用原规则重新计算正确、替换、删除、插入、CER，与保存分数及表格逐项比较。

[打开全部25张双案例对照板](index.html)。左侧原图/源屏裁块使用相同倍数增强亮度，仅便于核对字形和位置；实际逐像素计算在未经增强的RGB数据上进行。中间为实际截图的回复区域，右侧为原TXT；图中可视化增强不是实验输入，不影响原文件。

## 输入显示保真例外

{chr(10).join(issue_table)}

这里的4条是最终160条正式结果中的恢复后记录，**不是excluded中的失败尝试**。此前隔离失败尝试并未消除这4条正式源屏的像素差异。

比较区域固定为原屏坐标`[65,650,1030,1120)`，覆盖五种字号全部文字并排除系统状态栏/侧边手势条。PNG按RGB比较，忽略全不透明alpha；没有用“RGB最大值”替代整个图案的像素核对，也没有把最大值直接当作新的Δg标签。

对这4张原PNG分别做JPEG quality=90、subsampling=0的本地编码—解码诊断，重建后的文字区域与对应源屏**逐像素完全一致**。这一可复现特征说明源屏存在与JPEG90有损处理等价的像素变化；具体发生在图库预览、其他显示处理还是采集链条哪个环节，当前证据尚未定位。四条均对应先前的独立恢复/最小测试；关联不等于因果证实。

因此，4条的名义灰度仍是原PNG参数，但落屏字形边缘/局部灰度不与其余156条完全同一保真条件。尤其32px/g19恰处于该字号首次非零识读结果处，严格阈值解释应先保留这一不确定性。识读结果实际受影响多少未测量，不能据此反推“没有影响”或直接改分。

建议在后续分析中单独标注这4条输入显示一致性例外；如需排除、敏感性分析或补测，应保留原记录，并另建有明确原因的新记录。本次只报告问题，不擅自改动正式数据。

## 证据边界

- 31条[UNREADABLE]回复在文字层面相同，不具有独立的唯一case辨识性；这些case的关联还依靠输入图、source-query、条件、记录和归档哈希，不能仅凭相同回答字符串证明对应关系。
- 像素图形不独立证明Unicode代码点。OCR同形字差异结合原UI XML/TXT核对；具体差异代码点保存在checks.json。
- 本次验证的是留存证据的内部一致性及图片中的可见内容，不等于直接截获并证明了模型内部实际接收的图像。
- 先前收尾的160条“哈希/记录通过”不等于已验证160条源屏逐像素保真；本次增加的像素检查发现了上述4条例外。

## 随机50条逐项清单

{chr(10).join(table)}

## 文件与复核记录

- [抽样清单](sample-manifest.json)、[汇总结论](audit-summary.json)、[逐项检查](checks.json)、[独立OCR原结果](ocr-results.json)。
- [源屏160条针对性补查](source-pixel-followup-160.json)、[JPEG编码—解码诊断](source-pixel-jpeg-diagnostic.json)。
- 本Agent已逐张查看boards/pair-01.png至pair-25.png的50个答复区域；这不是另一个人类审查员的签字记录。
- 脚本：audit.py、ocr.swift、finalize_audit.py；原始数据只读，新增文件全部位于本抽检过程目录。
'''
(W/'AUDIT.md').write_text(report)
esc=html.escape
parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>实验二随机50条证据抽检</title><style>body{font:16px/1.6 system-ui;margin:24px auto;max-width:1500px;padding:0 20px;background:#f5f5f5;color:#111}header,section{background:white;padding:20px;margin-bottom:20px;border:1px solid #ddd}img{width:100%;height:auto}a{color:#1456a0}.issue{border-left:6px solid #d58a00}code{overflow-wrap:anywhere}li{margin:6px 0}</style><header><h1>随机50条证据抽检</h1><p>回答内容配对：50条未见错配。源屏像素：样本48/50一致；针对性全量检查156/160一致。</p><p class="issue">需复核的输入显示保真例外：f16-g01、f24-g16、f32-g19、f40-g31。文字区像素与JPEG90编码—解码结果完全一致，具体处理环节未定位；未改动原数据。</p><p>左侧裁块增强亮度仅用于本次核图；中栏来自真实回复截图，右栏为原TXT。点击对照板查看原尺寸。</p><p><a href="AUDIT.md">完整报告</a> · <a href="sample-manifest.json">锁定的抽样清单</a> · <a href="checks.json">逐项检查</a></p></header>']
for i in range(25):
 subset=rows[i*2:i*2+2];image=f'boards/pair-{i+1:02d}.png';parts.append(f'<section><h2>{i*2+1}–{i*2+2} / 50</h2><a href="{image}"><img loading="lazy" src="{image}" alt="{esc(subset[0]["case_id"])} / {esc(subset[1]["case_id"])}"></a><ul>')
 for r in subset:
  case=r['case_id'];base='../../exp2-perplexity/evidence-01';parts.append(f'<li><strong>{case}</strong>：<a href="{base}/source-images/{case}.png">原PNG</a> · <a href="{base}/source-screens/g{case}-source-clean.png">原源屏</a> · <a href="{base}/screenshots/exp2-screenshot-{case}.png">完整回复截图</a> · <a href="{base}/responses/exp2-response-{case}.txt">原TXT</a></li>')
 parts.append('</ul></section>')
parts.append('</html>');(W/'index.html').write_text(''.join(parts))
write('audit-artifact-sha256.json',{str(p.relative_to(W)):hashlib.sha256(p.read_bytes()).hexdigest() for p in W.rglob('*') if p.is_file() and p.name not in ['audit-artifact-sha256.json']})
print(json.dumps(summary,ensure_ascii=False,indent=2))
