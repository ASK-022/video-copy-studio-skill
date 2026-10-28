'use strict';
const narrationEl=id=>document.getElementById(id);
let narrationStorage=null;try{narrationStorage=window.localStorage;}catch(_){}
const narrationDrafts=new NarrationDrafts(narrationStorage);
let narrationExportBusy=false,narrationStorageWarned=false;
const narrationModes={same:'同商品裂变',switch:'换商品套结构',original:'原创脚本'};
function activeNarrations(){
  if(!current)return null;
  const batch=narrationDrafts.batch(current);
  return batch?{job:current,batch,rows:narrationDrafts.rows(current,batch)}:null;
}
function saveNarrations(data){
  if((!narrationDrafts.save(data.job,data.batch,data.rows)||!narrationStorage)&&!narrationStorageWarned){
    narrationStorageWarned=true;toast('本机浏览器存储不可用，修改仅在本次打开期间保留，请及时导出。');
  }
  if(typeof queueNarrationSaves==='function')queueNarrationSaves(data);
}
function updateNarrationActions(data=activeNarrations()){
  if(!data)return;
  const selected=data.rows.filter(r=>r.selected),invalid=selected.some(r=>!r.text.trim()||r.text.length>20000);
  narrationEl('narration-selection').textContent=`已选 ${selected.length} / ${data.rows.length} 条`;
  narrationEl('narration-all').checked=!!data.rows.length&&selected.length===data.rows.length;
  narrationEl('narration-all').indeterminate=selected.length>0&&selected.length<data.rows.length;
  for(const id of ['narration-copy','narration-txt','narration-zip','narration-table'])narrationEl(id).disabled=narrationExportBusy||!selected.length||invalid;
  const allCollapsed=data.rows.length&&data.rows.every(r=>r.collapsed);
  narrationEl('narration-collapse-all').textContent=allCollapsed?'全部展开':'全部折叠';
  narrationEl('narration-collapse-all').setAttribute('aria-expanded',String(!allCollapsed));
  narrationEl('narration-collapse-all').hidden=narrationDrafts.projects.get(data.job.id)?.view==='structure';
  narrationEl('narration-selection').textContent+=invalid?' · 请补全文案（单条最多 2 万字）':'';
}
function renderResults(job){
  narrationEl('drafts-export').href='/api/jobs/'+job.id+'/drafts/export';
  narrationEl('results-section').hidden=!job.batches.length;
  const batch=narrationDrafts.batch(job);if(!batch)return;
  const state=narrationDrafts.projects.get(job.id),rows=narrationDrafts.rows(job,batch),data={job,batch,rows};
  narrationEl('narration-batch').replaceChildren();
  for(const b of [...job.batches].reverse()){
    const option=document.createElement('option');option.value=b.id;
    option.textContent=`${b.id===job.batches.at(-1).id?'最新 · ':''}${narrationModes[b.mode]||'脚本'} · ${new Date(b.created*1000).toLocaleString('zh-CN')} · ${b.variants.length} 条${b.complete?'':'（未全部完成）'}`;
    narrationEl('narration-batch').append(option);
  }
  narrationEl('narration-batch').value=batch.id;
  narrationEl('results-count').textContent=`${batch.variants.length}${batch.requested_count?' / '+batch.requested_count:''} 条${batch.complete?'':' · 已生成部分可复制、导出'}`;
  narrationEl('narration-summary').hidden=state.view==='structure';narrationEl('results').hidden=state.view!=='structure';
  for(const b of document.querySelectorAll('[data-result-view]'))b.setAttribute('aria-selected',String(b.dataset.resultView===state.view));
  narrationEl('narration-summary').replaceChildren();
  rows.forEach((row,i)=>{
    const variant=batch.variants[i],card=document.createElement('article');card.className='narration-card';
    const heading=document.createElement('div');heading.className='narration-card-heading';
    const select=document.createElement('input');select.type='checkbox';select.checked=row.selected;select.setAttribute('aria-label',`选择第 ${i+1} 条文案`);
    const title=document.createElement('h3');title.textContent=`${String(i+1).padStart(2,'0')} · ${variant.title||'文案'}`;
    const copy=document.createElement('button');copy.className='quiet';copy.textContent='复制口播';copy.setAttribute('aria-label',`复制第 ${i+1} 条口播`);
    const edit=document.createElement('button');edit.className='text-link';edit.textContent='修改';edit.setAttribute('aria-expanded','false');edit.setAttribute('aria-label',`修改第 ${i+1} 条文案`);
    const fold=document.createElement('button');fold.className='quiet narration-fold';fold.setAttribute('aria-label',`折叠或展开第 ${i+1} 条文案`);
    heading.append(select,title,copy,edit,fold);card.append(heading);
    const content=document.createElement('div');content.id=`narration-content-${i}`;content.className='narration-content';card.append(content);fold.setAttribute('aria-controls',content.id);
    const text=document.createElement('p');text.className='narration-body';text.textContent=row.text;content.append(text);
    const editor=document.createElement('textarea');editor.className='narration-editor';editor.rows=9;editor.maxLength=20000;editor.hidden=true;editor.value=row.text;editor.setAttribute('aria-label',`第 ${i+1} 条口播正文`);content.append(editor);
    const footer=document.createElement('div');footer.className='narration-card-footer';
    const count=document.createElement('span'),reset=document.createElement('button');reset.className='quiet';reset.textContent='恢复生成原稿';reset.setAttribute('aria-label',`恢复第 ${i+1} 条生成原稿`);
    footer.append(count,reset);card.append(footer);
    const refresh=()=>{const changed=row.text!==row.source;count.textContent=`${row.text.replace(/\s/g,'').length} 字${changed?' · 已修改（用于复制和导出）':''}`;reset.hidden=!changed;copy.disabled=!row.text.trim();content.hidden=row.collapsed;fold.textContent=row.collapsed?'展开':'折叠';fold.setAttribute('aria-expanded',String(!row.collapsed));card.classList.toggle('collapsed',row.collapsed);};refresh();
    select.onchange=()=>{row.selected=select.checked;saveNarrations(data);updateNarrationActions(data);};
    copy.onclick=async()=>{try{if(typeof flushNarrations==='function')await flushNarrations(data);await copyText(row.text.trim());}catch(e){toast(e.message);}};
    edit.onclick=()=>{const editing=editor.hidden;row.collapsed=false;refresh();saveNarrations(data);updateNarrationActions(data);editor.hidden=!editing;text.hidden=editing;edit.textContent=editing?'完成':'修改';edit.setAttribute('aria-expanded',String(editing));if(editing)editor.focus();};
    fold.onclick=()=>{row.collapsed=!row.collapsed;refresh();saveNarrations(data);updateNarrationActions(data);};
    editor.oninput=()=>{row.text=editor.value;row.segments=null;text.textContent=row.text;refresh();saveNarrations(data);updateNarrationActions(data);};
    reset.onclick=()=>{row.text=row.source;row.segments=structuredClone(variant.segments);editor.value=row.text;text.textContent=row.text;refresh();saveNarrations(data);updateNarrationActions(data);};
    if(typeof enhanceNarrationCard==='function')enhanceNarrationCard({data,row,index:i,variant,card,heading,content,editor,text,refresh,view:state.view});
    if(variant.quality?.needs_revision||variant.quality_error||variant.revision_error){const note=document.createElement('p');note.className='hint narration-review-note';note.textContent='此稿仍有待改进项，可到「分段结构」查看质检详情。';content.append(note);}
    narrationEl('narration-summary').append(card);
  });
  if(!rows.length)narrationEl('narration-summary').textContent='文案生成后会逐条显示在这里。';
  renderStructuredResults(job,batch);updateNarrationActions(data);
  if(typeof queueNarrationSaves==='function')queueNarrationSaves(data);
}
for(const button of document.querySelectorAll('[data-result-view]'))button.onclick=()=>{
  if(!current)return;narrationDrafts.batch(current);narrationDrafts.projects.get(current.id).view=button.dataset.resultView;renderResults(current);
};
narrationEl('narration-batch').onchange=()=>{if(current){narrationDrafts.projects.get(current.id).batch=narrationEl('narration-batch').value;renderResults(current);}};
narrationEl('narration-all').onchange=()=>{const data=activeNarrations();if(!data)return;data.rows.forEach(r=>r.selected=narrationEl('narration-all').checked);saveNarrations(data);renderResults(current);};
narrationEl('narration-collapse-all').onclick=()=>{const data=activeNarrations();if(!data)return;const collapsed=!data.rows.every(r=>r.collapsed);data.rows.forEach(r=>r.collapsed=collapsed);saveNarrations(data);renderResults(current);};
narrationEl('narration-copy').onclick=async()=>{const data=activeNarrations();if(!data)return;try{if(typeof flushNarrations==='function')await flushNarrations(data);await copyText(data.rows.flatMap((r,i)=>r.selected?[`【${String(i+1).padStart(2,'0')} · ${data.batch.variants[i].title||'文案'}】\n\n${r.text.trim()}`]:[]).join('\n\n\n'));}catch(e){toast(e.message);}};
async function exportNarrations(format,snapshot=null){
  const data=snapshot||activeNarrations();if(!data||narrationExportBusy)return;
  if(!data.items&&typeof flushNarrations==='function'){try{await flushNarrations(data);}catch(e){toast(e.message);return;}}
  const items=data.items||data.rows.flatMap((r,index)=>r.selected?[{index,text:r.text,revision:r.revision}]:[]);if(!items.length)return;
  narrationExportBusy=true;updateNarrationActions();
  try{
    const options={method:'POST',headers:{'Content-Type':'application/json','X-Studio-Request':'1'},body:JSON.stringify({batch_id:data.batch.id,format,items,...(data.template?{template:data.template,table_options:data.table_options}:{})})};
    const path=`/api/jobs/${data.job.id}/drafts/text-export`;
    let response=await fetch(path,options);
    if(response.status===403){const error=await response.clone().json().catch(()=>({}));if(error.detail==='请重新打开客户端。'){await fetch('/');response=await fetch(path,options);}}
    if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(typeof error.detail==='string'?error.detail:'导出失败，请检查文案后重试。');}
    const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
    link.href=url;link.download=`${data.job.title.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,70)}_${narrationModes[data.batch.mode]||'文案'}_${format==='zip'?'逐条口播':format==='xlsx'?({script:'脚本文案表',shooting:'拍摄需求表',archive:'详细归档'}[data.template]||'文案汇总'):'文案汇总'}.${format}`;
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
    toast(format==='xlsx'&&data.template==='shooting'?`已汇总 ${items.length} 条脚本，导出 1 条拍摄需求。`:`已导出 ${items.length} 条${format==='zip'?'，每个 TXT 仅含口播正文。':format==='xlsx'?'到 Excel 表格。':'汇总文案。'}`);
  }catch(e){toast(e.message);}finally{narrationExportBusy=false;updateNarrationActions();}
}
narrationEl('narration-txt').onclick=()=>exportNarrations('txt');narrationEl('narration-zip').onclick=()=>exportNarrations('zip');
