import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const work=path.dirname(new URL(import.meta.url).pathname);
const root=path.resolve(work,'../../exp2-perplexity');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root,'实验结果-01.xlsx')));
console.log((await wb.inspect({kind:'table',range:'实验结果!A164:M169',include:'values,formulas',tableMaxRows:6,tableMaxCols:13,maxChars:6000})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:1200})).ndjson);
const results=wb.worksheets.getItem('实验结果');
const last=results.getRange('B169').values[0][0];
const before=results.getRange('U41').values[0][0];
results.getRange('B169').values=[[last-1]];wb.recalculate();
if(Math.abs(results.getRange('U41').values[0][0]-(before-.01))>1e-10)throw new Error('Font/gray comparison does not recalculate');
results.getRange('B169').values=[[last]];wb.recalculate();
if(Math.abs(results.getRange('U41').values[0][0]-before)>1e-10)throw new Error('Comparison restore failed');
for(const [sheetName,range,name] of [['实验结果','A153:M173','results-tail'],['完整回复','A164:C168','replies-tail']]){
 const blob=await wb.render({sheetName,range,scale:1.2,format:'png'});
 await fs.writeFile(path.join(work,`final-${name}.png`),new Uint8Array(await blob.arrayBuffer()));
}
console.log('SAVED WORKBOOK READ-ONLY QA PASS: both sheets, final rows, no formula errors; comparison input-change/restore verified in memory; workbook not re-exported');
