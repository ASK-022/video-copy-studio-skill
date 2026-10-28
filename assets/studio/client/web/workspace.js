'use strict';
// Persistent manuscripts, reference comparison, product facts and generation focus.
const manuscriptWrites=new Map(),focusDrafts=new Map(),productSelections=new Map();
let libraryProducts=[],libraryEditing=null,versionContext=null,rewriteContext=null,focusOffset=0,focusEpoch=0;
const versionKinds={generated:'生成原稿',edit:'人工修改',restore:'恢复版本',rewrite:'AI 单条重写'};
const manuscriptKey=(data,index)=>`${data.job.id}:${data.batch.id}:${index}`;
const manuscriptPath=(data,index)=>`/jobs/${data.job.id}/drafts/${data.batch.id}/${index}`;
function manuscriptBadge(key,row){
  for(const el of document.querySelectorAll('[data-manuscript-key]'))if(el.dataset.manuscriptKey===key){
    el.textContent=row.saveStatus==='conflict'?'版本冲突 · 到版本记录中另存':row.saveStatus==='error'?'未保存成功 · 到版本记录中重试':row.dirty?'正在保存到本机…':`已保存到本机 · v${row.revision||0}`;
    el.classList.toggle('save-warning',['conflict','error'].includes(row.saveStatus));
  }
}
function acceptManuscript(data,index,value){
  const row=data.rows[index];Object.assign(row,{text:value.text,segments:value.segments,revision:value.revision,persistedText:value.text,dirty:false,saveStatus:'saved'});
  data.batch.variants[index].manuscript=value;
  const live=current?.id===data.job.id?current.batches.find(b=>b.id===data.batch.id):null;
  if(live?.variants[index])live.variants[index].manuscript=value;
  narrationDrafts.save(data.job,data.batch,data.rows);manuscriptBadge(manuscriptKey(data,index),row);
}
function queueNarrationSaves(data){
  data.rows.forEach((row,index)=>{
    const key=manuscriptKey(data,index);
    manuscriptBadge(key,row);
    if(row.text===row.persistedText&&!row.dirty)return;
    if(['conflict','error'].includes(row.saveStatus)&&row.failedText===row.text)return;
    row.dirty=true;row.saveStatus='pending';manuscriptBadge(key,row);
    let entry=manuscriptWrites.get(key);if(!entry){entry={data,index,promise:null,timer:null};manuscriptWrites.set(key,entry);}
    entry.data=data;entry.index=index;clearTimeout(entry.timer);
    entry.timer=setTimeout(()=>persistNarration(entry).catch(()=>{}),650);
  });
  narrationDrafts.save(data.job,data.batch,data.rows);
}
async function persistNarration(entry){
  clearTimeout(entry.timer);entry.timer=null;
  if(entry.promise){await entry.promise;if(entry.data.rows[entry.index].dirty)return persistNarration(entry);return;}
  const {data,index}=entry,row=data.rows[index];if(!row.dirty)return;
  if(!row.text.trim()){row.saveStatus='error';row.failedText=row.text;manuscriptBadge(manuscriptKey(data,index),row);throw new Error('文案为空，尚未保存。可以继续编辑或从版本记录恢复。');}
  const sent=row.text,segments=row.segments?structuredClone(row.segments):null,revision=row.revision;
  row.saveStatus='saving';manuscriptBadge(manuscriptKey(data,index),row);
  entry.promise=(async()=>{
    try{
      const value=await api(manuscriptPath(data,index)+'/manuscript',{method:'PUT',body:JSON.stringify({base_revision:revision,text:sent,segments})});
      if(row.text===sent)acceptManuscript(data,index,value);
      else{row.revision=value.revision;row.persistedText=value.text;row.dirty=true;row.saveStatus='pending';narrationDrafts.save(data.job,data.batch,data.rows);}
    }catch(e){row.saveStatus=e.message.includes('其他窗口')?'conflict':'error';row.failedText=row.text;narrationDrafts.save(data.job,data.batch,data.rows);manuscriptBadge(manuscriptKey(data,index),row);throw e;}
  })();
  try{await entry.promise;}finally{entry.promise=null;}
  if(row.dirty&&!['conflict','error'].includes(row.saveStatus))return persistNarration(entry);
}
async function flushNarrations(data=null){
  if(data)queueNarrationSaves(data);
  const entries=[...manuscriptWrites.values()].filter(e=>!data||(e.data.job.id===data.job.id&&e.data.batch.id===data.batch.id));
  for(const entry of entries)await persistNarration(entry);
}
window.addEventListener('beforeunload',e=>{if([...manuscriptWrites.values()].some(x=>x.data.rows[x.index].dirty)){e.preventDefault();e.returnValue='';}});

function changedFragment(before,after){
  const a=Array.from(before),b=Array.from(after);let start=0,end=0;
  while(start<a.length&&start<b.length&&a[start]===b[start])start++;
  while(end<a.length-start&&end<b.length-start&&a[a.length-1-end]===b[b.length-1-end])end++;
  const fragment=document.createDocumentFragment();fragment.append(b.slice(0,start).join(''));
  const removed=document.createElement('del');removed.textContent=a.slice(start,a.length-end).join('');
  const added=document.createElement('mark');added.textContent=b.slice(start,b.length-end).join('');
  fragment.append(removed,added,b.slice(b.length-end).join(''));return fragment;
}
function addComparison(info){
  const {data,row,index,content,editor,text,refresh}=info,reference=data.batch.reference||info.variant.segments;
  editor.hidden=true;text.hidden=true;
  const wrap=document.createElement('div');wrap.className='script-comparison';content.prepend(wrap);
  const parts=row.segments||((row.text.split(/\n\s*\n/).length===reference.length)?reference.map((s,i)=>({...s,text:row.text.split(/\n\s*\n/)[i]})):null);
  if(!parts){
    const note=document.createElement('p');note.className='notice';note.textContent=`这个自由编辑稿的段数已变化，暂不能逐段对齐。请在「完整文案」用空行整理为 ${reference.length} 段，或从版本记录恢复分段稿。`;wrap.append(note);
    const whole=document.createElement('div');whole.className='compare-pair';const a=document.createElement('p'),b=document.createElement('p');a.textContent=reference.map(s=>s.text).join('\n\n');b.textContent=row.text;whole.append(a,b);wrap.append(whole);return;
  }
  row.segments=structuredClone(parts);
  reference.forEach((source,i)=>{
    const section=document.createElement('section');section.className='compare-segment';
    const label=document.createElement('h4');label.textContent=`${String(i+1).padStart(2,'0')} · ${source.role}`;
    const pair=document.createElement('div');pair.className='compare-pair';
    const original=document.createElement('div');original.className='compare-original';
    const originalLabel=document.createElement('small');originalLabel.textContent='参考原段';const p=document.createElement('p');p.textContent=source.text;original.append(originalLabel,p);
    const target=document.createElement('div');target.className='compare-current';const targetLabel=document.createElement('label');targetLabel.textContent='当前成稿 · 可编辑';
    const input=document.createElement('textarea');input.className='compare-editor';input.value=parts[i].text;input.rows=Math.min(9,Math.max(3,Math.ceil(parts[i].text.length/22)));input.maxLength=20000;input.setAttribute('aria-label',`第 ${index+1} 条第 ${i+1} 段 ${source.role}`);
    const diff=document.createElement('p');diff.className='compare-diff';diff.setAttribute('aria-label','变化预览');diff.append(changedFragment(source.text,input.value));
    target.append(targetLabel,input,diff);pair.append(original,target);section.append(label,pair);wrap.append(section);
    input.oninput=()=>{row.segments[i].text=input.value;row.text=row.segments.map(s=>s.text).join('\n\n');editor.value=row.text;text.textContent=row.text;diff.replaceChildren(changedFragment(source.text,input.value));refresh();saveNarrations(data);updateNarrationActions(data);};
  });
}
function enhanceNarrationCard(info){
  const {data,row,index,heading,content}=info;
  const status=document.createElement('span');status.className='manuscript-status';status.dataset.manuscriptKey=manuscriptKey(data,index);info.card.append(status);manuscriptBadge(status.dataset.manuscriptKey,row);
  const versions=document.createElement('button');versions.className='quiet';versions.textContent='版本记录';versions.onclick=()=>openVersions(info);
  const rewrite=document.createElement('button');rewrite.className='quiet script-rewrite';rewrite.textContent='重写这条';rewrite.onclick=()=>openRewrite(info);rewrite.disabled=busy(current);
  heading.append(versions,rewrite);
  if(info.variant.generation_focus){const p=document.createElement('p');p.className='script-direction hint';p.textContent=info.variant.generation_focus;content.prepend(p);}
  if(row.revision>0){const p=document.createElement('p');p.className='hint';p.textContent=(info.variant.manuscript?.note?'本版调整：'+info.variant.manuscript.note+'。':'')+'当前为保存后的成稿；生成原稿的分段与质检评分仍单独保留。';content.append(p);}
  if(info.view==='compare'){
    addComparison(info);
    for(const button of heading.querySelectorAll('button'))if(button.textContent==='修改')button.hidden=true;
  }
}
const compareTab=document.createElement('button');compareTab.dataset.resultView='compare';compareTab.setAttribute('role','tab');compareTab.setAttribute('aria-selected','false');compareTab.textContent='逐段对照';
document.querySelector('.narration-toolbar>p.hint').textContent='成稿自动保存到本机文件，并保留版本记录；浏览器仅暂存未完成的编辑。复制、TXT、Excel 与飞书使用当前成稿，分段结构与原稿 JSON 保留生成原稿。';
document.querySelector('.narration-view-row [role=tablist]').append(compareTab);
compareTab.onclick=()=>{if(current){narrationDrafts.projects.get(current.id).view='compare';renderResults(current);}};
function renderWorkspaceState(){document.querySelectorAll('.script-rewrite').forEach(b=>b.disabled=busy(current));}

async function openVersions(info){
  versionContext=info;$('manuscript-title').textContent=`第 ${info.index+1} 条 · 版本记录`;$('manuscript-message').textContent='正在读取本机版本…';$('manuscript-dialog').showModal();
  try{await flushNarrations(info.data);}catch(e){$('manuscript-message').textContent=e.message;}
  await loadVersions().catch(e=>$('manuscript-message').textContent=e.message);
}
async function loadVersions(){
  const c=versionContext,result=await api(manuscriptPath(c.data,c.index)+'/versions');if(versionContext!==c)return;
  c.serverRevision=result.current.revision;$('manuscript-version').replaceChildren();
  for(const version of result.versions){const option=document.createElement('option');option.value=version.revision;option.textContent=`v${version.revision} · ${versionKinds[version.kind]||'成稿'} · ${new Date(version.created*1000).toLocaleString('zh-CN')}${version.revision===c.serverRevision?' · 当前':''}`;$('manuscript-version').append(option);}
  $('manuscript-preview').value=result.current.text;
  if(!c.row.dirty)$('manuscript-message').textContent='已从本机文件读取，清除浏览器缓存后仍可找回。';
}
$('manuscript-close').onclick=()=>$('manuscript-dialog').close();
$('manuscript-version').onchange=async()=>{const c=versionContext,revision=$('manuscript-version').value;if(!c)return;try{const row=await api(manuscriptPath(c.data,c.index)+'/versions/'+revision);if(c===versionContext&&$('manuscript-version').value===revision)$('manuscript-preview').value=row.text;}catch(e){$('manuscript-message').textContent=e.message;}};
async function versionAction(restore){
  const c=versionContext;if(!c)return;const revision=Number($('manuscript-version').value);$('manuscript-restore').disabled=true;$('manuscript-save-local').disabled=true;$('manuscript-version').disabled=true;
  try{
    const latest=await api(manuscriptPath(c.data,c.index)+'/versions');
    const value=await api(manuscriptPath(c.data,c.index)+(restore?'/restore':'/manuscript'),{method:restore?'POST':'PUT',body:JSON.stringify(restore?{base_revision:latest.current.revision,revision}:{base_revision:latest.current.revision,text:c.row.text,segments:c.row.segments})});
    acceptManuscript(c.data,c.index,value);await loadVersions();$('manuscript-message').textContent=`已另存为 v${value.revision}，此前版本仍保留。`;if(current?.id===c.data.job.id)renderResults(current);
  }catch(e){$('manuscript-message').textContent=e.message;}finally{$('manuscript-restore').disabled=false;$('manuscript-save-local').disabled=false;$('manuscript-version').disabled=false;}
}
$('manuscript-restore').onclick=()=>versionAction(true);$('manuscript-save-local').onclick=()=>versionAction(false);
async function openRewrite(info){
  if(busy(current)){toast('当前参考正在处理中，请稍后重写。');return;}
  try{await flushNarrations(info.data);}catch(e){toast(e.message);return;}
  rewriteContext=info;$('rewrite-title').textContent=`重写第 ${info.index+1} 条`;
  const product=info.data.batch.product_snapshot;$('rewrite-context').textContent=product?`商品：${product.name} · 资料 v${product.version} · 成稿 v${info.row.revision}`:`使用本批次保存的商品资料 · 成稿 v${info.row.revision}`;
  $('rewrite-direction').value='';$('rewrite-message').textContent='';$('rewrite-dialog').showModal();
}
$('rewrite-close').onclick=()=>$('rewrite-dialog').close();
$('rewrite-submit').onclick=async()=>{
  const c=rewriteContext;if(!c)return;$('rewrite-submit').disabled=true;
  try{await api(manuscriptPath(c.data,c.index)+'/rewrite',{method:'POST',body:JSON.stringify({base_revision:c.row.revision,direction:$('rewrite-direction').value})});$('rewrite-dialog').close();if(current?.id===c.data.job.id)render(await api('/jobs/'+c.data.job.id));}
  catch(e){$('rewrite-message').textContent=e.message;}finally{$('rewrite-submit').disabled=false;}
};

function focusState(){const key=current?.id||'new';if(!focusDrafts.has(key))focusDrafts.set(key,{enabled:true,audience:'',scenario:'',tone:'自然口语',strength:'balanced',custom:{}});return focusDrafts.get(key);}
function captureFocus(){const f=focusState();for(const key of ['audience','scenario','tone','strength'])f[key]=$('focus-'+key).value;f.enabled=$('focus-enabled').checked;return f;}
function showFocus(){const f=focusState();for(const key of ['audience','scenario','tone','strength'])$('focus-'+key).value=f[key];$('focus-enabled').checked=f.enabled;}
for(const key of ['audience','scenario','tone','strength','enabled'])$('focus-'+key).addEventListener('input',captureFocus);
function generationOptions(){
  const focus=structuredClone(captureFocus()),count=Number($('count').value);focus.custom=Object.fromEntries(Object.entries(focus.custom).filter(([i])=>Number(i)<=count));
  const selected=productSelections.get((current?.id||'new')+':'+creationMode());
  return {focus,...(selected?{product_id:selected.id,product_version:selected.version}:{})};
}
async function renderFocusPlan(){
  const epoch=++focusEpoch,count=Number($('count').value);if(!Number.isSafeInteger(count)||count<1){toast('请先填写正整数条数。');return;}
  const focus=captureFocus(),result=await api('/drafts/plan',{method:'POST',body:JSON.stringify({count,focus,offset:focusOffset,limit:14})});if(epoch!==focusEpoch)return;
  $('focus-plan-list').replaceChildren();
  for(const item of result.items){const group=document.createElement('div');group.className='focus-plan-row';const label=document.createElement('label');label.textContent=`第 ${item.index} 条`;const field=document.createElement('textarea');field.rows=2;field.maxLength=500;field.value=item.label;field.setAttribute('aria-label',`第 ${item.index} 条表达方向`);field.oninput=()=>{if(field.value.trim())focus.custom[String(item.index)]=field.value;else delete focus.custom[String(item.index)];};const details=document.createElement('details'),summary=document.createElement('summary'),note=document.createElement('p');summary.textContent='查看本条执行要求';note.className='hint';note.textContent=item.direction||'不预分配方向，使用统一创作描述。';details.append(summary,note);group.append(label,field,details);$('focus-plan-list').append(group);}
  $('focus-page').textContent=`${focusOffset+1}–${Math.min(count,focusOffset+14)} / ${count} 条`;$('focus-prev').disabled=focusOffset===0;$('focus-next').disabled=focusOffset+14>=count;
}
$('focus-preview').onclick=async()=>{focusOffset=0;try{await renderFocusPlan();$('focus-dialog').showModal();}catch(e){toast(e.message);}};
$('focus-prev').onclick=async()=>{focusOffset=Math.max(0,focusOffset-14);try{await renderFocusPlan();}catch(e){toast(e.message);}};
$('focus-next').onclick=async()=>{focusOffset+=14;try{await renderFocusPlan();}catch(e){toast(e.message);}};
$('focus-close').onclick=$('focus-done').onclick=()=>$('focus-dialog').close();

const libraryFields=['name','aliases','facts','pending','forbidden','audience','tone','source'];
function productMaterial(p){return '商品：'+p.name+'\n已确认卖点：\n'+p.facts+(p.aliases?'\n专有名词：'+p.aliases:'');}
async function refreshProducts(){libraryProducts=await api('/products');renderLibraryList();if(current)renderProductLibrary(current);}
function renderProductLibrary(job){
  const key=job.id+':'+creationMode(),selected=productSelections.get(key),select=$('product-library-select');
  select.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent='使用当前参考 / 手动资料';select.append(empty);
  for(const p of libraryProducts){const option=document.createElement('option');option.value=p.id;option.textContent=`${p.name} · v${p.version}`;select.append(option);}
  select.value=selected?.id||'';$('product-library-note').textContent=selected?`已选择商品资料 v${selected.version}；生成批次会保留快照。`:'待确认信息不会自动加入生成资料。';showFocus();
}
function applyLibraryProduct(p){
  if(!current)return;productDrafts.edit(current,creationMode(),productMaterial(p));productSelections.set(current.id+':'+creationMode(),{id:p.id,version:p.version});
  const focus=focusState();if(p.audience)focus.audience=p.audience;if(p.tone&&[...$('focus-tone').options].some(o=>o.value===p.tone))focus.tone=p.tone;renderProduct(current);
  if(typeof clearImportedProduct==='function')clearImportedProduct(current,creationMode());
}
$('product-library-select').onchange=()=>{const p=libraryProducts.find(p=>p.id===$('product-library-select').value);if(p)applyLibraryProduct(p);else{productSelections.delete(current.id+':'+creationMode());renderProductLibrary(current);}};
$('product-facts').addEventListener('input',()=>{if(current){productSelections.delete(current.id+':'+creationMode());$('product-library-select').value='';$('product-library-note').textContent='已改为手动资料；商品库记录保持原样。';}});
$('restore-product').addEventListener('click',()=>{if(current){productSelections.delete(current.id+':'+creationMode());renderProductLibrary(current);}});
function fillLibrary(product=null){
  libraryEditing=product;for(const field of libraryFields)$('library-'+field).value=product?.[field]||'';
  $('library-confirmed').checked=false;$('library-message').textContent='';$('product-library-version').textContent=product?.id?`v${product.version} · ${new Date(product.updated*1000).toLocaleString('zh-CN')} · 保存后新增版本`:'新商品 · 保存前请核对资料';
  $('library-archive').hidden=!product?.id;$('library-submit').textContent=current?'保存并用于当前参考':'保存商品';
  const history=product?.history||[];$('library-history').hidden=!history.length;$('library-history-list').replaceChildren();
  for(const old of [...history].reverse()){const p=document.createElement('p');p.textContent=`v${old.version} · ${old.name}\n${old.facts}`;$('library-history-list').append(p);}
}
function renderLibraryList(){
  const q=$('product-library-search').value.trim().toLowerCase();$('product-library-list').replaceChildren();
  const shown=libraryProducts.filter(p=>(p.name+' '+p.aliases).toLowerCase().includes(q));
  for(const p of shown){const button=document.createElement('button');button.className='library-product';const title=document.createElement('strong');title.textContent=p.name;const small=document.createElement('small');small.textContent=`v${p.version} · ${p.facts.replace(/\n/g,' ').slice(0,50)}`;button.append(title,small);button.onclick=async()=>{try{fillLibrary(await api('/products/'+p.id));}catch(e){$('library-message').textContent=e.message;}};$('product-library-list').append(button);}
  if(!shown.length){const p=document.createElement('p');p.className='hint';p.textContent=q?'没有匹配商品。':'还没有商品，保存一份核对过的资料，之后即可重复使用。';$('product-library-list').append(p);}
}
async function openLibrary(fromReference=false){
  try{await refreshProducts();if(fromReference&&current){fillLibrary(ProductDrafts.libraryCandidate(current,creationMode(),$('product-facts').value));}
    else fillLibrary(libraryProducts[0]?await api('/products/'+libraryProducts[0].id):null);$('product-library-dialog').showModal();}catch(e){toast(e.message);}
}
$('product-library-open').onclick=()=>openLibrary();$('product-library-save-current').onclick=()=>openLibrary(true);$('product-library-close').onclick=()=>$('product-library-dialog').close();$('product-library-new').onclick=()=>fillLibrary();$('product-library-search').oninput=renderLibraryList;
$('product-library-form').onsubmit=async e=>{
  e.preventDefault();$('library-submit').disabled=true;
  try{const body={confirmed:$('library-confirmed').checked,base_version:libraryEditing?.version||0};for(const key of libraryFields)body[key]=$('library-'+key).value;
    const saved=await api('/products'+(libraryEditing?.id?'/'+libraryEditing.id:''),{method:libraryEditing?.id?'PUT':'POST',body:JSON.stringify(body)});await refreshProducts();fillLibrary(saved);if(current)applyLibraryProduct(saved);$('library-message').textContent=`已保存商品 v${saved.version}${current?'，并用于当前参考。':'。'}`;
  }catch(e){$('library-message').textContent=e.message;}finally{$('library-submit').disabled=false;}
};
$('library-archive').onclick=async()=>{if(!libraryEditing?.id)return;try{await api('/products/'+libraryEditing.id,{method:'DELETE'});for(const [key,p] of productSelections)if(p.id===libraryEditing.id)productSelections.delete(key);await refreshProducts();fillLibrary();$('library-message').textContent='商品已归档，历史批次中的资料快照保留。';}catch(e){$('library-message').textContent=e.message;}};
refreshProducts().catch(e=>toast(e.message));
