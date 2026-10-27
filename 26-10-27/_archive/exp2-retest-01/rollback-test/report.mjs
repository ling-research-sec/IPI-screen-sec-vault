import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {FileBlob,SpreadsheetFile,Workbook} from '@oai/artifact-tool';
const input=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const work=path.dirname(process.argv[2]);
const lastCol=input.has_conditions?'M':'I';
const canonical=v=>Number.isFinite(Number(v))?String(Number(v)):String(v);
const literal=v=>typeof v==='string'&&v.startsWith('=')?"'"+v:v;
const sameLiteral=(actual,expected)=>actual===expected||(typeof expected==='string'&&expected.startsWith('=')&&actual==="'"+expected);
const white='#FFFFFF',black='#000000',grey='#EFEFEF',border='#C8C8C8';
const font={name:'Arial',size:11,color:black};
function styleBody(s,range){s.getRange(range).format={fill:white,font:{...font,bold:false},rowHeight:28,verticalAlignment:'center',borders:{preset:'all',style:'thin',color:border}};}
function styleHeader(s,range){s.getRange(range).format={fill:grey,font:{...font,bold:true},rowHeight:30,horizontalAlignment:'center',verticalAlignment:'center',borders:{preset:'all',style:'thin',color:border}};}
await fs.mkdir(input.output_dir,{recursive:true});
for(const rd of input.rounds){
 const nn=String(rd.round).padStart(2,'0'),ev=`evidence-${nn}`;
 let wb,s,raw,ordered=[],oldN=rd.existing_rows,oldBody,oldReplies;
 const rowsByValue=new Map(rd.rows.map(r=>[canonical(r.value),r]));
 if(rd.template){
  wb=await SpreadsheetFile.importXlsx(await FileBlob.load(rd.template));
  s=wb.worksheets.getItem('实验结果');raw=wb.worksheets.getItem('完整回复');
  if(s.getRange('H9').values[0][0]!=='亮度条件')throw new Error('Unsupported column schema; adapt without overwriting it');
  if(!sameLiteral(String(raw.getRange('B5').values[0][0]).replace(/[\r\n]+$/,''),input.reference.replace(/[\r\n]+$/,'')))throw new Error('Reference differs from the existing workbook');
  const body=s.getRange(`A10:${lastCol}${oldN+9}`).values;
  oldBody=JSON.stringify(body);oldReplies=JSON.stringify(raw.getRange(`A9:C${oldN+8}`).values);
  for(let i=0;i<body.length;i++){
   const key=canonical(body[i][0]),r=rowsByValue.get(key);
   if(!r)throw new Error('Existing report case missing from evidence');
   const fields=[[1,'correct'],[3,'substitutions'],[4,'deletions'],[5,'insertions'],[6,'unk_tokens']];
   for(const [col,field] of fields)if(body[i][col]!==r[field])throw new Error('Existing score differs; review rather than silently rescore old results');
   if(!sameLiteral(raw.getRange(`B${i+9}`).values[0][0],r.response))throw new Error('Existing raw reply differs');
   ordered.push(r);rowsByValue.delete(key);
  }
 }else{
  wb=Workbook.create();s=wb.worksheets.add('实验结果');raw=wb.worksheets.add('完整回复');
  for(const sh of [s,raw]){sh.showGridLines=false;sh.getRange(sh===s?`A1:${lastCol}9`:'A1:C8').format.font=font;}
  const widths=[16,14,13,9,9,9,12,20,22,...(input.has_conditions?[12,12,10,12]:[])];
  widths.forEach((x,i)=>s.getRange(`${String.fromCharCode(65+i)}1:${String.fromCharCode(65+i)}9`).format.columnWidth=x);
  for(const [c,x] of [['A',12],['B',100],['C',36]])raw.getRange(`${c}1:${c}8`).format.columnWidth=x;
  s.getRange('A4:I4').values=[['平均正确率',null,input.has_conditions?'跨条件SD':'跨档SD (pp)',null,'图片数',null,'满分试次',null,null]];
  s.getRange('B4').setNumberFormat('0.00%');s.getRange('D4').setNumberFormat('0.00');
  s.getRange('A9:I9').values=[[input.parameter_label,`正确数 /${input.reference_total}`,'正确率','错字','漏字','多字','未知符数','亮度条件','结果及注意事项']];
  if(input.has_conditions)s.getRange('J9:M9').values=[['字号(px)','灰度差Δg','轮次','CER']];
  raw.getRange('A8:C8').values=[[input.parameter_label,'助手完整回复','对应截图文件名']];
  raw.getRange('A5').values=[['参考字符']];raw.getRange('B5').values=[[literal(input.reference)]];
  raw.getRange('B5').format={font,wrapText:true,verticalAlignment:'top',rowHeight:Math.max(105,input.reference.split('\n').length*16+10)};
  s.freezePanes.freezeRows(9);raw.freezePanes.freezeRows(8);
 }
 ordered.push(...rowsByValue.values());
 const count=ordered.length,end=count+9,totalRow=count+11,oldEnd=oldN+9;
 if(oldN)s.getRange(`A${oldEnd+1}:${lastCol}${Math.max(totalRow+3,oldN+14)}`).clear({applyTo:'all'});
 const additions=ordered.slice(oldN);
 const values=additions.map(r=>[r.value,r.correct,null,r.substitutions,r.deletions,r.insertions,r.unk_tokens,r.brightness_label,r.exact_transcription?'完整转写':r.unreadable?'不可读':'部分转写',...(input.has_conditions?[r.font_px,r.delta_g,r.round,null]:[])]);
 if(additions.length){
  if(oldN)s.tables.items[0].rows.add(null,values);else s.getRange(`A10:${lastCol}${end}`).values=values;
  styleBody(s,`A${oldN+10}:${lastCol}${end}`);s.getRange(`A${oldN+10}:G${end}`).format.horizontalAlignment='right';
  s.getRange(`H${oldN+10}:I${end}`).format.horizontalAlignment='left';
  s.getRange(`C${oldN+10}:C${end}`).formulas=additions.map((r,i)=>[`=B${oldN+10+i}/${input.reference_total}`]);
  s.getRange(`C${oldN+10}:C${end}`).setNumberFormat('0.0%');
  if(input.has_conditions){s.getRange(`M${oldN+10}:M${end}`).formulas=additions.map((r,i)=>[`=(D${oldN+10+i}+E${oldN+10+i}+F${oldN+10+i})/${input.reference_total}`]);s.getRange(`M${oldN+10}:M${end}`).setNumberFormat('0.0%');}
  raw.getRange(`A${oldN+9}:C${count+8}`).values=additions.map(r=>[r.value,literal(r.response),r.screenshot]);
  raw.getRange(`A${oldN+9}:C${count+8}`).format={fill:white,font,verticalAlignment:'top',borders:{preset:'all',style:'thin',color:border}};
  raw.getRange(`B${oldN+9}:B${count+8}`).format.wrapText=true;
  for(let i=0;i<additions.length;i++){
   const r=additions[i],lines=r.response.split('\n').reduce((n,x)=>n+Math.max(1,Math.ceil(x.length/90)),0);
   raw.getRange(`A${oldN+9+i}:C${oldN+9+i}`).format.rowHeight=r.unreadable?38:Math.max(115,lines*16+12);
  }
 }
 if(!oldN){const table=s.tables.add(`A9:${lastCol}${end}`,true,'ReadabilityResults');table.style='TableStyleLight1';table.showFilterButton=true;styleHeader(s,`A9:${lastCol}9`);styleHeader(raw,'A8:C8');}
 s.getRange('A2').values=[[literal(`${input.title}（第${nn}轮）`)]];raw.getRange('A2').values=[[`完整回复与参考字符（第${nn}轮）`]];
 for(const sh of [s,raw])sh.getRange('A2').format={font:{...font,size:14,bold:true},rowHeight:30};
 s.getRange('A5').values=[[`${input.date}　每档1次　每图${input.reference_total}个目标字符　${input.context}`]];
 s.getRange('A6').values=[[input.has_conditions?'标准差仅描述跨字号×灰度条件差异，不代表重复测量误差。':'标准差描述跨参数档位差异，不代表同档重复试验误差。']];
 s.getRange('A7').values=[[literal(input.condition_note)]];s.getRange('A5:I7').format.font=font;
 if(!rd.template){
  for(const row of [2,5,6,7])s.getRange(`A${row}:${lastCol}${row}`).merge();
  for(const row of [2,3,7])raw.getRange(`A${row}:C${row}`).merge();
 }
 s.getRange('A5:I7').format.rowHeight=24;
 s.getRange('B4').formulas=[[`=AVERAGE(C10:C${end})`]];
 s.getRange('D4').formulas=[[count>1?`=STDEV(C10:C${end})*100`:'="n.a."']];
 s.getRange('F4').formulas=[[`=COUNTA(A10:A${end})`]];
 s.getRange('H4').formulas=[[`=COUNTIFS(B10:B${end},${input.reference_total},F10:F${end},0)`]];
 s.getRange(`A${totalRow}:I${totalRow}`).values=[['合计',null,null,null,null,null,null,null,`${rd.total_characters}个目标字符`]];
 for(const col of ['B','D','E','F','G'])s.getRange(col+totalRow).formulas=[[`=SUM(${col}10:${col}${end})`]];
 s.getRange('C'+totalRow).formulas=[[`=B${totalRow}/${rd.total_characters}`]];s.getRange('C'+totalRow).setNumberFormat('0.00%');
 s.getRange(`A${totalRow}:I${totalRow}`).format={fill:white,font:{...font,bold:true},rowHeight:30,borders:{preset:'all',style:'thin',color:border}};
 s.getRange('A'+(totalRow+2)).values=[['错字=替换；漏字=删除；多字=插入。[UNK]视为1个未知字符，[UNREADABLE]视为空转写。']];
 s.getRange('A'+(totalRow+3)).values=[[`原始回复、截图与记录分别保存在 ${ev}，不同轮次不互相覆盖。`]];
 s.getRange(`A${totalRow+2}:I${totalRow+3}`).format.font=font;
 s.getRange(`A${totalRow+2}:I${totalRow+3}`).format.rowHeight=24;
 raw.getRange('A3').values=[[`来源：${ev}/records、responses；参考文字见本页。`]];
 raw.getRange('A7').values=[['原文及换行保留，不补全、不纠错；亮度条件以逐轮原记录和已确认说明为准。']];
 if(input.has_conditions){
  const baseline=JSON.parse(await fs.readFile(path.join(input.root,'evidence-01','records','baseline48-reference.json'),'utf8'));
  if(baseline.rows.length!==96)throw new Error('48px baseline is not 3x32');
  raw.getRange('E2').values=[['48px历史数据（只读引用实验一三轮）']];
  raw.getRange('E3').values=[['g1沿用历史旧位置；新字号均使用固定锚点(86,672)。']];
  if(!rd.template){raw.getRange('E2:N2').merge();raw.getRange('E3:N3').merge();}
  raw.getRange('E8:N8').values=[['历史轮次','Δg','字号px','正确数','正确率','替换','删除','插入','CER','历史记录路径']];
  raw.getRange('E9:N104').values=baseline.rows.map(r=>[r.round,r.delta_g,48,r.correct,r.accuracy,r.substitutions,r.deletions,r.insertions,r.cer,r.record_path]);
  styleHeader(raw,'E8:N8');styleBody(raw,'E9:N104');
  raw.getRange('I9:I104').setNumberFormat('0.0%');raw.getRange('M9:M104').setNumberFormat('0.0%');
  for(const col of ['E','F','G','H','I','J','K','L','M'])raw.getRange(`${col}1:${col}104`).format.columnWidth=12;
  raw.getRange('N1:N104').format.columnWidth=85;
  s.getRange('O2').values=[['字号×灰度差比较']];
  s.getRange('O3').values=[['48px为历史3轮均值；其他字号为本轮单次结果。']];
  s.getRange('O4').values=[['新字号无重复测量SD；待测不按0分处理。g1位置存在历史差异。']];
  if(!rd.template)for(const row of [2,3,4])s.getRange(`O${row}:U${row}`).merge();
  s.getRange('O9:U9').values=[['Δg','16px (n=1)','24px (n=1)','32px (n=1)','40px (n=1)','48px (n=3)','64px (n=1)']];
  s.getRange('O10:O41').values=Array.from({length:32},(_,i)=>[i+1]);
  for(const [col,f] of [['P',16],['Q',24],['R',32],['S',40],['U',64]]){
   s.getRange(`${col}10:${col}41`).formulas=Array.from({length:32},(_,i)=>[`=IF(COUNTIFS($J$10:$J$${end},${f},$K$10:$K$${end},$O${i+10})=0,"待测",AVERAGEIFS($C$10:$C$${end},$J$10:$J$${end},${f},$K$10:$K$${end},$O${i+10}))`]);
  }
  s.getRange('T10:T41').formulas=Array.from({length:32},(_,i)=>[`=AVERAGEIFS('完整回复'!$I$9:$I$104,'完整回复'!$F$9:$F$104,$O${i+10})`]);
  styleHeader(s,'O9:U9');styleBody(s,'O10:U41');s.getRange('O1:U41').format.columnWidth=17;s.getRange('P10:U41').setNumberFormat('0.0%');
 }
 wb.recalculate();
 if(oldN&&(JSON.stringify(s.getRange(`A10:${lastCol}${oldN+9}`).values)!==oldBody||JSON.stringify(raw.getRange(`A9:C${oldN+8}`).values)!==oldReplies))throw new Error('Prior report rows changed');
 if(s.getRange('B'+totalRow).values[0][0]!==rd.total_correct||Math.abs(s.getRange('B4').values[0][0]-rd.mean_accuracy)>1e-10)throw new Error('Summary mismatch');
 if(count>1&&Math.abs(s.getRange('D4').values[0][0]-rd.sample_sd*100)>1e-8)throw new Error('SD mismatch');
 const last=s.getRange('B'+end).values[0][0],delta=last===input.reference_total?-1:1;
 s.getRange('B'+end).values=[[last+delta]];wb.recalculate();
 if(Math.abs(s.getRange('B4').values[0][0]-rd.mean_accuracy-delta/rd.total_characters)>1e-10)throw new Error('Recalculation failure');
 s.getRange('B'+end).values=[[last]];wb.recalculate();
 console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
 const target=path.join(input.output_dir,`实验结果-${nn}.xlsx`);
 await(await SpreadsheetFile.exportXlsx(wb)).save(target);
 const ledgerPath=path.join(work,'report-output-hashes.json');
 let ledger={};try{ledger=JSON.parse(await fs.readFile(ledgerPath,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
 ledger[target]=createHash('sha256').update(await fs.readFile(target)).digest('hex');
 await fs.writeFile(ledgerPath+'.tmp',JSON.stringify(ledger,null,2)+'\n');await fs.rename(ledgerPath+'.tmp',ledgerPath);
 for(const [sheetName,range,name] of [['实验结果',`A1:${lastCol}${Math.min(end,25)}`,'results'],['完整回复',`A1:C${Math.min(count+8,16)}`,'replies']]){
  const png=await wb.render({sheetName,range,scale:1.2,format:'png'});
  await fs.writeFile(path.join(work,`round${nn}-${name}.png`),new Uint8Array(await png.arrayBuffer()));
 }
 if(input.has_conditions){
  for(const [sheetName,range,name] of [['实验结果','O1:U41','comparison'],['完整回复','E1:N18','baseline']]){
   const png=await wb.render({sheetName,range,scale:1.2,format:'png'});
   await fs.writeFile(path.join(work,`round${nn}-${name}.png`),new Uint8Array(await png.arrayBuffer()));
  }
 }
 console.log(`REPORT PASS: round${nn}, ${count} rows, ${rd.total_correct}/${rd.total_characters}`);
}
