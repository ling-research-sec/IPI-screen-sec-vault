import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const w=path.dirname(new URL(import.meta.url).pathname);
const target=path.resolve(w,'../../exp2-perplexity/实验结果-01.xlsx');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(target));
const s=wb.worksheets.getItem('实验结果'),raw=wb.worksheets.getItem('完整回复');
const original=JSON.stringify([s.getRange('A10:M169').values,raw.getRange('A9:N168').values]);
const texts=[
 '复测后结论（2026-10-27）',
 '4条显示例外已按重测结果替换：16px/g1=0、24px/g16=0、32px/g19=69、40px/g31=95（均为正确数/100）。',
 '正式数据仍为160条，其余156条不变；当前160条源屏文字区与原PNG逐像素一致。',
 '总正确数为5724/16000（35.775%），较复测前仅下降0.0375个百分点；本轮整体观察未改变，单次差异不作因果归因。'
];
for(let i=0;i<texts.length;i++){
 const row=176+i;const r=s.getRange(`A${row}:M${row}`);r.merge();s.getRange(`A${row}`).values=[[texts[i]]];
 r.format={font:{name:'Arial',size:i===0?12:11,bold:i===0,color:'#000000'},fill:'#FFFFFF',rowHeight:i===0?28:32,wrapText:true,verticalAlignment:'center'};
}
wb.recalculate();
if(JSON.stringify([s.getRange('A10:M169').values,raw.getRange('A9:N168').values])!==original)throw new Error('Result data changed while adding conclusion');
await(await SpreadsheetFile.exportXlsx(wb)).save(target);
const preview=await wb.render({sheetName:'实验结果',range:'A176:M179',scale:1.2,format:'png'});
await fs.writeFile(path.join(w,'conclusion.png'),new Uint8Array(await preview.arrayBuffer()));
console.log('SAVED: conclusion written into official XLSX;160 result rows and all raw replies unchanged');
