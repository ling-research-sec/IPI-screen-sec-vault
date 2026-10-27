import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const w=path.dirname(new URL(import.meta.url).pathname);
const file=path.resolve(process.argv[2]);
if(!/实验结果-0[23]\.xlsx$/.test(file))throw new Error('Only newly created round02/03 workbooks are allowed');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(file));
const s=wb.worksheets.getItem('实验结果'),r=wb.worksheets.getItem('完整回复');
const before=JSON.stringify([s.getRange('B10:M169').values,r.getRange('B9:N168').values]);
let count=0;
for(const [sheet,range] of [[s,'A10:A169'],[r,'A9:A168']]){
 const values=sheet.getRange(range).values.map(([id])=>{if(/^px\d+-g\d+$/.test(id))return [id];if(!/^f\d+-g\d+$/.test(id))throw new Error('Unexpected ID: '+id);count++;return [id.replace(/^f/,'px')];});
 sheet.getRange(range).values=values;
}
// Baseline styling must not clip the newly collected full replies on shared worksheet rows.
for(const [i,[reply]] of r.getRange('B9:B168').values.entries()){
 const lines=String(reply).split('\n').reduce((n,x)=>n+Math.max(1,Math.ceil(x.length/90)),0);
 r.getRange(`A${i+9}:C${i+9}`).format.rowHeight=String(reply).trim()==='[UNREADABLE]'?38:Math.max(115,lines*16+12);
}
// Equal 100-character denominators: reuse the exact total rate and avoid binary-average display ties.
s.getRange('B4').formulas=[['=C171']];
wb.recalculate();
if(JSON.stringify([s.getRange('B10:M169').values,r.getRange('B9:N168').values])!==before)throw new Error('Other result data changed');
await(await SpreadsheetFile.exportXlsx(wb)).save(file);
const side=file+'.inspect.ndjson';try{await fs.rename(side,path.join(w,path.basename(file)+'.display-inspect.ndjson'));}catch(e){if(e.code!=='ENOENT')throw e;}
console.log(`UPDATED ${count} display IDs across two sheets; scores/replies unchanged`);

for(const [sheetName,range,name] of [['实验结果','A1:M18','results'],['完整回复','A1:C16','replies']]){const png=await wb.render({sheetName,range,scale:1.2,format:'png'});await fs.writeFile(path.join(w,path.basename(file)+'.'+name+'.png'),new Uint8Array(await png.arrayBuffer()));}
