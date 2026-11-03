import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const root='/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault',out=root+'/26-11-02/exp3-gpt-advanced',work=root+'/26-11-02/_archive/exp3-gpt-analysis';
const d=JSON.parse(await fs.readFile(out+'/evidence/scored_records.json','utf8'));
const w=await SpreadsheetFile.importXlsx(await FileBlob.load(d.workbook_input));
const s=w.worksheets.getItem('实验结果'),r=w.worksheets.getItem('完整回复');
if(process.argv.includes('--baseline')){
 assert.equal(s.getRange('B203').values[0][0],6354);
 assert.equal(s.getRange('F4').values[0][0],192);
 const b=await w.render({sheetName:'实验结果',range:'A1:U16',scale:1,format:'png'});await fs.writeFile(work+'/baseline.png',new Uint8Array(await b.arrayBuffer()));
 console.log('BASELINE PASS round=03 images=192 scored=190 correct=6354');process.exit(0);
}
assert.equal(d.records.length,192);assert.equal(r.getRange('B5').values[0][0],d.reference);
s.getRange('A2').values=[['GPT Advanced 屏幕识读实验（第03轮）']];
s.getRange('A5').values=[['2026-11-02　Advanced Voice／Screen　第03轮　6字号×32灰度']];
s.getRange('A6').values=[['跨条件SD表示本轮192个条件的离散程度，不代表同条件重复测量误差。']];
s.getRange('A7').values=[['手动255；原始回复与负结果保留。']];
s.getRange('O3').values=[[`截图${d.overall.available}，已评分${d.overall.scored}，异常${d.overall.anomalies}，缺图${d.overall.missing}。`]];
s.getRange('O4').values=[['每个条件对应一张正式截图及一条完整回复。']];
r.getRange('A2').values=[['完整回复与参考字符（GPT Advanced · 第03轮）']];
r.getRange('A3').values=[['192个条件的完整回复；截图文件名见右列，来源见证据清单。']];
r.getRange('A7').values=[['原文不补全、不纠错；不识读的真实回复照常保留。']];
s.getRange('A10:B201').values=d.records.map(x=>[x.condition_id,x.metrics?.correct??null]);
s.getRange('D10:I201').values=d.records.map(x=>[x.metrics?.substitutions??null,x.metrics?.deletions??null,x.metrics?.insertions??null,x.metrics?.unk_tokens??null,'手动255',x.result_note]);
s.getRange('J10:L201').values=d.records.map(x=>[x.font_px,x.gray,3]);
r.getRange('A9:C200').values=d.records.map(x=>[x.condition_id,x.raw_response,x.file?path.basename(x.file):null]);
r.getRange('C9:C200').format.wrapText=true;
s.getRange('C10:C201').clear({applyTo:'contents'});s.getRange('M10:M201').clear({applyTo:'contents'});
s.getRange('C10:C201').formulas=d.records.map((_,i)=>[`=IF(ISBLANK(B${i+10}),"",B${i+10}/100)`]);
s.getRange('M10:M201').formulas=d.records.map((_,i)=>[`=IF(ISBLANK(B${i+10}),"",(D${i+10}+E${i+10}+F${i+10})/100)`]);
s.getRange('P10:U41').clear({applyTo:'contents'});
s.getRange('P10:U41').formulas=Array.from({length:32},(_,g)=>Array.from({length:6},(_,f)=>`=IF(ISNUMBER(C${10+f*32+g}),C${10+f*32+g},"")`));
s.getRange('F4').formulas=[["=COUNTA('完整回复'!C9:C200)"]];
s.getRange('C203').formulas=[['=B203/(100*COUNT(B10:B201))']];
s.getRange('M203').formulas=[['=(D203+E203+F203)/(100*COUNT(B10:B201))']];
s.getRange('I203').values=[[`${d.overall.denominator}个参考字符（已评分）`]];
for(let i=0;i<192;i++){
 const x=d.records[i],raw=x.raw_response??'',lines=raw.split('\n').reduce((n,l)=>n+Math.max(1,Math.ceil(l.length/112)),0);
 r.getRange(`A${i+9}:C${i+9}`).format.rowHeight=Math.max(38,lines*15+8);
 if(x.anomaly){s.getRange(`I${i+10}`).format.wrapText=true;s.getRange(`A${i+10}:M${i+10}`).format.rowHeight=Math.max(38,Math.ceil(x.result_note.length/20)*15+8);}
}
for(const row of [89,148])s.getRange(`A${row}:M${row}`).format.rowHeight=s.getRange(`A${row-1}:M${row-1}`).format.rowHeight;
w.recalculate();
assert.equal(s.getRange('B203').values[0][0],d.overall.correct);assert.equal(s.getRange('F4').values[0][0],d.overall.available);
assert.ok(Math.abs(s.getRange('C203').values[0][0]-d.overall.accuracy)<1e-12);
for(let i=0;i<192;i++){
 const x=d.records[i],v=s.getRange(`C${i+10}`).values[0][0];
 if(x.metrics)assert.ok(Math.abs(v-x.metrics.accuracy)<1e-12);else assert.ok(v===null||v==='');
}
const test=10+d.records.findIndex(x=>x.metrics?.correct>0),old=s.getRange(`B${test}`).values[0][0];
s.getRange(`B${test}`).values=[[0]];assert.equal(s.getRange(`C${test}`).values[0][0],0);
s.getRange(`B${test}`).values=[[null]];assert.ok(s.getRange(`C${test}`).values[0][0]==='');
assert.ok(Math.abs(s.getRange('C203').values[0][0]-(d.overall.correct-old)/((d.overall.scored-1)*100))<1e-12);
s.getRange(`B${test}`).values=[[old]];w.recalculate();
for(const sheet of [s,r])for(const row of sheet.getUsedRange().values)for(const v of row)if(typeof v==='string')assert.ok(!/^#(?:REF!|DIV\/0!|VALUE!|NAME\?|N\/A|NUM!|NULL!|SPILL!|CALC!)$/.test(v));
console.log((await w.inspect({kind:'region',sheetId:'实验结果',range:'A2:M7',maxChars:1800,tableMaxRows:6,tableMaxCols:13})).ndjson);
for(const [sheetName,range,name] of [['实验结果','A1:U15','overview'],['完整回复','A1:C12','replies'],['实验结果','A88:M90','replaced32'],['实验结果','A146:M149','replaced48'],['完整回复','A87:C89','reply32'],['完整回复','A146:C148','reply48'],['实验结果','A203:M205','totals']]){
 const b=await w.render({sheetName,range,scale:1,format:'png'});await fs.writeFile(work+'/'+name+'.png',new Uint8Array(await b.arrayBuffer()));
}
await(await SpreadsheetFile.exportXlsx(w)).save(out+'/GPT_Advanced_实验结果03.xlsx');
console.log(`AUTHOR PASS registered=192 images=${d.overall.available} scored=${d.overall.scored} missing=${d.overall.missing} anomalies=${d.overall.anomalies} correct=${d.overall.correct}`);
