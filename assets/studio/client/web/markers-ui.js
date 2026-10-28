'use strict';
let markerProject='',markerSignature='',markerFilter='all',markerLimit=30;
const inspectionDrafts=new Map();
const markerLabels={silence:'静音区间',repeat:'相似口播',scene:'画面切换'};
function markerClock(t){const v=Math.round(Math.max(0,Number(t)||0)*10)/10;return String(Math.floor(v/60)).padStart(2,'0')+':'+(v%60).toFixed(1).padStart(4,'0');}
function syncDrawerAccess(){
  $('review-sidebar').inert=window.innerWidth<1480&&!document.body.classList.contains('review-open');
  $('reference-sidebar').inert=false;
}
function closeWorkspaceDrawers(){document.body.classList.remove('review-open');$('workspace-scrim').hidden=true;$('detection-open').setAttribute('aria-expanded','false');syncDrawerAccess();}
function openInspection(){
  closeWorkspaceDrawers();
  if(window.matchMedia('(min-width:1480px)').matches){$('review-sidebar').scrollTo({top:0,behavior:'smooth'});$('markers-run').focus({preventScroll:true});return;}
  document.body.classList.add('review-open');$('workspace-scrim').hidden=false;$('detection-open').setAttribute('aria-expanded','true');syncDrawerAccess();$('review-close').focus();
}
$('detection-open').onclick=openInspection;$('review-close').onclick=closeWorkspaceDrawers;
$('workspace-scrim').onclick=closeWorkspaceDrawers;
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('settings-dialog').open)closeWorkspaceDrawers();});
window.addEventListener('resize',syncDrawerAccess);
$('sidebar-import').onclick=()=>{startNewReference();const sidebar=$('reference-sidebar');sidebar.scrollTo({top:$('import-details').offsetTop-sidebar.offsetTop,behavior:'smooth'});};
function saveInspectionDraft(){if(current)inspectionDrafts.set(current.id,{filter:markerFilter,decision:$('marker-decision-filter').value,
  settings:{silence_db:$('silence-db').value,silence_seconds:$('silence-seconds').value,repeat_similarity:$('repeat-similarity').value,scene_threshold:$('scene-threshold').value}});}
for(const id of ['silence-db','silence-seconds','repeat-similarity','scene-threshold'])$(id).oninput=saveInspectionDraft;
function setMarkerFilter(filter){markerFilter=filter;markerLimit=30;markerSignature='';saveInspectionDraft();if(current)renderMarkerUI(current);}
document.querySelectorAll('[data-marker-filter]').forEach(b=>b.onclick=()=>setMarkerFilter(markerFilter===b.dataset.markerFilter?'all':b.dataset.markerFilter));
$('marker-all').onclick=()=>setMarkerFilter('all');$('marker-decision-filter').onchange=()=>{markerLimit=30;markerSignature='';saveInspectionDraft();if(current)renderMarkerUI(current);};
function resetMarkerUI(){
  $('review-sidebar').hidden=true;markerProject='';markerSignature='';
  document.body.classList.remove('has-reference');closeWorkspaceDrawers();
  const player=$('reference-player');player.pause();player.removeAttribute('src');player.load();
}
function locateReference(second){
  if(!current)return;const player=$('reference-player');$('marker-preview').open=true;$('preview-position').textContent=markerClock(second);
  const src='/api/jobs/'+current.id+'/reference/media';
  const seek=()=>{player.currentTime=Math.min(Math.max(0,second),Number.isFinite(player.duration)?Math.max(0,player.duration-.01):second);};
  if(player.getAttribute('src')!==src){player.src=src;player.load();player.addEventListener('loadedmetadata',seek,{once:true});}
  else if(player.readyState>=1)seek();else player.addEventListener('loadedmetadata',seek,{once:true});
  $('marker-preview').scrollIntoView({block:'nearest',behavior:'smooth'});
}
function timeButton(text,second){const button=document.createElement('button');button.className='time-button';button.textContent=text;button.onclick=()=>locateReference(second);return button;}
async function decideMarker(id,decision){
  if(!current||busy(current))return;const project=current.id;
  try{await api(`/jobs/${project}/markers/${id}/decision`,{method:'PUT',body:JSON.stringify({decision})});const job=await api('/jobs/'+project);if(currentId===project){markerSignature='';render(job);}}catch(e){toast(e.message);}
}
function markerCard(m,result){
  const card=document.createElement('article');card.className='marker-card';card.dataset.markerId=m.id;
  const decision=result.decisions?.[m.id]||'pending';
  const head=document.createElement('div');head.className='marker-card-head';head.innerHTML=`<span class="marker-type ${m.kind}">${markerLabels[m.kind]}</span><span class="marker-status ${decision}">${{pending:'待查看',keep:'已标保留',reviewed:'已查看'}[decision]}</span>`;card.append(head);
  if(m.kind==='repeat'){
    card.append(timeButton('首次 '+markerClock(m.original.start)+' →',m.original.start));
    const first=document.createElement('div');first.className='marker-quote';first.textContent=m.original.text;card.append(first);
    card.append(timeButton('再次 '+markerClock(m.repeated.start)+' →',m.repeated.start));
    const second=document.createElement('div');second.className='marker-quote';second.textContent=m.repeated.text;card.append(second);
    const score=document.createElement('p');score.textContent=`文字相似度 ${m.similarity}% · 可能是刻意强调`;card.append(score);
  }else card.append(timeButton(markerClock(m.start)+(m.end>m.start?'–'+markerClock(m.end):'')+' →',m.start));
  const reason=document.createElement('p');reason.textContent=m.kind==='silence'?`持续 ${m.duration.toFixed(1)} 秒，低于 ${result.settings.silence_db} dB。`+m.reason:m.reason;card.append(reason);
  const suggestion=document.createElement('p');suggestion.className='marker-suggestion';suggestion.textContent='建议：'+m.suggestion;card.append(suggestion);
  const actions=document.createElement('div');actions.className='marker-card-actions';
  for(const [value,label] of [['keep','保留'],['reviewed','已查看'],['pending','待查看']]){const b=document.createElement('button');b.textContent=label;b.classList.toggle('active',decision===value);b.disabled=busy(current);b.onclick=()=>decideMarker(m.id,value);actions.append(b);}
  card.append(actions);return card;
}
function renderMarkerUI(job){
  document.body.classList.add('has-reference');$('review-sidebar').hidden=false;
  const result=job.markers,working=busy(job),detecting=working&&job.operation==='markers';
  if(markerProject!==job.id){
    markerProject=job.id;markerSignature='';markerLimit=30;const draft=inspectionDrafts.get(job.id),settings=draft?.settings||result?.settings||{};
    markerFilter=draft?.filter||'all';$('marker-decision-filter').value=draft?.decision||'all';
    for(const [key,id,defaultValue] of [['silence_db','silence-db',-35],['silence_seconds','silence-seconds',.6],['repeat_similarity','repeat-similarity',88],['scene_threshold','scene-threshold',3]])$(id).value=settings[key]??defaultValue;
    $('transcript-editor').open=!job.reports?.transcript;const player=$('reference-player');player.pause();player.removeAttribute('src');player.load();$('marker-preview').open=false;
    syncDrawerAccess();
  }
  $('job-metadata').textContent=[job.kind==='script'?'脚本原文':job.kind==='link'?'链接参考':'本地参考',job.duration?markerClock(job.duration):'',job.structure?.length?job.structure.length+' 段原结构':''].filter(Boolean).join(' · ');
  $('markers-run').disabled=working||!job.input_file;$('markers-run').innerHTML=(detecting?'正在本机检测…':result?'重新检测':'开始本机检测')+' <span>↗</span>';
  $('marker-progress').textContent=detecting?job.message:result?'已完成 · '+new Date(result.created*1000).toLocaleString('zh-CN')+' · 仅做标记':'三项检测均在本机完成，无需 AI 额度。';
  const warnings=[...(result?.warnings||[]),...(job.marker_warning?[job.marker_warning]:[])];$('marker-warning').hidden=!warnings.length;$('marker-warning').textContent=warnings.join('\n');
  $('marker-results-area').hidden=!result;$('marker-empty').hidden=!!result;
  for(const [field,id] of [['silences','silence-count'],['repeats','repeat-count'],['cuts','cut-count']])$(id).textContent=result?.statuses[field]==='done'?result[field].length:'—';
  const all=result?[...result.silences,...result.repeats,...result.cuts].sort((a,b)=>a.start-b.start):[];
  $('detection-count').textContent=result?all.length:'';
  document.querySelectorAll('[data-marker-filter]').forEach(b=>{b.classList.toggle('active',markerFilter===b.dataset.markerFilter);b.setAttribute('aria-pressed',String(markerFilter===b.dataset.markerFilter));});
  if(!result)return;
  $('marker-duration').textContent=markerClock(result.duration);$('marker-export-md').href=`/api/jobs/${job.id}/markers/export?format=md`;$('marker-export-json').href=`/api/jobs/${job.id}/markers/export?format=json`;
  const signature=job.id+':'+result.created+':'+JSON.stringify(result.decisions)+':'+markerFilter+':'+$('marker-decision-filter').value+':'+markerLimit+':'+working;
  if(signature===markerSignature)return;markerSignature=signature;
  $('marker-timeline').replaceChildren();
  for(const m of all){const b=document.createElement('button');b.className='timeline-mark '+m.kind;b.style.left=Math.min(99.3,100*m.start/Math.max(1,result.duration))+'%';b.style.width=Math.max(.6,100*(m.end-m.start)/Math.max(1,result.duration))+'%';b.title=markerLabels[m.kind]+' '+markerClock(m.start);b.setAttribute('aria-label',b.title);b.onclick=()=>locateReference(m.start);$('marker-timeline').append(b);}
  const state=$('marker-decision-filter').value,filtered=all.filter(m=>(markerFilter==='all'||m.kind===markerFilter)&&(state==='all'||(result.decisions?.[m.id]||'pending')===state));
  $('marker-filter-description').textContent=(markerFilter==='all'?'全部类型':markerLabels[markerFilter])+' · '+filtered.length+' 项标记';$('marker-list').replaceChildren();
  for(const m of filtered.slice(0,markerLimit))$('marker-list').append(markerCard(m,result));
  if(!filtered.length){const empty=document.createElement('p');empty.className='marker-empty';empty.textContent='当前筛选下没有标记。原内容均已保留。';$('marker-list').append(empty);}
  if(filtered.length>markerLimit){const more=document.createElement('button');more.className='secondary full';more.textContent='再显示 30 项';more.onclick=()=>{markerLimit+=30;markerSignature='';renderMarkerUI(current);};$('marker-list').append(more);}
}
$('markers-run').onclick=async()=>{
  if(!current||busy(current))return;
  for(const id of ['silence-db','silence-seconds','repeat-similarity','scene-threshold'])if(!$(id).reportValidity())return;
  const data={silence_db:Number($('silence-db').value),silence_seconds:Number($('silence-seconds').value),repeat_similarity:Number($('repeat-similarity').value),scene_threshold:Number($('scene-threshold').value)};
  if(Object.values(data).some(v=>!Number.isFinite(v))){toast('请填写有效的检测参数。');return;}
  const id=current.id;saveInspectionDraft();
  try{await api('/jobs/'+id+'/markers/run',{method:'POST',body:JSON.stringify(data)});if(currentId===id)render(await api('/jobs/'+id));}catch(e){toast(e.message);}
};
syncDrawerAccess();if(current)renderMarkerUI(current);
