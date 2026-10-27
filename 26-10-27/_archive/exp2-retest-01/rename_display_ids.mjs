import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const w=path.dirname(new URL(import.meta.url).pathname);
const file=path.resolve(w,'../../exp2-perplexity/实验结果-01.xlsx');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(file));
const s=wb.worksheets.getItem('实验结果'),r=wb.worksheets.getItem('完整回复');
const before=JSON.stringify([s.getRange('B10:M169').values,r.getRange('B9:N168').values]);
let count=0;
for(const [sheet,range] of [[s,'A10:A169'],[r,'A9:A168']]){
 const values=sheet.getRange(range).values.map(([id])=>{if(!/^f\d+-g\d+$/.test(id))throw new Error('Unexpected ID: '+id);count++;return [id.replace(/^f/,'px')];});
 sheet.getRange(range).values=values;
}
wb.recalculate();
if(JSON.stringify([s.getRange('B10:M169').values,r.getRange('B9:N168').values])!==before)throw new Error('Other result data changed');
await(await SpreadsheetFile.exportXlsx(wb)).save(file);
const side=file+'.inspect.ndjson';try{await fs.rename(side,path.join(w,'rename-ids-inspect.ndjson'));}catch(e){if(e.code!=='ENOENT')throw e;}
console.log(`UPDATED ${count} display IDs across two sheets; scores/replies unchanged`);
