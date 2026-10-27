import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
let input='';for await(const chunk of process.stdin)input+=chunk;
const payload=JSON.parse(input),layout=payload.template||'archive',wb=Workbook.create();
const names={archive:'详细归档',script:'脚本文案表',shooting:'拍摄需求表'};
const sheet=wb.worksheets.add(names[layout]);
sheet.showGridLines=false;
const literal=v=>typeof v==='string'&&v.startsWith('=')?"'"+v:v;
const values=[payload.headers,...payload.rows.map(row=>row.map((v,i)=>layout==='archive'&&i===6?new Date(v.replace(' ','T')):v))].map(row=>row.map(literal));
const end=values.length,last=String.fromCharCode(64+payload.headers.length),range=`A1:${last}${end}`;
sheet.getRange(range).values=values;
sheet.getRange(range).format.font={name:'Arial',size:10,color:'#1D1D1F'};
sheet.getRange(range).format.verticalAlignment=layout==='archive'?'top':'center';
sheet.getRange(range).format.wrapText=true;
sheet.getRange(range).format.horizontalAlignment='center';
sheet.getRange(range).format.borders={preset:'all',style:'thin',color:'#D0D0D0'};
sheet.getRange(`A1:${last}1`).format.font={name:'Arial',size:11,bold:true,color:layout==='archive'?'#FFFFFF':'#1D1D1F'};
sheet.getRange(`A1:${last}1`).format.fill=layout==='archive'?'#25364A':'#FFFFFF';
sheet.getRange(`A1:${last}1`).format.rowHeight=42;
const widths=layout==='script'?[24,115,36,20,28]:layout==='shooting'?[22,19,32,70,32,32,24,26]:[8,32,100,10,20,32,23,16];
for(let i=0;i<widths.length;i++)sheet.getRange(`${String.fromCharCode(65+i)}1:${String.fromCharCode(65+i)}${end}`).format.columnWidth=widths[i];
const bodyColumn=layout==='script'?'B':layout==='shooting'?'D':'C';
sheet.getRange(`${bodyColumn}2:${bodyColumn}${end}`).format.horizontalAlignment='left';
for(let i=0;i<payload.rows.length;i++){
 const row=i+2,text=String(payload.rows[i][layout==='script'?1:layout==='shooting'?3:2]||'');
 const lines=text.split('\n').reduce((n,line)=>n+Math.max(1,Math.ceil(line.length/(layout==='shooting'?35:55))),0);
 sheet.getRange(`A${row}:${last}${row}`).format.rowHeight=Math.min(409,Math.max(layout==='shooting'?160:130,lines*13+24));
}
if(layout==='archive')sheet.getRange(`G2:G${end}`).setNumberFormat('yyyy-mm-dd hh:mm:ss');
if(layout==='shooting')sheet.getRange(`B2:B${end}`).setNumberFormat('0');
const table=sheet.tables.add(range,true,'NarrationTable');table.style='TableStyleLight1';
if(layout!=='archive')sheet.getRange(range).format.fill='#FFFFFF';
sheet.freezePanes.freezeRows(1);
wb.recalculate();
await (await SpreadsheetFile.exportXlsx(wb)).save(process.argv[2]);
if(process.argv[3]){
 const image=await wb.render({sheetName:names[layout],range:`A1:${last}${Math.min(end,3)}`,scale:1.1});
 await fs.writeFile(process.argv[3],new Uint8Array(await image.arrayBuffer()));
}
