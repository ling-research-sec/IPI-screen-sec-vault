import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const W=path.dirname(new URL(import.meta.url).pathname);
const input=JSON.parse(await fs.readFile(path.join(W,'replacements.json'),'utf8'));
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(input.old_workbook));
const s=wb.worksheets.getItem('实验结果'),raw=wb.worksheets.getItem('完整回复');
const oldMain=s.getRange('A10:M169').values,oldRaw=raw.getRange('A9:N168').values;
const formulas=JSON.stringify(s.getRange('A1:U174').formulas);
const changed=new Set();let expectedTotal=oldMain.reduce((a,r)=>a+r[1],0);
for(const item of input.cases){
 const idx=oldMain.findIndex(r=>String(r[0])===item.case_id);if(idx<0)throw new Error('Case missing');
 const row=idx+10,rr=idx+9,o=item.old,n=item.new;
 if(oldMain[idx][1]!==o.correct||raw.getRange(`B${rr}`).values[0][0]!==o.response)throw new Error('Old data differs from preserved evidence');
 for(const [col,key] of [['B','correct'],['D','substitutions'],['E','deletions'],['F','insertions'],['G','unk_tokens']])s.getRange(`${col}${row}`).values=[[n[key]]];
 s.getRange(`I${row}`).values=[[n.exact_transcription?'完整转写':n.unreadable?'不可读':'部分转写']];
 raw.getRange(`B${rr}`).values=[[n.response.startsWith('=')?"'"+n.response:n.response]];
 if(n.response.includes('\n'))raw.getRange(`A${rr}:C${rr}`).format.rowHeight=Math.max(115,n.response.split('\n').length*16+12);
 expectedTotal+=n.correct-o.correct;changed.add(idx);
}
s.getRange('A7').values=[['已按源屏一致性复测替换4条；其余156条不变。48px仍引用历史3轮均值。']];
wb.recalculate();
if(s.getRange('B171').values[0][0]!==expectedTotal||s.getRange('F4').values[0][0]!==160)throw new Error('Summary mismatch');
if(JSON.stringify(s.getRange('A1:U174').formulas)!==formulas)throw new Error('Formulas changed');
const newMain=s.getRange('A10:M169').values,newRaw=raw.getRange('A9:N168').values;
for(let i=0;i<160;i++){
 if(!changed.has(i)&&(JSON.stringify(oldMain[i])!==JSON.stringify(newMain[i])||JSON.stringify(oldRaw[i])!==JSON.stringify(newRaw[i])))throw new Error('Unrelated row changed');
 if(changed.has(i))for(let j=0;j<14;j++)if(j!==1&&oldRaw[i][j]!==newRaw[i][j])throw new Error('Historical baseline/raw metadata changed');
}
for(const item of input.cases){const col={16:'P',24:'Q',32:'R',40:'S',64:'U'}[item.new.font_px];if(Math.abs(s.getRange(`${col}${item.new.delta_g+9}`).values[0][0]-item.new.accuracy)>1e-10)throw new Error('Comparison curve data not updated');}
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
await(await SpreadsheetFile.exportXlsx(wb)).save(input.output_workbook);
for(const [sheetName,range,name] of [['实验结果','A1:M12','main-header'],['实验结果','O1:U41','comparison'],['完整回复','A91:C91','reply-32px'],['完整回复','A135:C135','reply-40px']]){
 const blob=await wb.render({sheetName,range,scale:1.2,format:'png'});await fs.writeFile(path.join(W,`${name}.png`),new Uint8Array(await blob.arrayBuffer()));
}
console.log(`AUTHORIZED REPLACEMENT PASS: 4 rows changed;156 rows unchanged;all formulas unchanged;total ${expectedTotal}/16000`);
