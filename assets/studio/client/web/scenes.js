'use strict';
const sceneNames={transcript:'视频转文字',summary:'内容分析总结',breakdown:'爆款视频拆解',storyboard:'视频转脚本',generate:'爆款脚本生成',prompts:'视频提示词反推'};
const sceneDescriptions={transcript:'分段口播全文 · 带小标题与重点的净稿 · 分组屏幕文字 · 时间线合并稿',summary:'一句话主旨 · 结构章节 · 核心要点 · 金句 · 目标受众与 CTA',breakdown:'结构分段表 · 脚本类型 · 内容与留存设计假设 · 六维评分 · 可复用清单',storyboard:'按口播段落组织分镜，附屏幕文字、口播净稿；镜头、运镜、转场与情绪标为推断。',prompts:'整体风格提示词 · 分镜 prompt · 带停顿重音的 TTS 口播 · 结构化 JSON'};
let activeScene='transcript',sceneReportSignature='',sceneProjectId='';
const sceneDrafts=new Map();
const generationReferencePrefs=new Map();
let generationReferenceSignature='';
function referencePreference(job){return generationReferencePrefs.get(job.id)||{view:'corrected',expanded:false};}
function referenceDisplayText(job,view){
  if(view==='raw')return job.raw||'';
  if(view==='structure')return (job.structure||[]).map(s=>s.id+' · '+s.role+'\n'+s.text).join('\n\n');
  return job.corrected||job.raw||'';
}
function renderGenerationReference(job){
  $('generation-reference').hidden=activeScene!=='generate';
  if(activeScene!=='generate')return;
  const prefs=referencePreference(job),text=referenceDisplayText(job,prefs.view);
  $('generation-reference-body').hidden=!prefs.expanded;
  $('generation-reference-toggle').textContent=prefs.expanded?'收起':'展开';$('generation-reference-toggle').setAttribute('aria-expanded',String(prefs.expanded));
  $('generation-reference-copy').disabled=!text;
  $('generation-reference-meta').textContent=(prefs.view==='raw'?'原始转写':prefs.view==='structure'?'结构分段':'当前校对稿')+' · '+(prefs.view==='structure'?(job.structure?.length||0)+' 段':text.length+' 字');
  document.querySelectorAll('[data-reference-view]').forEach(b=>{const selected=b.dataset.referenceView===prefs.view;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected));});
  const signature=job.id+'|'+prefs.view+'|'+text;
  if(signature!==generationReferenceSignature){
    generationReferenceSignature=signature;$('generation-reference-text').textContent=text||(prefs.view==='structure'?'尚未拆分结构，可先在「视频转文字」中纠错并拆结构。':'转写完成后，参考文案会显示在这里。');
    $('generation-reference-text').scrollTop=0;
  }
}
for(const button of document.querySelectorAll('[data-reference-view]'))button.onclick=()=>{if(!current)return;generationReferencePrefs.set(current.id,{...referencePreference(current),view:button.dataset.referenceView});renderGenerationReference(current);};
$('generation-reference-toggle').onclick=()=>{if(!current)return;const prefs=referencePreference(current);generationReferencePrefs.set(current.id,{...prefs,expanded:!prefs.expanded});renderGenerationReference(current);};
$('generation-reference-copy').onclick=()=>{if(current)copyText(referenceDisplayText(current,referencePreference(current).view));};
function inlineReport(text){return escapeHTML(text).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');}
// Minimal safe Markdown renderer: only text, headings, tables, lists and code. Never insert model HTML.
function reportHTML(md){
  const lines=md.split('\n');let out='',table=false,code=false,codeLines=[];
  const closeTable=()=>{if(table){out+='</tbody></table></div>';table=false;}};
  for(const line of lines){
    if(line.startsWith('```')){closeTable();if(code){out+='<pre><code>'+escapeHTML(codeLines.join('\n'))+'</code></pre>';codeLines=[];}code=!code;continue;}
    if(code){codeLines.push(line);continue;}
    if(line.startsWith('|')){
      const cells=line.replace(/^\||\|$/g,'').split('|').map(s=>s.trim());
      if(cells.every(s=>/^:?-+:?$/.test(s)))continue;
      if(!table){out+='<div class="report-table"><table><thead><tr>'+cells.map(c=>'<th>'+inlineReport(c)+'</th>').join('')+'</tr></thead><tbody>';table=true;}
      else out+='<tr>'+cells.map(c=>'<td>'+inlineReport(c)+'</td>').join('')+'</tr>';
      continue;
    }
    closeTable();if(!line.trim())continue;
    const heading=line.match(/^(#{1,3}) (.*)/);
    if(heading)out+=`<h${heading[1].length+1}>${inlineReport(heading[2])}</h${heading[1].length+1}>`;
    else if(line.startsWith('> '))out+='<blockquote>'+inlineReport(line.slice(2))+'</blockquote>';
    else if(line.startsWith('- '))out+='<p class="report-bullet">• '+inlineReport(line.slice(2))+'</p>';
    else out+='<p>'+inlineReport(line)+'</p>';
  }
  closeTable();if(codeLines.length)out+='<pre>'+escapeHTML(codeLines.join('\n'))+'</pre>';return out;
}
function sceneSelect(scene){
  activeScene=scene;sceneReportSignature='';
  if(current)sceneDrafts.set(current.id,{scene,visual:$('visual-mode').value,vision:$('vision-provider-select').value});
  document.querySelectorAll('#scene-nav button').forEach(b=>{b.classList.toggle('active',b.dataset.scene===scene);b.setAttribute('aria-current',b.dataset.scene===scene?'page':'false');});
  document.querySelector('.transcript-panel').hidden=scene!=='transcript';
  document.querySelector('.generate-panel').hidden=scene!=='generate';
  $('generation-reference').hidden=scene!=='generate';
  $('results-section').hidden=scene!=='generate'||!current?.batches.length;
  $('scene-report-panel').hidden=scene==='generate'||current?.kind==='script';
  if(scene!=='generate'){$('scene-report-title').textContent=sceneNames[scene];$('scene-description').textContent=sceneDescriptions[scene];$('scene-run').textContent='生成'+sceneNames[scene];}
  if(current)renderSceneUI(current);
}
for(const b of document.querySelectorAll('#scene-nav button'))b.onclick=()=>sceneSelect(b.dataset.scene);
function visionOptions(){
  const select=$('vision-provider-select'),selected=select.value,signature=providerCatalog.map(p=>p.id+p.model+p.has_key).join();
  if(select.dataset.signature===signature)return;
  select.dataset.signature=signature;select.replaceChildren(new Option('请选择支持图片输入的模型',''));
  for(const p of providerCatalog.filter(p=>p.has_key))select.append(new Option(p.name+' · '+p.model,p.id));
  select.value=selected;
}
function visualHint(){
  const mode=$('visual-mode').value;$('vision-provider-field').hidden=mode!=='vision';visionOptions();
  $('visual-mode-hint').textContent=mode==='vision'?'将最多 12 张抽样画面发送到所选服务商，请选择支持图片输入的模型；文字服务商继续用于报告写作。':mode==='cue'?'仅向 Cue 发送当前公开分享链接，可能消耗积分；本机已有解析会复用。':'本机识别抽样屏幕文字，不上传画面。人物、动作与构图未识别时会明确注明，拍摄建议标为推断。';
}
$('visual-mode').onchange=()=>{visualHint();if(current)sceneDrafts.set(current.id,{scene:activeScene,visual:$('visual-mode').value,vision:$('vision-provider-select').value});};
$('vision-provider-select').onchange=()=>{if(current)sceneDrafts.set(current.id,{scene:activeScene,visual:$('visual-mode').value,vision:$('vision-provider-select').value});};
function renderSceneUI(job){
  if(sceneProjectId!==job.id){
    sceneProjectId=job.id;sceneReportSignature='';const draft=sceneDrafts.get(job.id);
    activeScene=draft?.scene||(job.kind==='script'?'generate':'transcript');$('visual-mode').value=draft?.visual||'local';visionOptions();$('vision-provider-select').value=draft?.vision||'';visualHint();sceneSelect(activeScene);return;
  }
  const working=busy(job),report=job.reports?.[activeScene];
  renderGenerationReference(job);
  if(typeof renderTranscriptPreview==='function')renderTranscriptPreview(job);
  $('scene-run').disabled=working||!job.corrected;$('scene-run-all').disabled=working||!job.corrected;$('original-generate').disabled=working||!job.corrected;
  for(const b of document.querySelectorAll('#scene-nav button')){const done=b.dataset.scene==='generate'?job.batches.length:job.reports?.[b.dataset.scene];b.classList.toggle('has-result',!!done);}
  $('results-section').hidden=activeScene!=='generate'||!job.batches.length;
  $('scene-copy').hidden=!report;$('scene-export-md').hidden=!report;$('scene-export-json').hidden=!report;
  $('scene-report-empty').hidden=!!report;$('scene-report-body').hidden=!report;
  $('scene-report-empty').textContent=working&&job.operation==='report'?job.message:'点击生成，查看'+sceneNames[activeScene]+'。结果按当前参考独立保存。';
  $('report-stale').hidden=!report||report.segments.map(s=>s.text).join('').replace(/\s/g,'')===job.corrected.replace(/\s/g,'');
  if(report){
    $('report-provider-label').textContent=report.ai_provider.name+' · '+({local:'本机 OCR',cue:'Cue',vision:'视觉模型'}[report.visual_mode])+' · '+new Date(report.created*1000).toLocaleString('zh-CN');
    const signature=job.id+activeScene+report.created;
    if(signature!==sceneReportSignature){sceneReportSignature=signature;$('scene-report-body').innerHTML=reportHTML(report.markdown);$('report-options').open=false;if(activeScene==='transcript')$('transcript-editor').open=false;}
    $('scene-export-md').href=`/api/jobs/${job.id}/reports/${activeScene}/export?format=md`;$('scene-export-json').href=`/api/jobs/${job.id}/reports/${activeScene}/export?format=json`;
  }else{$('report-provider-label').textContent='';sceneReportSignature='';$('report-options').open=true;}
  const frames=job.evidence?.frames||[];$('frame-evidence').hidden=!frames.length;
  const signature=job.id+':'+frames.length;
  if($('frame-gallery').dataset.signature!==signature){
    $('frame-gallery').dataset.signature=signature;$('frame-gallery').replaceChildren();
    for(const f of frames){const figure=document.createElement('figure');const img=document.createElement('img');img.src=`/api/jobs/${job.id}/frames/${f.id}`;img.loading='lazy';img.alt='抽样画面 '+f.time+' 秒';const caption=document.createElement('figcaption');caption.textContent=f.time+' 秒 · '+f.ocr.map(x=>x.text).join(' / ');figure.append(img,caption);$('frame-gallery').append(figure);}
  }
}
async function startReport(scene){
  if(!current||busy(current))return;
  try{await api('/jobs/'+current.id+'/reports/run',{method:'POST',body:JSON.stringify({scene,visual_mode:$('visual-mode').value,vision_provider_id:$('vision-provider-select').value,reference_text:$('transcript').value})});await selectJob(current.id);}catch(e){toast(e.message);}
}
$('scene-run').onclick=()=>startReport(activeScene);$('scene-run-all').onclick=()=>startReport('all');
$('scene-copy').onclick=()=>copyText(current?.reports?.[activeScene]?.markdown||'');
$('original-generate').onclick=async()=>{
  if(!current||busy(current))return;const count=Number($('count').value),duration=Number($('original-duration').value);
  if(!Number.isSafeInteger(count)||count<1||!Number.isInteger(duration)||duration<10||duration>1800){toast('条数需为正整数，时长需为 10–1800 秒。');return;}
  try{await api('/jobs/'+current.id+'/drafts/generate',{method:'POST',body:JSON.stringify({mode:'original',facts:$('product-facts').value,count,direction:$('direction').value,reference_text:$('transcript').value,quality_check:$('quality-check').checked,target_duration:duration,purpose:$('original-purpose').value,audience:$('original-audience').value,...(typeof generationOptions==='function'?generationOptions():{})})});await selectJob(current.id);}catch(e){toast(e.message);}
};
async function refreshCue(){const state=await api('/cue/settings');providerStatus('provider-cue-status',state.has_key);$('cue-import').hidden=!state.existing_available||state.has_key;}
$('cue-manage').onclick=()=>$('cue-config-panel').hidden=!$('cue-config-panel').hidden;
async function saveCue(extra={}){try{await api('/cue/settings',{method:'PUT',body:JSON.stringify({key:$('cue-key').value,...extra})});$('cue-key').value='';await refreshCue();toast('Cue 配置已保存。');}catch(e){toast(e.message);}}
$('cue-save').onclick=()=>saveCue();$('cue-import').onclick=()=>saveCue({import_existing:true});$('cue-clear').onclick=()=>saveCue({clear_key:true});
const priorSettingsOpen=$('settings-open').onclick;$('settings-open').onclick=async()=>{await priorSettingsOpen();await refreshCue();};
function filterProviders(){const query=$('settings-search').value.trim().toLowerCase();document.querySelectorAll('#settings-providers-pane .provider-card').forEach(card=>card.hidden=!!query&&!card.textContent.toLowerCase().includes(query));}
$('settings-search').oninput=()=>{setSettingsTab('providers');filterProviders();};
visualHint();
