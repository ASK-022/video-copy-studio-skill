'use strict';
const $ = id => document.getElementById(id);
let current = null, currentId = '', selectedFile = null, scriptDocuments=new ScriptDocuments(), inputMode = 'file', rawView = false, timer = null, selectionEpoch = 0, isSubmitting = false;
let lastBatchSignature = '';
const productDrafts=new ProductDrafts();
const referenceDrafts=new ReferenceDrafts();
let importJob=null,historyTrash=false;
let creativeSpace='video';const workspaceLastJobs={video:'',script:''};
function applyCreativeSpace(space){
  creativeSpace=space==='script'?'script':'video';referenceDrafts.setSpace(creativeSpace);
  const script=creativeSpace==='script';document.body.dataset.workspace=creativeSpace;
  $('video-workspace-tab').setAttribute('aria-selected',String(!script));$('script-workspace-tab').setAttribute('aria-selected',String(script));
  $('media-import-tabs').hidden=script;$('import-panel-title').textContent=script?'导入脚本':'导入参考';
  $('reference-sidebar-title').textContent=script?'脚本原文':'导入参考';
  $('workspace-eyebrow').textContent=script?'从原文，到更多表达':'从参考，到自己的表达';
  $('workspace-hero-title').textContent=script?'一份脚本，更多可能。':'好内容，清晰展开。';
  $('workspace-hero-description').textContent=script?'上传或粘贴脚本，保留原结构，写出不同版本。':'提取口播，读懂结构，再写出你的版本。';
  $('empty-state-title').textContent=script?'从一份脚本开始':'从一条参考视频开始';
  $('empty-state-description').textContent=script?'左侧粘贴原文或上传文档，分析结构后直接生成新版本。':'导入后，在这里校对文字、查看结构，再生成自己的文案。';
  for(const b of document.querySelectorAll('#scene-nav button'))b.hidden=script&&!['transcript','generate'].includes(b.dataset.scene);
  const transcriptNav=document.querySelector('#scene-nav [data-scene="transcript"]');transcriptNav.innerHTML='<small>01</small>'+(script?'原文与结构':'视频转文字');
  try{localStorage.setItem('vcs-creative-space',creativeSpace);}catch(_){}
}
async function switchCreativeSpace(space){
  if(space===creativeSpace)return;captureImportDraft();workspaceLastJobs[creativeSpace]=currentId;
  applyCreativeSpace(space);historyTrash=false;
  showNewReference(false);
  if(workspaceLastJobs[space])await selectJob(workspaceLastJobs[space],false);
  else await refreshHistory();
}
$('video-workspace-tab').onclick=()=>switchCreativeSpace('video').catch(e=>toast(e.message));
$('script-workspace-tab').onclick=()=>switchCreativeSpace('script').catch(e=>toast(e.message));
let providerCatalog=[],activeAiProviderId='',editingProviderId=null;
const creationMode=()=>document.querySelector('input[name=mode]:checked').value;
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const busy = item => item && ['queued','working'].includes(item.status);
function toast(message){ $('toast').textContent=message; $('toast').hidden=false; clearTimeout(timer); timer=setTimeout(()=>$('toast').hidden=true,5000); }
async function api(path,options={}){
  const headers={'X-Studio-Request':'1',...(options.body instanceof FormData ? {} : {'Content-Type':'application/json'}),...options.headers};
  let response=await fetch('/api'+path,{...options,headers});
  if(response.status===403){const error=await response.clone().json().catch(()=>({}));if(error.detail==='请重新打开客户端。'){await fetch('/');response=await fetch('/api'+path,{...options,headers});}}
  if(!response.ok){let text='请求失败，请重试。';try{const data=await response.json();text=typeof data.detail==='string'?data.detail:'输入信息有误，请检查后重试。';}catch(_){}throw new Error(text);}
  return response.json();
}
function setMode(mode){inputMode=mode;for(const key of ['file','link','script']){$(key+'-input-area').hidden=mode!==key;const tab=$(key+'-tab');if(tab)tab.setAttribute('aria-selected',String(mode===key));}$('auto-ai-label').textContent=mode==='script'?'导入后自动拆结构、提取商品':'转写后自动 AI 纠错、拆结构';renderImportButton();}
function captureImportDraft(){referenceDrafts.save(importJob,{mode:inputMode,file:selectedFile,fileName:selectedFile?.name||referenceDrafts.get(importJob).fileName,scriptFiles:scriptDocuments.snapshot(),scriptText:$('script-source-text').value,link:$('video-link').value,facts:$('reference-facts').value,autoAI:$('auto-ai').checked,provider:$('link-provider').value});}
function restoreImportDraft(job){importJob=job;const draft=referenceDrafts.get(job);selectedFile=draft.file;scriptDocuments=new ScriptDocuments(draft.scriptFiles||[]);$('script-document').value='';$('script-source-text').value=draft.scriptText||'';$('video-file').value='';$('file-name').textContent=draft.fileName||'点击选择或拖入视频';$('video-link').value=draft.link;$('reference-facts').value=draft.facts;$('auto-ai').checked=draft.autoAI;$('link-provider').value=draft.provider;setMode(draft.mode);renderScriptDocuments();}
function renderImportButton(){if(isSubmitting)return;const existing=current&&((inputMode==='file'&&current.kind==='upload'&&!selectedFile&&current.input_file)||(inputMode==='link'&&current.kind==='link'&&$('video-link').value.trim()===current.source)),pending=scriptDocuments.pending().length;$('import-button').disabled=Boolean(existing&&busy(current));$('import-button').innerHTML=(inputMode==='script'?(pending?'导入 '+pending+' 个脚本'+($('auto-ai').checked?'并分析':''):'导入脚本并'+($('auto-ai').checked?'分析结构':'保留原文')):existing?'重新提取本条口播':'开始提取口播')+' <span>→</span>';}
function showNewReference(reset=true){++selectionEpoch;if(reset)referenceDrafts.resetNew();current=null;currentId='';lastBatchSignature='';restoreImportDraft(null);$('job-content').hidden=true;$('empty-state').hidden=false;historyTrash=false;if(typeof resetMarkerUI==='function')resetMarkerUI();if(typeof resetTranscriptPreview==='function')resetTranscriptPreview();}
function startNewReference(){captureImportDraft();workspaceLastJobs[creativeSpace]='';showNewReference();refreshHistory().catch(e=>toast(e.message));}
$('new-reference').onclick=()=>startNewReference();
$('file-tab').onclick=()=>{setMode('file');captureImportDraft();}; $('link-tab').onclick=()=>{setMode('link');captureImportDraft();};
$('script-source-text').oninput=()=>captureImportDraft();
function renderScriptDocuments(){
  const list=$('script-document-list');list.replaceChildren();const pending=scriptDocuments.pending().length;
  $('script-document-summary').textContent=scriptDocuments.rows.length?`${scriptDocuments.rows.length} 个文件${pending?' · '+pending+' 个待导入':''}`:'';
  $('script-document').disabled=isSubmitting;$('script-document-choose').disabled=isSubmitting;$('script-source-text').readOnly=isSubmitting||pending>0;
  for(const row of scriptDocuments.rows){
    const item=document.createElement('div');item.className='script-document-item';const content=document.createElement('div');content.className='script-document-item-content';
    const name=document.createElement('strong');name.textContent=row.name;name.title=row.name;
    const meta=document.createElement('span');meta.textContent=[row.size!==null?(row.size<1024*1024?Math.max(1,Math.round(row.size/1024))+' KB':(row.size/1024/1024).toFixed(1)+' MB'):'',({ready:'待导入',uploading:'正在上传…',imported:'已导入',error:'上传失败'}[row.status]||'待导入')].filter(Boolean).join(' · ');
    content.append(name,meta);if(row.error){const error=document.createElement('small');error.textContent=row.error;error.className='save-warning';content.append(error);}
    const remove=document.createElement('button');remove.type='button';remove.className='quiet script-document-remove';remove.textContent=row.jobId?'删除':'移除';remove.setAttribute('aria-label',(row.jobId?'删除已导入文件 ':'移除待上传文件 ')+row.name);remove.disabled=isSubmitting||(row.jobId===currentId&&busy(current));
    remove.onclick=()=>removeScriptDocument(row).catch(e=>toast(e.message));item.append(content,remove);list.append(item);
  }
  $('script-document-note').hidden=!scriptDocuments.rows.some(row=>row.jobId);renderImportButton();
}
async function removeScriptDocument(row){
  if(isSubmitting)return;const queue=scriptDocuments;
  if(row.jobId)await api('/jobs/'+row.jobId,{method:'DELETE'});
  queue.remove(row.id);referenceDrafts.removeScriptDocument(row.id,row.jobId);captureImportDraft();
  if(row.jobId&&currentId===row.jobId){
    const next=queue.rows.find(item=>item.jobId);
    if(next)await selectJob(next.jobId);else{workspaceLastJobs.script='';showNewReference(false);$('script-source-text').value='';}
    if(creativeSpace==='script'){scriptDocuments=queue;captureImportDraft();}
  }
  renderScriptDocuments();await refreshHistory();toast(row.jobId?'已移入回收站，可恢复。':'已从待上传列表移除。');
}
function chooseScripts(files){
  if(isSubmitting)return;const incoming=[...files];if(!incoming.length)return;
  const valid=incoming.filter(file=>/\.(docx|pdf|txt)$/i.test(file.name)&&file.size>0&&file.size<=20*1024*1024);
  if(!valid.length){toast('请选择有正文且不超过 20 MB 的 DOCX、PDF 或 TXT。');return;}
  const result=scriptDocuments.add(valid);$('script-source-text').value='';setMode('script');captureImportDraft();renderScriptDocuments();
  if(valid.length<incoming.length)toast('已添加有效文件；不支持的格式、空文件或超过 20 MB 的文件未加入。');
  else if(!result.added)toast('这些文件已在列表中。');
}
$('script-document').onchange=e=>{chooseScripts(e.target.files);e.target.value='';};
$('script-document-choose').onclick=()=>$('script-document').click();
let scriptDragDepth=0;
for(const event of ['dragenter','dragover'])$('script-document-drop').addEventListener(event,e=>{e.preventDefault();e.stopPropagation();if(event==='dragenter')scriptDragDepth++;if(!isSubmitting)$('script-document-drop').classList.add('dragging');});
$('script-document-drop').ondragleave=e=>{e.preventDefault();if(--scriptDragDepth<=0){scriptDragDepth=0;$('script-document-drop').classList.remove('dragging');}};
$('script-document-drop').ondrop=e=>{e.preventDefault();e.stopPropagation();scriptDragDepth=0;$('script-document-drop').classList.remove('dragging');chooseScripts(e.dataTransfer.files);};
for(const id of ['video-link','reference-facts','auto-ai','link-provider'])$(id).addEventListener('input',()=>{captureImportDraft();renderImportButton();});
function chooseFile(file){if(!file)return;if(file.size>500*1024*1024){toast('请选择 500 MB 以内的文件。');return;}if(currentId)startNewReference();selectedFile=file;$('file-name').textContent=file.name;setMode('file');captureImportDraft();}
$('video-file').onchange=e=>chooseFile(e.target.files[0]);
for(const event of ['dragenter','dragover'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.add('dragging');});
for(const event of ['dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('dragging');if(event==='drop')chooseFile(e.dataTransfer.files[0]);});
$('import-button').onclick=async()=>{
  if(isSubmitting)return;
  if(inputMode==='file'&&!selectedFile&&!(current?.kind==='upload'&&current.input_file)){toast('请先选择视频。');return;}
  if(inputMode==='link'&&!$('video-link').value.trim()){toast('请先粘贴视频链接。');return;}
  if(inputMode==='script'&&!scriptDocuments.pending().length&&!$('script-source-text').value.trim()){toast('请粘贴脚本，或上传脚本文档。');return;}
  captureImportDraft();const requestEpoch=selectionEpoch,source=current,mode=inputMode,file=selectedFile,draft={...referenceDrafts.get(importJob)};
  isSubmitting=true;renderScriptDocuments();$('import-button').disabled=true;$('import-button').textContent=inputMode==='link'?'正在提交链接…':'正在导入文件与文字…';
  try{
    let result;
    const options={facts:draft.facts,auto_ai:draft.autoAI,provider:draft.provider};
    if(mode==='script'){
      if(scriptDocuments.pending().length){
        const queue=scriptDocuments,originDraft=referenceDrafts.get(importJob);
        const batch=await queue.submit(async file=>{const form=new FormData();form.append('file',file);form.append('facts',draft.facts);form.append('auto_ai',draft.autoAI);return api('/jobs/script/upload',{method:'POST',body:form});},(index,total)=>{
          originDraft.scriptFiles=queue.snapshot();if(scriptDocuments===queue)renderScriptDocuments();$('import-button').textContent=`正在上传 ${index} / ${total}…`;
        });result=batch.first;
        if(requestEpoch===selectionEpoch&&result){historyTrash=false;await selectJob(result.id);if(currentId===result.id){scriptDocuments=queue;captureImportDraft();renderScriptDocuments();if(typeof sceneSelect==='function')sceneSelect('generate');}}
        await refreshHistory();toast(`已导入 ${batch.imported} 个文件`+(batch.failed?'，失败文件已保留，可单独重试。':'，每个文件独立保存。'));return;
      }
      else result=await api('/jobs/script',{method:'POST',body:JSON.stringify({text:draft.scriptText,facts:draft.facts,auto_ai:draft.autoAI})});
    }
    else if(source&&((mode==='file'&&!file&&source.kind==='upload')||(mode==='link'&&source.kind==='link'&&draft.link.trim()===source.source))){result=await api('/jobs/'+source.id+'/retry',{method:'POST',body:JSON.stringify(options)});}
    else if(mode==='file'){const form=new FormData();form.append('file',file);form.append('facts',draft.facts);form.append('auto_ai',draft.autoAI);result=await api('/jobs/upload',{method:'POST',body:form});}
    else result=await api('/jobs/link',{method:'POST',body:JSON.stringify({url:draft.link,...options})});
    if(requestEpoch===selectionEpoch){historyTrash=false;await selectJob(result.id);if(mode==='script'&&typeof sceneSelect==='function')sceneSelect('generate');}await refreshHistory();
  }catch(e){toast(e.message);}finally{isSubmitting=false;$('import-button').disabled=false;renderScriptDocuments();renderImportButton();}
};
async function refreshHistory(){
  const trashMode=historyTrash,space=creativeSpace,all=await api('/jobs'+(trashMode?'?trash=true':''));if(trashMode!==historyTrash||space!==creativeSpace)return [];
  const jobs=all.filter(job=>space==='script'?job.kind==='script':job.kind!=='script');
  $('history-heading').textContent=trashMode?'回收站':space==='script'?'脚本参考库':'参考库';$('history-trash-toggle').textContent=trashMode?'返回参考库':'回收站';
  $('history-count').textContent=jobs.length;$('history-list').replaceChildren();
  for(const job of jobs){
    const row=document.createElement('div');row.className='history-row'+(job.id===currentId?' selected':'');
    const button=document.createElement('button');button.className='history-item';button.disabled=trashMode;
    const title=document.createElement('span');title.className='history-title';title.textContent=(job.pinned?'★ ':'')+job.title;
    const meta=document.createElement('span');meta.className='history-meta';meta.textContent=(job.pinned?'已置顶 · ':'')+new Date(job.created*1000).toLocaleDateString('zh-CN')+' · '+({queued:'排队中',working:'处理中',done:'已完成',error:'需处理'}[job.status]||job.status);
    button.append(title,meta);button.onclick=()=>selectJob(job.id).catch(e=>toast(e.message));row.append(button);
    const actions=document.createElement('div');actions.className='history-actions';
    if(trashMode){const restore=document.createElement('button');restore.className='quiet';restore.textContent='恢复';restore.setAttribute('aria-label','恢复 '+job.title);restore.onclick=async()=>{try{await api('/jobs/'+job.id+'/history/restore',{method:'POST'});toast('已恢复到最近参考。');await refreshHistory();}catch(e){toast(e.message);}};actions.append(restore);}
    else{
      const pin=document.createElement('button');pin.className='quiet';pin.textContent=job.pinned?'取消置顶':'置顶';pin.setAttribute('aria-label',(job.pinned?'取消置顶 ':'置顶 ')+job.title);pin.onclick=async()=>{try{await api('/jobs/'+job.id+'/history/pin',{method:'POST',body:JSON.stringify({pinned:!job.pinned})});await refreshHistory();}catch(e){toast(e.message);}};
      const remove=document.createElement('button');remove.className='quiet history-delete';remove.textContent='删除';remove.disabled=busy(job);remove.setAttribute('aria-label','删除 '+job.title);remove.onclick=async()=>{try{await api('/jobs/'+job.id,{method:'DELETE'});referenceDrafts.removeScriptDocument('',job.id);scriptDocuments.rows=scriptDocuments.rows.filter(row=>row.jobId!==job.id);renderScriptDocuments();toast('已移入回收站，可恢复。');const next=await refreshHistory();if(currentId===job.id){if(next.length)await selectJob(next[0].id);else startNewReference();}}catch(e){toast(e.message);}};
      actions.append(pin,remove);
    }
    row.append(actions);$('history-list').append(row);
  }
  if(!jobs.length)$('history-list').innerHTML='<p class="hint">'+(trashMode?'回收站为空。':space==='script'?'导入的脚本会单独保存在这里。':'导入的视频会保存在这里。')+'</p>';
  return jobs;
}
$('history-trash-toggle').onclick=()=>{historyTrash=!historyTrash;refreshHistory().catch(e=>toast(e.message));};
async function selectJob(id,saveDraft=true){if(saveDraft)captureImportDraft();const epoch=++selectionEpoch;const job=await api('/jobs/'+id);if(epoch!==selectionEpoch)return;const space=job.kind==='script'?'script':'video';if(space!==creativeSpace)applyCreativeSpace(space);workspaceLastJobs[space]=id;currentId=id;current=null;lastBatchSignature='';restoreImportDraft(job);render(job,true);renderImportButton();await refreshHistory();}
function render(job,fresh=false){
  const previous=current;current=job;const working=busy(job);
  $('raw-tab').textContent=job.kind==='script'?'导入原文':'原始转写';$('generation-reference-raw').textContent=job.kind==='script'?'导入原文':'原始转写';
  $('empty-state').hidden=true;$('job-content').hidden=false;$('job-title').textContent=job.title;$('job-status').textContent=job.message;
  $('error-box').hidden=!job.error;$('error-box').textContent=job.error;
  $('retry').hidden=working||job.status!=='error';$('export').href='/api/jobs/'+job.id+'/export';$('export').hidden=!job.corrected;
  // Polling must not overwrite unsaved user edits.
  if(fresh||!previous||previous.corrected!==job.corrected){$('transcript').value=job.corrected||'';}
  $('raw-transcript').textContent=job.raw||'本地转写尚未完成。';$('transcript').disabled=working;
  $('correct-button').disabled=working||!job.corrected;$('analyze-button').disabled=working||!job.corrected;
  $('generate-button').disabled=working||!job.structure.length;
  if(fresh){rawView=false;updateTextView();}
  renderProduct(job);
  const generating=working&&job.operation==='generate';
  $('stop-generation').hidden=!generating;$('stop-generation').disabled=false;
  const progress=job.generation_progress;
  $('generation-hint').textContent=generating&&progress?`已完成 ${progress.completed} / ${progress.total} 条，可随时停止后续生成。`:'每条逐段对应原结构；发布前请核对商品事实。';
  $('text-count').textContent=(job.corrected||'').length+' 字';
  $('correction-details').hidden=!job.corrections.length&&!job.uncertainties.length;
  $('correction-summary').textContent=`${job.corrections.length} 处纠错 · ${job.uncertainties.length} 项待确认`;
  $('correction-list').innerHTML=job.corrections.map(x=>`<div class="correction-row"><del>${escapeHTML(x.original)}</del> → <ins>${escapeHTML(x.replacement)}</ins><br>${escapeHTML(x.reason)}</div>`).join('')+job.uncertainties.map(x=>`<div class="correction-row">待确认：${escapeHTML(x)}</div>`).join('');
  $('structure-area').hidden=!job.structure.length;
  $('structure-preview').innerHTML=job.structure.slice(0,6).map(s=>`<span>${escapeHTML(s.id+' · '+s.role)}</span>`).join('')+(job.structure.length>6?`<span>… 共 ${job.structure.length} 段</span>`:'');
  $('structure-summary').textContent=`查看逐段参考文案（${job.structure.length} 段）`;
  $('structure-list').innerHTML=job.structure.map(s=>`<div class="structure-row"><span class="index">${String(s.id).padStart(2,'0')}</span><span class="role">${escapeHTML(s.role)}</span><span>${escapeHTML(s.text)}</span></div>`).join('');
  $('dirty-note').hidden=$('transcript').value===job.corrected;
  const signature=job.id+':'+job.batches.map(x=>x.id+':'+x.variants.length+':'+x.complete+':'+x.variants.map(v=>v.manuscript?.revision||0).join('.')).join(',');if(signature!==lastBatchSignature){lastBatchSignature=signature;renderResults(job);}
  renderScriptDocuments();renderImportButton();
  if(typeof renderSceneUI==='function')renderSceneUI(job);
  if(typeof renderMarkerUI==='function')renderMarkerUI(job);
  if(typeof renderWorkspaceState==='function')renderWorkspaceState();
}
function renderProduct(job){
  const mode=creationMode(),draft=productDrafts.sync(job),profile=job.product_profile;
  $('product-facts').value=draft[mode];
  $('product-label').innerHTML=(mode==='switch'?'目标商品与卖点':'当前商品与卖点')+' <span class="required">必填</span>';
  $('extract-product').hidden=mode==='switch';$('extract-product').disabled=busy(job)||!job.corrected;
  $('extract-product').textContent=profile?'重新提取':'提取商品卖点';
  $('restore-product').hidden=mode==='switch'||!draft.sameEdited||!job.product_facts;
  $('product-hint').textContent=mode==='switch'?'填写新商品资料；原视频的商品与卖点保留在「同商品裂变」中。':
    job.product_warning||(draft.sameEdited?'已手动编辑，可继续修改或恢复视频资料。':profile?'已从参考口播自动提取，可直接编辑；请核对商品信息。':'AI 纠错、拆结构后自动填写；已有视频也可点击「提取商品卖点」。');
  const review=profile?.needs_confirmation||[];
  $('product-review').hidden=mode==='switch'||!review.length;
  $('product-review-summary').textContent=`${review.length} 项商品信息待确认（未自动加入卖点）`;
  $('product-review-list').innerHTML=review.map(x=>`<p>${escapeHTML(x.value)}<br><span class="hint">原文：${escapeHTML(x.source_excerpt)}</span></p>`).join('');
  if(typeof renderProductLibrary==='function')renderProductLibrary(job);
  if(typeof renderProductMaterial==='function')renderProductMaterial(job);
}
$('product-facts').oninput=()=>{if(current){productDrafts.edit(current,creationMode(),$('product-facts').value);$('restore-product').hidden=creationMode()==='switch'||!current.product_facts;}};
$('restore-product').onclick=()=>{if(current){productDrafts.restore(current);renderProduct(current);}};
function updateTextView(){$('transcript').hidden=rawView;$('raw-transcript').hidden=!rawView;$('raw-tab').classList.toggle('active',rawView);$('corrected-tab').classList.toggle('active',!rawView);}
$('raw-tab').onclick=()=>{rawView=true;updateTextView();};$('corrected-tab').onclick=()=>{rawView=false;updateTextView();};
$('transcript').oninput=()=>{$('dirty-note').hidden=!current||$('transcript').value===current.corrected;$('text-count').textContent=$('transcript').value.length+' 字';};
async function copyText(text){try{await navigator.clipboard.writeText(text);toast('已复制。');}catch(_){toast('复制失败，请选中文字后复制。');}}
$('copy-transcript').onclick=()=>copyText(rawView?current?.raw||'':$('transcript').value);
async function processText(operation){if(!current||busy(current))return;try{await api('/jobs/'+current.id+'/'+operation,{method:'POST',body:JSON.stringify({text:$('transcript').value,facts:$('reference-facts').value})});await selectJob(current.id);}catch(e){toast(e.message);}}
$('correct-button').onclick=()=>processText('correct');$('analyze-button').onclick=()=>processText('analyze');
$('extract-product').onclick=()=>processText('extract-product');
$('retry').onclick=async()=>{if(!current)return;try{await api('/jobs/'+current.id+'/retry',{method:'POST'});await selectJob(current.id);}catch(e){toast(e.message);}};
for(const input of document.querySelectorAll('input[name=mode]'))input.onchange=()=>{if(current)renderProduct(current);};
$('generate-button').onclick=async()=>{if(!current||busy(current))return;const count=Number($('count').value);if(!Number.isSafeInteger(count)||count<1){toast('生成条数请填写大于 0 的整数。');$('count').focus();return;}try{await api('/jobs/'+current.id+'/drafts/generate',{method:'POST',body:JSON.stringify({mode:creationMode(),facts:$('product-facts').value,count,direction:$('direction').value,reference_text:$('transcript').value,quality_check:$('quality-check').checked,...(typeof generationOptions==='function'?generationOptions():{})})});await selectJob(current.id);}catch(e){toast(e.message);}};
$('stop-generation').onclick=async()=>{if(!current)return;try{await api('/jobs/'+current.id+'/drafts/stop',{method:'POST'});$('stop-generation').disabled=true;toast('已请求停止，当前一轮返回后结束，已完成的文案会保留。');}catch(e){toast(e.message);}};
function renderStructuredResults(job,batch){
  $('results').replaceChildren();
  function appendBatch(batch,container){
    const label=document.createElement('div');label.className='batch-heading';
    label.textContent=({same:'同商品裂变',switch:'换商品套结构',original:'原创脚本'}[batch.mode])+' · '+new Date(batch.created*1000).toLocaleString('zh-CN')+(batch.requested_count?` · ${batch.variants.length} / ${batch.requested_count} 条`:'');
    container.append(label);
    if(batch.review_notes?.length){const notes=document.createElement('details');const summary=document.createElement('summary');summary.textContent='编辑提示（不属于口播）';notes.append(summary);for(const note of batch.review_notes){const line=document.createElement('p');line.textContent=note;notes.append(line);}container.append(notes);}
    batch.variants.forEach((variant,i)=>{
      const card=document.createElement('article');card.className='draft';
      const full=variant.segments.map(s=>s.text).join('\n\n');
      card.innerHTML=`<div class="draft-heading"><span class="draft-index">${String(i+1).padStart(2,'0')}</span><h3>${escapeHTML(variant.title)}</h3><button class="quiet">复制口播</button></div>`+variant.segments.map(s=>`<p class="draft-paragraph"><span class="role">${escapeHTML(s.id+' · '+s.role)}</span>${escapeHTML(s.text)}</p>`).join('')+`<details><summary>查看完整口播</summary><p class="draft-full">${escapeHTML(full)}</p></details>`;
      card.querySelector('button').onclick=()=>copyText(full);container.append(card);
      if(variant.quality_error||variant.revision_error){const warning=document.createElement('p');warning.className='notice';warning.textContent=variant.quality_error||variant.revision_error;card.append(warning);}
      if(variant.production_segments){const production=document.createElement('details');production.innerHTML='<summary>分段拍摄表 · TTS 口播</summary>'+reportHTML('| 段落功能 | 时长预算（秒） | 口播要点 | 屏幕文字建议 |\n| --- | --- | --- | --- |\n'+variant.production_segments.map(s=>'| '+[s.role,s.duration_budget,s.text,s.screen_suggestion].map(v=>String(v).replace(/\|/g,'／').replace(/\n/g,' ')).join(' | ')+' |').join('\n'))+'<p class="draft-full">'+escapeHTML(variant.tts_narration)+'</p>';card.append(production);}
      if(variant.quality){const quality=document.createElement('details');const q=variant.quality;quality.innerHTML='<summary>六维质检 · '+escapeHTML(q.average)+' / 10 · '+escapeHTML(q.grade)+(q.needs_revision?' · 仍有待改进项':'')+'</summary>'+reportHTML('| 维度 | 分数 | 成稿引用 | 说明 |\n| --- | --- | --- | --- |\n'+q.scores.map(s=>'| '+[s.dimension,s.score,s.quote,s.reason].map(v=>String(v).replace(/\|/g,'／')).join(' | ')+' |').join('\n'))+'<p class="hint">'+escapeHTML(variant.revision?.performed?'已按低分项自动改写一轮：'+variant.revision.reason:'各维度均达到 7 分；评分属于编辑评估。')+'</p>';card.append(quality);}
    });
  }
  appendBatch(batch,$('results'));
}
function providerStatus(id,ready){$(id).textContent=ready?'已配置':'未连接';$(id).classList.toggle('ready',ready);}
async function refreshSettings(){
  const catalog=await api('/providers');providerCatalog=catalog.providers;activeAiProviderId=catalog.active_ai_id;
  const active=providerCatalog.find(p=>p.id===activeAiProviderId);
  $('ai-dot').classList.toggle('ready',!!active?.has_key);
  $('ai-service-summary').textContent=active?`${active.name} · ${active.model}${active.has_key?'':' · 未配置 Key'}`:'未选择';
  $('ai-provider-select').replaceChildren();
  for(const profile of providerCatalog){const option=document.createElement('option');option.value=profile.id;option.textContent=profile.name+' · '+profile.model+(profile.has_key?'':'（未配置 Key）');option.disabled=!profile.has_key&&profile.id!==activeAiProviderId;$('ai-provider-select').append(option);}
  $('ai-provider-select').value=activeAiProviderId;
  renderAIProviders();return active;
}
function renderAIProviders(){
  $('ai-provider-list').replaceChildren();
  for(const profile of providerCatalog){
    const card=document.createElement('article');card.className='provider-card';card.dataset.providerId=profile.id;
    const row=document.createElement('div');row.className='provider-row';
    const icon=document.createElement('span');icon.className='provider-icon';icon.textContent=profile.name.slice(0,2).toUpperCase();
    const info=document.createElement('div');info.className='provider-info';
    const name=document.createElement('strong');name.textContent=profile.name;
    const description=document.createElement('p');description.textContent=profile.model+' · '+profile.base_url;
    const status=document.createElement('span');status.className='provider-status'+(profile.has_key?' ready':'');status.textContent=(profile.active?'当前使用 · ':'')+(profile.has_key?'已配置':'待配置 Key');
    info.append(name,description,status);
    const actions=document.createElement('div');actions.className='provider-row-actions';
    const use=document.createElement('button');use.type='button';use.className=profile.active?'quiet':'secondary';use.textContent=profile.active?'使用中':'使用';use.disabled=profile.active||!profile.has_key;use.setAttribute('aria-label','使用 '+profile.name);use.onclick=async()=>{try{await api('/providers/active',{method:'PUT',body:JSON.stringify({provider_id:profile.id})});await refreshSettings();if(editingProviderId)updateEditorControls();toast('已切换到 '+profile.name+'，新启动的文字任务将使用此服务商。');}catch(e){toast(e.message);}};
    const manage=document.createElement('button');manage.type='button';manage.className='secondary';manage.textContent='管理';manage.setAttribute('aria-label','管理 '+profile.name);manage.onclick=()=>openProviderEditor(profile.id);
    actions.append(use,manage);row.append(icon,info,actions);card.append(row);$('ai-provider-list').append(card);
  }
}
function updateEditorControls(){
  const profile=providerCatalog.find(p=>p.id===editingProviderId);
  $('key-status').textContent=profile?.has_key?'已加密保存；留空不修改':'未配置';
  $('clear-key').hidden=!profile?.has_key;
  $('provider-remove').hidden=!profile||profile.active;
}
function openProviderEditor(id=null){
  editingProviderId=id;const profile=providerCatalog.find(p=>p.id===id);
  $('provider-editor-title').textContent=profile?'管理 '+profile.name:'添加服务商';
  $('provider-name').value=profile?.name||'';$('api-base').value=profile?.base_url||'';$('api-model').value=profile?.model||'';$('api-key').value='';
  $('provider-json-mode').checked=profile?.json_mode??false;
  $('settings-message').hidden=true;$('ai-config-panel').hidden=false;updateEditorControls();
  $('provider-name').focus();
}
function setSettingsTab(tab){$('settings-providers-pane').hidden=tab!=='providers';$('settings-services-pane').hidden=tab!=='services';$('settings-nav-providers').classList.toggle('active',tab==='providers');$('settings-nav-services').classList.toggle('active',tab==='services');}
async function openSettings(target='providers'){
  try{
    const [, ,prefs,health]=await Promise.all([refreshSettings(),refreshTikHub(),api('/services'),api('/health'),refreshFeishu()]);
    $('default-link-provider').value=prefs.default_link_provider;
    $('ai-provider-select').value=prefs.ai_provider_id;
    $('provider-local-status').textContent=health.asr_ready?'本机已就绪':'尚未安装';$('provider-local-status').classList.toggle('ready',health.asr_ready);
    $('settings-message').hidden=true;$('tikhub-message').hidden=true;$('services-message').hidden=true;
    $('ai-config-panel').hidden=true;$('tikhub-config-panel').hidden=target!=='tikhub';$('feishu-config-panel').hidden=target!=='feishu';
    setSettingsTab(target==='services'?'services':'providers');
    if(!$('settings-dialog').open)$('settings-dialog').showModal();
    if(target==='ai')openProviderEditor(activeAiProviderId);
    if(target==='feishu')$('feishu-app-id').focus();
  }catch(e){toast(e.message);}
}
$('settings-open').onclick=()=>openSettings();
$('settings-nav-providers').onclick=()=>setSettingsTab('providers');$('settings-nav-services').onclick=()=>setSettingsTab('services');
$('provider-add').onclick=()=>openProviderEditor();
$('provider-editor-close').onclick=()=>{$('ai-config-panel').hidden=true;$('api-key').value='';};
$('tikhub-manage').onclick=()=>{$('tikhub-config-panel').hidden=!$('tikhub-config-panel').hidden;if(!$('tikhub-test-url').value)$('tikhub-test-url').value=$('video-link').value;};
$('service-ai-configure').onclick=()=>setSettingsTab('providers');
$('services-form').onsubmit=async e=>{e.preventDefault();$('services-save').disabled=true;const note=$('services-message');note.hidden=false;note.classList.remove('error');try{const prefs=await api('/services',{method:'PUT',body:JSON.stringify({ai_provider_id:$('ai-provider-select').value,default_link_provider:$('default-link-provider').value})});await refreshSettings();referenceDrafts.setDefault(prefs.default_link_provider);if(!importJob)restoreImportDraft(null);note.textContent='服务选择已保存，新启动的文字任务使用所选服务商。';}catch(error){note.classList.add('error');note.textContent=error.message;}finally{$('services-save').disabled=false;}};
$('settings-close').onclick=()=>$('settings-dialog').close();
async function refreshTikHub(){const config=await api('/tikhub/settings');$('tikhub-key').value='';$('tikhub-key-status').textContent=config.has_key?'已加密保存；留空不修改':'未配置';providerStatus('provider-tikhub-status',config.has_key);$('tikhub-manage').textContent=config.has_key?'管理':'＋连接';$('default-link-provider').querySelector('option[value=tikhub]').disabled=!config.has_key;return config;}
$('tikhub-open').onclick=()=>{$('tikhub-test-url').value=$('video-link').value;openSettings('tikhub');};
async function saveTikHub(test=false){$('tikhub-test').disabled=true;$('tikhub-save').disabled=true;const note=$('tikhub-message');note.hidden=false;note.classList.remove('error');try{await api('/tikhub/settings',{method:'PUT',body:JSON.stringify({key:$('tikhub-key').value.trim()})});await refreshTikHub();if(test){note.textContent='正在请求 TikHub 解析…';const result=await api('/tikhub/test',{method:'POST',body:JSON.stringify({url:$('tikhub-test-url').value})});note.textContent=`解析成功，已取得视频地址（${result.elapsed_seconds} 秒）。\n${result.title}\n可关闭设置，选择 TikHub 后导入并本地转写。`;}else note.textContent='TikHub 设置已保存。';}catch(e){note.classList.add('error');note.textContent=e.message;}finally{$('tikhub-test').disabled=false;$('tikhub-save').disabled=false;}}
$('tikhub-form').onsubmit=e=>{e.preventDefault();saveTikHub();};$('tikhub-test').onclick=()=>saveTikHub(true);
$('tikhub-clear').onclick=async()=>{try{await api('/tikhub/settings',{method:'PUT',body:JSON.stringify({clear_key:true})});await refreshTikHub();toast('已清除 TikHub Key。');}catch(e){toast(e.message);}};
function settingsMessage(text,error=false){$('settings-message').hidden=false;$('settings-message').textContent=text;$('settings-message').classList.toggle('error',error);}
async function saveSettings(test=false,activate=false){
  if(!$('settings-form').reportValidity())return;
  $('save-ai').disabled=true;$('test-ai').disabled=true;$('provider-save-use').disabled=true;
  try{
    const profile=await api('/providers'+(editingProviderId?'/'+editingProviderId:''),{method:editingProviderId?'PUT':'POST',body:JSON.stringify({name:$('provider-name').value.trim(),base_url:$('api-base').value.trim(),model:$('api-model').value.trim(),key:$('api-key').value.trim(),json_mode:$('provider-json-mode').checked})});
    editingProviderId=profile.id;$('api-key').value='';
    if(activate)await api('/providers/active',{method:'PUT',body:JSON.stringify({provider_id:profile.id})});
    await refreshSettings();updateEditorControls();$('provider-editor-title').textContent='管理 '+profile.name;
    if(test){settingsMessage('配置已保存，正在测试这个服务商…');await api('/providers/'+profile.id+'/test',{method:'POST'});settingsMessage('连接成功。可在列表点「使用」，或到「服务」页选择。');}
    else settingsMessage(activate?'已保存并切换到 '+profile.name+'。':'配置已独立保存，不影响当前使用的服务商。');
  }catch(e){settingsMessage(e.message,true);await refreshSettings().catch(()=>{});updateEditorControls();}
  finally{$('save-ai').disabled=false;$('test-ai').disabled=false;$('provider-save-use').disabled=false;}
}
$('settings-form').onsubmit=e=>{e.preventDefault();saveSettings();};$('test-ai').onclick=()=>saveSettings(true);
$('provider-save-use').onclick=()=>saveSettings(false,true);
$('clear-key').onclick=async()=>{const p=providerCatalog.find(p=>p.id===editingProviderId);if(!p)return;try{await api('/providers/'+p.id,{method:'PUT',body:JSON.stringify({name:p.name,base_url:p.base_url,model:p.model,clear_key:true})});await refreshSettings();openProviderEditor(p.id);settingsMessage('已清除这个服务商的 Key，其他配置不受影响。');}catch(e){settingsMessage(e.message,true);}};
$('provider-remove').onclick=async()=>{if(!editingProviderId)return;try{await api('/providers/'+editingProviderId,{method:'DELETE'});editingProviderId=null;$('ai-config-panel').hidden=true;$('api-key').value='';await refreshSettings();toast('已移除该服务商配置。');}catch(e){settingsMessage(e.message,true);}};
async function poll(){try{if(currentId&&busy(current)){const id=currentId;const item=await api('/jobs/'+id);if(id===currentId){const wasBusy=busy(current);render(item);if(wasBusy&&!busy(item)){await refreshHistory();toast(item.status==='done'?'处理完成。':item.error);}}}}catch(e){toast(e.message);}finally{setTimeout(poll,1800);}}
(async()=>{try{let initialSpace='video';try{initialSpace=localStorage.getItem('vcs-creative-space')||'video';}catch(_){}applyCreativeSpace(initialSpace);const [,prefs]=await Promise.all([refreshSettings(),api('/preferences')]);referenceDrafts.setDefault(prefs.default_link_provider);$('link-provider').value=prefs.default_link_provider;const jobs=await refreshHistory();if(jobs.length)await selectJob(jobs[0].id);else restoreImportDraft(null);}catch(e){toast(e.message);}poll();})();

// Manual, read-only release check; updates are applied by the Windows manager.
$('updates-check').onclick=async()=>{
  const button=$('updates-check'),status=$('updates-status');button.disabled=true;status.textContent='正在检查正式版…';
  try{
    const result=await api('/updates');
    status.textContent=`本机 v${result.current} · 正式版 v${result.latest}。`+(result.update_available?'发现新版。打开安装管理器点击“安装 / 更新”，或查看发布页下载新版。':'当前已是最新版本。');
    if(result.update_available){
      const link=document.createElement('a');link.href=result.release_url;link.target='_blank';link.rel='noreferrer';link.textContent=' 查看新版与下载';status.append(link);
    }
  }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
};
