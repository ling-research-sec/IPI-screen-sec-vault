import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const w=path.dirname(new URL(import.meta.url).pathname);
const config=JSON.parse(await fs.readFile(path.join(w,'config-full.json'),'utf8'));
for(const n of [2,3]){
 const nn=String(n).padStart(2,'0'),file=path.join(config.experiment_dir,`实验结果-${nn}.xlsx`);
 const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(file));
 const main=wb.worksheets.getItem('实验结果'),raw=wb.worksheets.getItem('完整回复');
 if(main.getRange('F4').values[0][0]!==160)throw new Error('Wrong count');
 if(main.tables.items.length!==1||!main.tables.items[0].showFilterButton)throw new Error('Missing filter table');
 console.log(JSON.stringify({round:n,summary:main.getRange('A4:I4').values,totals:main.getRange('A171:M171').values,last_condition:main.getRange('A169:M169').values,last_reply:raw.getRange('A168:C168').values}));
 console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:25},maxChars:1800})).ndjson);
 for(const [sheetName,range,label] of [['实验结果','A160:M174','totals'],['完整回复','A164:C168','replies-tail']]){
  const png=await wb.render({sheetName,range,scale:1.2,format:'png'});
  await fs.writeFile(path.join(w,`round${nn}-final-${label}.png`),new Uint8Array(await png.arrayBuffer()));
 }
}
