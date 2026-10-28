'use strict';
const materialStates=new Map(),materialDraftQueues=new Map(),materialDraftTimers=new Map();
let materialContext=null,materialOpenEpoch=0;
const materialKey=(job,mode)=>job.id+':'+mode;
const materialBusy=s=>s.submitting||['queued','working'].includes(s.record?.status);
function materialState(job,mode,kind){
  const key=materialKey(job,mode)+':'+kind;
  if(!materialStates.has(key))materialStates.set(key,{key,jobId:job.id,mode,kind,text:'',files:[],urls:[],record:null,reviewText:null,submitting:false,timer:null});
  return materialStates.get(key);
}
function showMaterial(){
  const s=materialContext;if(!s)return;const busy=materialBusy(s),images=s.kind==='images',isDocument=s.kind==='document';
  $('material-title').textContent=isDocument?'从商品文档提取':images?'从商品图片提取':'从商品文案提取';
  $('material-context').textContent=`填入${s.mode==='switch'?'目标':'当前'}商品资料 · 只读取你在这里提供的内容，不混入参考视频。`;
  $('material-image-area').hidden=!images;$('material-text-area').hidden=s.kind!=='text';$('material-document-area').hidden=!isDocument;
  for(const [id,kind] of [['image','images'],['text','text'],['document','document']]){$('material-'+id+'-tab').setAttribute('aria-selected',String(s.kind===kind));$('material-'+id+'-tab').disabled=busy;}
  $('material-document-file').disabled=busy;$('material-document-name').textContent=s.document?.name||s.record?.document_name||'点击选择，或拖入文档';
  $('material-source-text').readOnly=busy;$('material-files').disabled=busy;
  $('material-run').disabled=busy||(isDocument?!s.document:images?!s.files.length:!s.text.trim());$('material-run').textContent=busy?'正在提取…':'开始提取';
  $('material-progress').textContent=s.record?.error||s.record?.message||'';
  $('material-progress').classList.toggle('save-warning',s.record?.status==='error');
  const configured=providerCatalog.find(p=>p.id===activeAiProviderId),used=s.record?.provider;
  $('material-provider').textContent=used?.name?'本次使用：'+used.name+' · '+used.model:configured?'文字整理：'+configured.name+' · '+configured.model:'请先在设置中配置文字服务商。';
  const done=s.record?.status==='done';$('material-result').hidden=!done;
  if(done){
    if(s.reviewText===null)s.reviewText=s.record.facts||'';
    $('material-facts-preview').value=s.reviewText;
    const pending=s.record.profile?.needs_confirmation||[];$('material-pending').hidden=!pending.length;$('material-pending-list').replaceChildren();
    for(const fact of pending){const p=document.createElement('p');p.textContent=fact.value;const quote=document.createElement('small');quote.textContent='来源：'+fact.source_excerpt;p.append(document.createElement('br'),quote);$('material-pending-list').append(p);}
    $('material-evidence-title').textContent=isDocument?'查看文档正文':images?'查看本机识别的图片文字':'查看输入的商品文案';$('material-evidence').value=s.record.source_text||'';
    $('material-apply').disabled=!s.reviewText.trim();$('material-apply').textContent='核对并填入'+(s.mode==='switch'?'目标':'当前')+'商品资料';
  }
  $('material-thumbnails').replaceChildren();
  s.files.forEach((file,index)=>{const wrap=document.createElement('div');wrap.className='material-thumbnail';const image=document.createElement('img');image.src=s.urls[index];image.alt=`第 ${index+1} 张商品图片`;
    const label=document.createElement('span');label.textContent=file.name;label.title=file.name;
    const remove=document.createElement('button');remove.className='quiet';remove.textContent='移除';remove.disabled=busy;remove.setAttribute('aria-label',`移除第 ${index+1} 张商品图片`);
    remove.onclick=()=>{URL.revokeObjectURL(s.urls[index]);s.urls.splice(index,1);s.files.splice(index,1);s.record=null;s.reviewText=null;showMaterial();};wrap.append(image,label,remove);$('material-thumbnails').append(wrap);});
}
async function openMaterial(kind,context=null){
  if(!current){toast('请先选择一条参考。');return;}
  const epoch=++materialOpenEpoch,mode=context?.mode||creationMode(),job=context?.job||current;
  if(materialContext)clearTimeout(materialContext.timer);
  const s=materialState(job,mode,kind);materialContext=s;$('material-source-text').value=s.text;
  showMaterial();if(!$('material-dialog').open)$('material-dialog').showModal();
  if(s.record){if(materialBusy(s))pollMaterial(s);return;}
  try{const rows=await api('/jobs/'+job.id+'/product-imports?mode='+mode);
    if(epoch!==materialOpenEpoch||materialContext!==s)return;
    const latest=rows.find(r=>r.kind===kind);
    if(latest&&!s.files.length&&!s.text.trim()&&!s.document){s.record=latest;s.reviewText=null;if(kind==='text'){s.text=latest.source_text||'';$('material-source-text').value=s.text;}showMaterial();if(materialBusy(s))pollMaterial(s);}
  }catch(e){if(materialContext===s)$('material-progress').textContent=e.message;}
}
function addMaterialImages(files){
  const s=materialContext;if(!s||materialBusy(s))return;
  const incoming=[...files].filter(f=>!s.files.some(old=>old.name===f.name&&old.size===f.size&&old.lastModified===f.lastModified));
  if(!incoming.length)return;
  if(incoming.some(f=>!['image/png','image/jpeg','image/webp'].includes(f.type)&&!(/\.(png|jpe?g|webp)$/i.test(f.name)))){toast('请选择 PNG、JPG 或 WebP 图片。');return;}
  if(s.files.length+incoming.length>5){toast('每次最多提取 5 张图片。');return;}
  if(incoming.some(f=>f.size>12*1024*1024)||[...s.files,...incoming].reduce((sum,f)=>sum+f.size,0)>30*1024*1024){toast('单张最多 12 MB，每次合计最多 30 MB。');return;}
  s.files.push(...incoming);s.urls.push(...incoming.map(f=>URL.createObjectURL(f)));s.record=null;s.reviewText=null;showMaterial();
}
async function pollMaterial(s){
  clearTimeout(s.timer);if(materialContext!==s||!$('material-dialog').open||!s.record)return;
  try{s.record=await api(`/jobs/${s.jobId}/product-imports/${s.record.id}`);if(materialContext!==s||!$('material-dialog').open)return;showMaterial();if(materialBusy(s))s.timer=setTimeout(()=>pollMaterial(s),1000);}
  catch(e){if(materialContext===s)$('material-progress').textContent=e.message;}
}
$('material-image-open').onclick=()=>openMaterial('images');$('material-text-open').onclick=()=>openMaterial('text');
$('material-image-tab').onclick=()=>openMaterial('images');$('material-text-tab').onclick=()=>openMaterial('text');
$('material-document-tab').onclick=()=>openMaterial('document');
function addMaterialDocument(file){
  const s=materialContext;if(!file||!s||materialBusy(s))return;
  if(!/\.(docx|pdf|txt)$/i.test(file.name)||file.size>20*1024*1024){toast('请选择 20 MB 内的 DOCX、PDF 或 TXT 文档。');return;}
  s.document=file;s.record=null;s.reviewText=null;showMaterial();
}
$('material-document-drop').onclick=()=>{if(materialContext&&!materialBusy(materialContext))$('material-document-file').click();};
$('material-document-drop').onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();$('material-document-drop').click();}};
$('material-document-file').onchange=()=>{addMaterialDocument($('material-document-file').files[0]);$('material-document-file').value='';};
$('material-document-drop').ondragover=e=>e.preventDefault();$('material-document-drop').ondrop=e=>{e.preventDefault();addMaterialDocument(e.dataTransfer.files[0]);};
$('material-close').onclick=()=>$('material-dialog').close();$('material-dialog').addEventListener('close',()=>{if(materialContext)clearTimeout(materialContext.timer);});
$('material-drop').onclick=()=>{if(!materialBusy(materialContext))$('material-files').click();};
$('material-drop').onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();$('material-drop').click();}};
$('material-files').onchange=()=>{addMaterialImages($('material-files').files);$('material-files').value='';};
$('material-drop').ondragover=e=>{e.preventDefault();};$('material-drop').ondrop=e=>{e.preventDefault();addMaterialImages(e.dataTransfer.files);};
$('material-dialog').addEventListener('paste',e=>{if(materialContext?.kind!=='images')return;const files=[...(e.clipboardData?.items||[])].filter(item=>item.kind==='file'&&item.type.startsWith('image/')).map(item=>item.getAsFile()).filter(Boolean);if(files.length){e.preventDefault();addMaterialImages(files);}});
$('material-source-text').oninput=()=>{const s=materialContext;if(!s)return;s.text=$('material-source-text').value;s.record=null;s.reviewText=null;$('material-result').hidden=true;$('material-run').disabled=!s.text.trim();};
$('material-facts-preview').oninput=()=>{if(materialContext){materialContext.reviewText=$('material-facts-preview').value;$('material-apply').disabled=!materialContext.reviewText.trim();}};
$('material-run').onclick=async()=>{
  const s=materialContext;if(!s||materialBusy(s))return;s.submitting=true;s.record=null;s.reviewText=null;showMaterial();
  try{
    if(s.kind==='images'){const form=new FormData();form.append('mode',s.mode);s.files.forEach(file=>form.append('files',file));s.record=await api(`/jobs/${s.jobId}/product-imports/images`,{method:'POST',body:form});}
    else if(s.kind==='document'){const form=new FormData();form.append('mode',s.mode);form.append('file',s.document);s.record=await api(`/jobs/${s.jobId}/product-imports/document`,{method:'POST',body:form});}
    else s.record=await api(`/jobs/${s.jobId}/product-imports/text`,{method:'POST',body:JSON.stringify({mode:s.mode,text:s.text})});
    s.submitting=false;if(materialContext===s){showMaterial();pollMaterial(s);}
  }catch(e){s.submitting=false;if(materialContext===s){showMaterial();$('material-progress').textContent=e.message;}}
};
function persistMaterialDraft(job,mode,text,sourceId,active=true){
  const key=materialKey(job,mode);clearTimeout(materialDraftTimers.get(key));
  const previous=materialDraftQueues.get(key)||Promise.resolve();
  const request=previous.catch(()=>{}).then(()=>api('/jobs/'+job.id+'/product-material',{method:'PUT',body:JSON.stringify({mode,text,source_id:sourceId,active})})).then(drafts=>{
    job.material_drafts=drafts;if(current?.id===job.id)current.material_drafts=drafts;return drafts;
  });materialDraftQueues.set(key,request);return request;
}
async function clearImportedProduct(job,mode){
  const draft=job.material_drafts?.[mode];if(!draft?.active)return;
  draft.active=false;renderProduct(job);
  try{await persistMaterialDraft(job,mode,'','',false);}catch(e){toast('商品资料来源更新未完成：'+e.message);}
}
$('material-apply').onclick=async()=>{
  const s=materialContext;if(!s?.record||s.record.status!=='done')return;
  if(current?.id!==s.jobId||creationMode()!==s.mode){$('material-progress').textContent='当前参考或模式已切换，请回到原参考及模式后再使用。';return;}
  const text=$('material-facts-preview').value.trim();if(!text)return;$('material-apply').disabled=true;
  try{await persistMaterialDraft(current,s.mode,text,s.record.id);productDrafts.edit(current,s.mode,text);
    productSelections.delete(materialKey(current,s.mode));renderProduct(current);$('material-dialog').close();toast('已填入'+(s.mode==='switch'?'目标':'当前')+'商品资料，可继续编辑或存入商品库。');
  }catch(e){$('material-progress').textContent=e.message;}finally{$('material-apply').disabled=false;}
};
function renderProductMaterial(job){
  const mode=creationMode();$('product-facts').placeholder=mode==='switch'?'输入你的目标商品资料，或从图片、商品文案中提取。':'可使用参考视频资料，也可以从自己的图片、商品文案中提取。';
  const applied=job.material_drafts?.[mode];if(!applied?.active)return;
  $('product-hint').textContent=`已从你提供的商品${({images:'图片',text:'文案',document:'文档'}[applied.kind]||'资料')}提取并保存，当前模式单独使用；可继续编辑或存入商品库。`;
  const pending=applied.profile?.needs_confirmation||[];$('product-review').hidden=!pending.length;
  $('product-review-summary').textContent=`自己的商品资料 · ${pending.length} 项待核对（未自动加入卖点）`;$('product-review-list').replaceChildren();
  for(const fact of pending){const p=document.createElement('p');p.textContent=fact.value+'\n来源：'+fact.source_excerpt;$('product-review-list').append(p);}
}
$('product-facts').addEventListener('input',()=>{
  const job=current,mode=creationMode(),draft=job?.material_drafts?.[mode];if(!draft?.active)return;
  const text=$('product-facts').value,sourceId=draft.source_id,key=materialKey(job,mode);draft.text=text;clearTimeout(materialDraftTimers.get(key));
  if(text.trim())materialDraftTimers.set(key,setTimeout(()=>persistMaterialDraft(job,mode,text,sourceId).catch(e=>toast('商品资料未保存：'+e.message)),600));
});
$('restore-product').addEventListener('click',()=>{if(current)clearImportedProduct(current,creationMode());});
if(current)renderProductMaterial(current);
