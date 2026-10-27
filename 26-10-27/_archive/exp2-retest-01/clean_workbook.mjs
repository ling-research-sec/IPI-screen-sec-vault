import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const w=path.dirname(new URL(import.meta.url).pathname),target=path.resolve(w,'../../exp2-perplexity/实验结果-01.xlsx');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(target));
const s=wb.worksheets.getItem('实验结果'),raw=wb.worksheets.getItem('完整回复');
const before=JSON.stringify([s.getRange('A10:M169').values,raw.getRange('A9:N168').values,s.getRange('A171:M174').values]);
s.getRange('A175:M185').clear({applyTo:'all'});
s.getRange('A7').values=[['黑底；固定手动最大亮度255；每个字号×灰度条件保留1条正式结果。']];
wb.recalculate();
if(JSON.stringify([s.getRange('A10:M169').values,raw.getRange('A9:N168').values,s.getRange('A171:M174').values])!==before)throw new Error('Data or statistics changed');
await(await SpreadsheetFile.exportXlsx(wb)).save(target);
const side=target+'.inspect.ndjson';try{await fs.rename(side,path.join(w,'clean-workbook-inspect.ndjson'));}catch(e){if(e.code!=='ENOENT')throw e;}
console.log('SAVED: retest conclusion removed;160 data rows,full replies and original bottom statistics unchanged');
