'use strict';
const adoptionLabels={review:'待审核',edit:'需修改',adopted:'已采用',shoot:'待拍摄',published:'已发布',discarded:'弃用'};
const editorialViews=new Map(),adoptionDrafts=new Map();let metadataVersion=0,intakeContext=null,intakeEpoch=0,taskPoll=null;
function workflowElement(tag,cls,text){const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;}
function statusOptions(select,blank=false){select.replaceChildren();if(blank)select.append(new Option('全部状态',''));for(const [value,label] of Object.entries(adoptionLabels))select.append(new Option(label,value));}
statusOptions($('editorial-filter'),true);statusOptions($('editorial-bulk-status'));
function editorialState(job,batch){const key=job.id+':'+batch.id;if(!editorialViews.has(key))editorialViews.set(key,{status:'',similarity:'',review:null,signature:''});return editorialViews.get(key);}
function editorialVisible(job,batch,index){
  const state=editorialState(job,batch);return WorkflowRules.visible(batch.editorial?.[index],state,state.review,index);
}
function prepareEditorialResults(data){
  const state=editorialState(data.job,data.batch),signature=JSON.stringify(data.rows.map(row=>[row.text,row.revision]));
  if(state.review&&state.signature!==signature){state.review=null;state.similarity='';$('editorial-message').textContent='成稿已修改，请重新分析相似度。';}
  $('editorial-filter').value=state.status;$('similarity-filter').value=state.similarity;
  const remaining=Math.max(0,(data.batch.requested_count||0)-data.batch.variants.length);$('resume-batch').hidden=!remaining;$('resume-batch').textContent=`补齐剩余 ${remaining} 条`;$('resume-batch').disabled=busy(data.job);
  $('similarity-summary').replaceChildren();
  if(state.review){const note=workflowElement('p','',state.review.method);$('similarity-summary').append(note);
    for(const pair of state.review.pairs.slice(0,30))$('similarity-summary').append(workflowElement('p','',`第 ${pair.a+1} / ${pair.b+1} 条：正文 ${pair.similarity}% · 开头 ${pair.opening_similarity}%（${pair.reason}）`));
    if(!state.review.pairs.length)$('similarity-summary').append(workflowElement('p','','所选文案未发现超过当前阈值的相似稿。'));
  }
  const count=data.rows.filter((_,i)=>editorialVisible(data.job,data.batch,i)).length;
  $('editorial-tools').dataset.visibleCount=count;
}
const previousEnhanceNarrationCard=enhanceNarrationCard;
enhanceNarrationCard=function(info){
  previousEnhanceNarrationCard(info);const {data,index,card,content}=info,entry=data.batch.editorial?.[index]||{status:'review',version:0,note:''},key=data.job.id+':'+data.batch.id+':'+index,draft=adoptionDrafts.get(key)||entry;
  const bar=workflowElement('div','adoption-row'),select=workflowElement('select');select.setAttribute('aria-label',`第 ${index+1} 条采用状态`);statusOptions(select);select.value=draft.status;
  const note=workflowElement('input');note.placeholder='审核意见（选填）';note.maxLength=1000;note.value=draft.note||'';note.setAttribute('aria-label',`第 ${index+1} 条审核意见`);
  select.onchange=note.oninput=()=>adoptionDrafts.set(key,{status:select.value,note:note.value,version:draft.version||0});
  const save=workflowElement('button','quiet','保存状态');bar.append(select,note,save);card.append(bar);
  if(draft.version!==entry.version){const reload=workflowElement('button','quiet','读取最新状态');reload.onclick=()=>{adoptionDrafts.delete(key);renderResults(current);};bar.append(reload);}
  save.onclick=async()=>{save.disabled=select.disabled=note.disabled=true;try{await saveAdoption(data,[{index,status:select.value,note:note.value,base_version:draft.version||0}]);toast('采用状态和审核意见已保存。');}catch(e){toast(e.message);if(e.message.includes('其他窗口')){const fresh=await api('/jobs/'+data.job.id);if(currentId===data.job.id)render(fresh);}}finally{save.disabled=select.disabled=note.disabled=false;}};
  const state=editorialState(data.job,data.batch),related=state.review?.pairs.filter(p=>p.a===index||p.b===index)||[];
  if(related.length)content.prepend(workflowElement('p','similarity-badge',`相似提示：${related.map(p=>'第 '+((p.a===index?p.b:p.a)+1)+' 条').join('、')}；请比较后决定。`));
  const checked=state.review?.items.find(item=>item.index===index);if(checked)content.append(workflowElement('p','hint',`与参考正文文本相似度 ${checked.reference_similarity}% · ${checked.changed?'表达有变化':'正文与参考相同'} · 方向：${info.variant.generation_focus||'未指定'}`));
};
async function saveAdoption(data,items){
  const saved=await api(`/jobs/${data.job.id}/drafts/${data.batch.id}/editorial`,{method:'PUT',body:JSON.stringify({items})});data.batch.editorial=saved;for(const item of items)adoptionDrafts.delete(data.job.id+':'+data.batch.id+':'+item.index);
  const live=current?.id===data.job.id?current.batches.find(b=>b.id===data.batch.id):null;if(live){live.editorial=saved;renderResults(current);}return saved;
}
$('editorial-filter').onchange=()=>{const data=activeNarrations();if(!data)return;editorialState(data.job,data.batch).status=$('editorial-filter').value;renderResults(current);};
$('similarity-filter').onchange=()=>{const data=activeNarrations();if(!data)return;const state=editorialState(data.job,data.batch);if($('similarity-filter').value&&!state.review){$('similarity-filter').value='';toast('请先勾选文案并分析文本相似度。');return;}state.similarity=$('similarity-filter').value;renderResults(current);};
$('select-visible').onclick=()=>{const data=activeNarrations();if(!data)return;data.rows.forEach((row,i)=>row.selected=editorialVisible(data.job,data.batch,i));saveNarrations(data);renderResults(current);};
$('editorial-bulk-save').onclick=async()=>{const data=activeNarrations();if(!data)return;const items=data.rows.flatMap((row,index)=>row.selected?[{index,status:$('editorial-bulk-status').value,note:data.batch.editorial?.[index]?.note||'',base_version:data.batch.editorial?.[index]?.version||0}]:[]);if(!items.length){toast('请先勾选要更新的文案。');return;}
  $('editorial-bulk-save').disabled=true;try{await saveAdoption(data,items);toast('已更新所选文案状态。');}catch(e){toast(e.message);}finally{$('editorial-bulk-save').disabled=false;}};
$('review-run').onclick=async()=>{const data=activeNarrations();if(!data)return;const indices=data.rows.flatMap((row,i)=>row.selected?[i]:[]);if(!indices.length||indices.length>300){toast('每次请选择 1–300 条文案分析。');return;}
  $('review-run').disabled=true;try{await flushNarrations(data);const signature=JSON.stringify(data.rows.map(row=>[row.text,row.revision]));const result=await api(`/jobs/${data.job.id}/drafts/${data.batch.id}/review`,{method:'POST',body:JSON.stringify({indices,threshold:80})});if(signature!==JSON.stringify(data.rows.map(row=>[row.text,row.revision]))||result.items.some(item=>item.revision!==data.rows[item.index].revision))throw new Error('分析过程中成稿已修改，请重新打开参考后再分析。');const state=editorialState(data.job,data.batch);state.review=result;state.signature=signature;if(current?.id===data.job.id)renderResults(current);$('editorial-message').textContent=`已分析 ${indices.length} 条。未勾选稿件未参与比较；相似度为文本重合提示。`;}catch(e){toast(e.message);}finally{$('review-run').disabled=false;}};
async function resumeBatch(job,batch){
  if(busy(job))return;try{await flushNarrations();await api(`/jobs/${job.id}/drafts/${batch.id}/resume`,{method:'POST'});await selectJob(job.id);sceneSelect('generate');toast('正在按原批次商品、模型和结构补齐；已有成稿保留。');}catch(e){toast(e.message);}
}
$('resume-batch').onclick=()=>{const data=activeNarrations();if(data)resumeBatch(data.job,data.batch);};
const previousRetryAction=$('retry').onclick;
$('retry').onclick=()=>{const batch=current?.batches.findLast(b=>(b.requested_count||0)>b.variants.length);if(batch&&(!current.last_error_operation||current.last_error_operation==='generate'))resumeBatch(current,batch);else previousRetryAction();};
function renderIteration(job){
  const pending=job.batches.some(b=>(b.requested_count||0)>b.variants.length)&&(!job.last_error_operation||job.last_error_operation==='generate');$('retry').textContent=pending?'补齐未完成批次':job.kind==='script'?'重新分析脚本':'重新转写';
  $('metadata-open').title=[job.project,job.product_label,...(job.tags||[])].filter(Boolean).join(' / ')||'设置项目、商品分类与标签';
  $('metadata-open').textContent=job.project?'项目：'+job.project:'分类与标签';
}

function historySearchParams(){const params=new URLSearchParams();if(historyTrash)params.set('trash','true');for(const [id,key] of [['library-search','q'],['library-project','project'],['library-product','product'],['library-tag','tag'],['library-start','start'],['library-end','end']]){const value=$(id).value.trim();if(value)params.set(key,value);}return params.size?'?'+params:'';}
let librarySearchTimer;
for(const id of ['library-search','library-product','library-tag','library-start','library-end'])$(id).oninput=()=>{clearTimeout(librarySearchTimer);librarySearchTimer=setTimeout(()=>refreshHistory().catch(e=>toast(e.message)),300);};
$('library-project').onchange=()=>refreshHistory().catch(e=>toast(e.message));
$('library-clear').onclick=()=>{for(const id of ['library-search','library-project','library-product','library-tag','library-start','library-end'])$(id).value='';refreshHistory().catch(e=>toast(e.message));};
async function loadLibraryCatalog(){const value=await api('/library/catalog'),selected=$('library-project').value;$('library-project').replaceChildren(new Option('全部项目',''));$('project-options').replaceChildren();for(const project of value.projects){$('library-project').append(new Option(project,project));$('project-options').append(new Option(project,project));}$('library-project').value=selected;}
$('metadata-open').onclick=()=>{if(!current)return;metadataVersion=current.metadata_version||0;$('metadata-title').value=current.title;$('metadata-project').value=current.project||'';$('metadata-product').value=current.product_label||'';$('metadata-tags').value=(current.tags||[]).join('，');$('metadata-message').textContent='';$('metadata-dialog').showModal();};
$('metadata-close').onclick=()=>$('metadata-dialog').close();
$('metadata-save').onclick=async()=>{if(!current)return;const id=current.id;$('metadata-save').disabled=true;try{const value=await api('/jobs/'+id+'/metadata',{method:'PATCH',body:JSON.stringify({title:$('metadata-title').value,project:$('metadata-project').value,product_label:$('metadata-product').value,tags:$('metadata-tags').value.split(/[,，]/).map(t=>t.trim()).filter(Boolean),base_version:metadataVersion})});if(currentId===id)render(value);$('metadata-dialog').close();await loadLibraryCatalog();await refreshHistory();}catch(e){$('metadata-message').textContent=e.message;}finally{$('metadata-save').disabled=false;}};

const previousImportAction=$('import-button').onclick;
$('import-button').onclick=()=>inputMode==='script'?openIntake().catch(e=>toast(e.message)):previousImportAction();
async function openIntake(){
  if(isSubmitting)return;captureImportDraft();const queue=scriptDocuments,rows=queue.pending();
  if(intakeContext?.uploading&&intakeContext.queue===queue){if(!$('intake-dialog').open)$('intake-dialog').showModal();return;}
  if(!rows.length&&!$('script-source-text').value.trim()){toast('请粘贴脚本或选择文档。');return;}
  const epoch=++intakeEpoch;
  const inputText=$('script-source-text').value;
  if(!intakeContext||intakeContext.queue!==queue||(!rows.length&&intakeContext.inputText!==inputText)){intakeContext={queue,epoch:selectionEpoch,inputText,records:[],busy:false};}
  const ctx=intakeContext;ctx.facts=$('reference-facts').value;ctx.autoAI=$('auto-ai').checked;ctx.originDraft=referenceDrafts.get(importJob);
  ctx.records=ctx.records.filter(record=>rows.length?record.row&&rows.some(row=>row.id===record.row.id):!record.row);
  if(!$('intake-dialog').open)$('intake-dialog').showModal();$('intake-message').textContent='正在本机读取，尚未创建脚本参考…';
  $('intake-confirm-current').disabled=$('intake-confirm-all').disabled=true;$('intake-file').disabled=true;$('intake-parts').replaceChildren();ctx.uploading=true;
  $('intake-project').value=current?.project||'';$('intake-product').value=current?.product_label||'';
  try{if(rows.length){for(const row of rows){
    if(ctx.records.some(record=>record.row?.id===row.id))continue;
    const form=new FormData();form.append('file',row.file);const value=await api('/script-previews/document',{method:'POST',body:form});ctx.records.push({row,value,parts:null,source:null});
  }}else if(!ctx.records.length){const value=await api('/script-previews/text',{method:'POST',body:JSON.stringify({text:$('script-source-text').value,title:'粘贴的脚本'})});ctx.records.push({row:null,value,parts:null,source:null});}}
  catch(e){ctx.lastError=e.message;$('intake-message').textContent=e.message;throw e;}finally{ctx.uploading=false;$('intake-file').disabled=false;}
  if(epoch!==intakeEpoch)return;$('intake-file').replaceChildren();ctx.records.forEach((record,i)=>$('intake-file').append(new Option(record.value.title,String(i))));showIntake();pollIntake(ctx);
}
function intakeRecord(){return intakeContext?.records[Number($('intake-file').value||0)];}
function showIntake(){
  const ctx=intakeContext,record=intakeRecord();if(!ctx||!record)return;const value=record.value,ready=value.status==='ready',confirmed=value.status==='confirmed';
  $('intake-file').disabled=ctx.busy||ctx.uploading;
  if((ready||confirmed)&&record.parts===null){record.source=value.source_text;record.parts=value.parts.map(part=>({...part,selected:true}));}
  $('intake-message').textContent=ctx.lastError||value.error||value.message||'读取中…';if(ready&&!ctx.lastError)$('intake-message').textContent+=` 检测到 ${record.parts.length} 份候选，请核对后确认。`;
  $('intake-source').value=record.source||value.source_text||'';$('intake-source').readOnly=ctx.busy||confirmed||!ready;
  $('intake-confirm-current').disabled=ctx.busy||!ready;$('intake-confirm-all').disabled=ctx.busy||!ctx.records.some(r=>r.value.status==='ready')||ctx.records.some(r=>['queued','working'].includes(r.value.status));
  for(const id of ['intake-one','intake-numbered','intake-separator'])$(id).disabled=ctx.busy||!ready;
  $('intake-parts').replaceChildren();
  (record.parts||[]).forEach((part,index)=>{const section=workflowElement('section','intake-part');const head=workflowElement('label','checkbox');const select=workflowElement('input');select.type='checkbox';select.checked=part.selected;select.disabled=ctx.busy||confirmed;select.onchange=()=>part.selected=select.checked;head.append(select,document.createTextNode(`导入第 ${index+1} 份`));
    const title=workflowElement('input');title.value=part.title;title.maxLength=160;title.setAttribute('aria-label',`第 ${index+1} 份脚本名称`);title.disabled=ctx.busy||confirmed;title.oninput=()=>part.title=title.value;
    const text=workflowElement('textarea');text.value=part.text;text.rows=5;text.maxLength=20000;text.setAttribute('aria-label',`第 ${index+1} 份脚本正文`);text.readOnly=ctx.busy||confirmed;text.oninput=()=>part.text=text.value;
    section.append(head,title,text);$('intake-parts').append(section);
  });
}
async function pollIntake(ctx){
  if(ctx!==intakeContext||!$('intake-dialog').open)return;
  try{let changed=false;for(const record of ctx.records){if(['queued','working'].includes(record.value.status)){const previous=record.value.status;record.value=await api('/script-previews/'+record.value.id);if(record===intakeRecord()&&previous!==record.value.status)changed=true;}}if(ctx===intakeContext){if(changed)showIntake();if(ctx.records.some(record=>['queued','working'].includes(record.value.status)))ctx.timer=setTimeout(()=>pollIntake(ctx),700);else{$('intake-confirm-all').disabled=ctx.busy||!ctx.records.some(r=>r.value.status==='ready');}}}catch(e){$('intake-message').textContent=e.message;}
}
$('intake-file').onchange=showIntake;$('intake-source').oninput=()=>{const record=intakeRecord();if(record)record.source=$('intake-source').value;};
$('intake-close').onclick=()=>$('intake-dialog').close();$('intake-dialog').addEventListener('close',()=>{if(intakeContext)clearTimeout(intakeContext.timer);});
function replaceIntakeParts(parts){const record=intakeRecord();if(!record||!parts.length||parts.length>50){toast('请将文档整理为 1–50 份脚本。');return;}record.parts=parts.map((part,i)=>({title:record.value.title+' · '+(i+1),text:part.trim(),selected:true}));showIntake();}
$('intake-one').onclick=()=>replaceIntakeParts([$('intake-source').value]);
$('intake-separator').onclick=()=>replaceIntakeParts(WorkflowRules.split($('intake-source').value,'separator'));
$('intake-numbered').onclick=()=>{const parts=WorkflowRules.split($('intake-source').value,'numbered');if(parts.length<2){toast('未发现明确的脚本编号，可手动插入分隔线后拆分。');return;}replaceIntakeParts(parts);};
async function confirmIntake(all){
  const ctx=intakeContext;if(!ctx||ctx.busy||ctx.uploading)return;const records=all?ctx.records.filter(record=>record.value.status==='ready'):[intakeRecord()].filter(Boolean);
  if(!records.length)return;
  for(const record of records){if(record.value.status!=='ready')return;const selected=record.parts?.filter(part=>part.selected)||[];if(!selected.length||selected.some(part=>!part.text.trim()||!part.title.trim())){toast('每个待导入文档至少勾选一份，且名称、正文不能为空。');return;}}
  ctx.busy=true;ctx.lastError='';showIntake();let first=null,total=0;
  try{for(const record of records){const parts=record.parts.filter(part=>part.selected).map(({title,text})=>({title,text}));const result=await api(`/script-previews/${record.value.id}/confirm`,{method:'POST',body:JSON.stringify({parts,facts:ctx.facts,auto_ai:ctx.autoAI,project:$('intake-project').value,product_label:$('intake-product').value})});
    first=first||result.jobs[0];total+=result.jobs.length;record.value.status='confirmed';record.value.message=`已确认导入 ${result.jobs.length} 份。`;
    if(record.row){const originalName=record.row.name;record.row.jobId=result.jobs[0];record.row.file=null;record.row.status='imported';if(parts.length>1)record.row.name=originalName+' · '+parts[0].title;
      for(let i=1;i<result.jobs.length;i++)ctx.queue.rows.push({id:'job-'+result.jobs[i],name:originalName+' · '+parts[i].title,size:null,file:null,jobId:result.jobs[i],status:'imported',error:''});}
    ctx.originDraft.scriptFiles=ctx.queue.snapshot();
  }
    if(creativeSpace==='script'&&selectionEpoch===ctx.epoch&&first){await selectJob(first);ctx.epoch=selectionEpoch;scriptDocuments=ctx.queue;captureImportDraft();renderScriptDocuments();sceneSelect('generate');}
    await refreshHistory();await loadLibraryCatalog();showIntake();$('intake-message').textContent=`已分别导入 ${total} 份脚本。`;
    if(!ctx.records.some(record=>record.value.status==='ready'))$('intake-dialog').close();
  }catch(e){ctx.lastError=e.message+' 已确认导入的部分仍保留，可继续处理其余文档。';}finally{ctx.busy=false;showIntake();}
}
$('intake-confirm-current').onclick=()=>confirmIntake(false);$('intake-confirm-all').onclick=()=>confirmIntake(true);

async function loadTasks(){const rows=await api('/tasks');$('task-center-list').replaceChildren();for(const row of rows){const card=workflowElement('div','task-center-item');card.append(workflowElement('strong','',row.title),workflowElement('p','hint',({queued:'排队',working:'处理中',done:'完成',error:'需处理'}[row.status]||row.status)+' · '+row.message));if(row.error_stage)card.append(workflowElement('p','hint','出错阶段：'+row.error_stage));if(row.progress)card.append(workflowElement('p','hint',`已保存 ${row.progress.completed} / ${row.progress.total} 条${row.remaining?' · 仍有未完成批次':''}`));const open=workflowElement('button','secondary','查看结果');open.onclick=async()=>{$('task-center-dialog').close();await selectJob(row.id);if(current.batches.length)sceneSelect('generate');};card.append(open);$('task-center-list').append(card);}
  if($('task-center-dialog').open&&rows.some(row=>['queued','working'].includes(row.status)))taskPoll=setTimeout(()=>loadTasks().catch(e=>toast(e.message)),2500);
}
$('task-center-open').onclick=()=>{$('task-center-dialog').showModal();loadTasks().catch(e=>toast(e.message));};$('task-center-close').onclick=()=>$('task-center-dialog').close();$('task-center-dialog').addEventListener('close',()=>clearTimeout(taskPoll));$('task-center-refresh').onclick=()=>{clearTimeout(taskPoll);loadTasks().catch(e=>toast(e.message));};
loadLibraryCatalog().catch(()=>{});if(current)renderIteration(current);
