'use strict';
let previewProject='',previewInfo=null,previewRequestKey='',previewRequestEpoch=0,previewRows=[],previewRowsSignature='',previewActive=-1;
let previewView='corrected',previewMode='video',previewPendingSeek=null;
const previewPreferences=new Map();
const previewVideo=$('transcription-video'),previewAudio=$('transcription-audio');
function activePreviewMedia(){return previewMode==='video'?previewVideo:previewAudio;}
function previewClock(t){const value=Math.round(Math.max(0,Number(t)||0)*10)/10;return String(Math.floor(value/60)).padStart(2,'0')+':'+(value%60).toFixed(1).padStart(4,'0');}
function rememberPreview(){if(previewProject)previewPreferences.set(previewProject,{view:previewView,mode:previewMode,rate:$('transcription-preview-rate').value,follow:$('transcription-follow').checked});}
function clearPreviewPlayers(){for(const player of [previewVideo,previewAudio]){player.pause();player.removeAttribute('src');player.load();}previewPendingSeek=null;}
function resetTranscriptPreview(){
  rememberPreview();previewProject='';previewInfo=null;previewRequestKey='';previewRows=[];previewRowsSignature='';previewActive=-1;++previewRequestEpoch;
  clearPreviewPlayers();$('transcription-preview').hidden=true;
}
function previewStatus(message){$('transcription-preview-status').textContent=message;}
function previewError(message){$('transcription-preview-error').hidden=!message;$('transcription-preview-error').textContent=message;}
function refreshPreviewClock(){const media=activePreviewMedia();$('transcription-playback-clock').textContent=previewClock(media.currentTime)+' / '+(Number.isFinite(media.duration)?previewClock(media.duration):previewInfo?.duration?previewClock(previewInfo.duration):'—');}
function setPreviewSource(mode,seek=null){
  if(!previewInfo||!current||previewProject!==current.id)return;
  const previous=activePreviewMedia();previous.pause();previewMode=mode;
  const media=activePreviewMedia(),route=mode==='video'?'media':'audio';
  const src=`/api/jobs/${previewProject}/reference/${route}?v=${encodeURIComponent(previewInfo.source_hash)}`;
  $('transcription-video').hidden=mode!=='video';$('transcription-audio-shell').hidden=mode!=='audio';
  $('transcription-video-mode').hidden=!previewInfo.has_video;$('transcription-audio-mode').disabled=!previewInfo.has_audio;
  for(const [id,value] of [['transcription-video-mode','video'],['transcription-audio-mode','audio']]){$(id).classList.toggle('active',mode===value);$(id).setAttribute('aria-pressed',String(mode===value));}
  previewError('');previewPendingSeek=seek;
  if(media.getAttribute('src')!==src){media.preload='metadata';media.src=src;media.load();previewStatus(mode==='audio'?'正在准备音频…':'正在加载视频…');}
  else if(seek!==null&&media.readyState>=1){media.currentTime=Math.max(0,Math.min(seek,Math.max(0,media.duration-.01)));previewPendingSeek=null;}
  media.playbackRate=Number($('transcription-preview-rate').value);rememberPreview();refreshPreviewClock();
}
function renderPreviewRows(job){
  if(!job||job.id!==previewProject)return;
  const timed=previewView==='raw'?previewInfo?.raw_segments:previewInfo?.corrected_segments;
  previewRows=timed?.length?timed:[{text:previewView==='raw'?(job.raw||''):(job.corrected||job.raw||''),start:null,end:null}].filter(s=>s.text);
  $('transcription-view-corrected').setAttribute('aria-selected',String(previewView==='corrected'));$('transcription-view-raw').setAttribute('aria-selected',String(previewView==='raw'));
  const hasTimes=previewRows.some(s=>Number.isFinite(s.start)&&Number.isFinite(s.end));
  $('transcription-timing-note').textContent=hasTimes?'点击时间定位；播放时高亮对应段落。时间来自本机音频对齐，需结合原声核对。':'暂未生成时间戳，可先播放原声，对照下方全文。';
  const signature=job.id+'|'+previewView+'|'+JSON.stringify(previewRows);
  if(signature===previewRowsSignature)return;previewRowsSignature=signature;previewActive=-1;$('transcription-preview-lines').replaceChildren();
  if(!previewRows.length){const empty=document.createElement('p');empty.className='hint';empty.textContent='转写完成后，文字会显示在这里。';$('transcription-preview-lines').append(empty);}
  previewRows.forEach((row,index)=>{
    const item=document.createElement('div');item.className='preview-transcript-row';item.dataset.index=String(index);
    const header=document.createElement('div');header.className='preview-line-heading';
    if(Number.isFinite(row.start)&&Number.isFinite(row.end)){
      const seek=document.createElement('button');seek.className='preview-line-time';seek.textContent=previewClock(row.start)+'–'+previewClock(row.end);seek.onclick=()=>seekTranscriptPreview(row.start);header.append(seek);
    }
    if(row.role){const role=document.createElement('span');role.className='preview-line-role';role.textContent=row.role;header.append(role);}
    if(header.childElementCount)item.append(header);const text=document.createElement('p');text.textContent=row.text;item.append(text);$('transcription-preview-lines').append(item);
  });highlightPreviewRow();
}
function highlightPreviewRow(){
  const media=activePreviewMedia(),time=media.currentTime;refreshPreviewClock();let index=-1;
  previewRows.forEach((row,i)=>{if(Number.isFinite(row.start)&&Number.isFinite(row.end)&&time>=row.start&&time<row.end&&(index<0||row.start>=previewRows[index].start))index=i;});
  if(index===previewActive)return;previewActive=index;const list=$('transcription-preview-lines');
  Array.from(list.children).forEach((el,i)=>{el.classList.toggle('playing',i===index);if(i===index)el.setAttribute('aria-current','true');else el.removeAttribute('aria-current');});
  const row=list.children[index];
  if(row&&$('transcription-follow').checked){const top=row.offsetTop,bottom=top+row.offsetHeight;if(top<list.scrollTop||bottom>list.scrollTop+list.clientHeight)list.scrollTo({top:Math.max(0,top-10),behavior:'smooth'});}
}
function seekTranscriptPreview(second){
  if(!previewInfo)return;const media=activePreviewMedia();
  if(media.readyState>=1){media.currentTime=Math.min(Math.max(0,second),Math.max(0,media.duration-.01));highlightPreviewRow();}
  else{previewPendingSeek=second;media.load();}
}
function renderTranscriptPreview(job){
  if(previewProject!==job.id){
    rememberPreview();clearPreviewPlayers();previewProject=job.id;previewInfo=null;previewRequestKey='';previewRowsSignature='';previewRows=[];previewActive=-1;++previewRequestEpoch;
    const prefs=previewPreferences.get(job.id);previewView=prefs?.view||'corrected';previewMode=prefs?.mode||'video';$('transcription-preview-rate').value=prefs?.rate||'1';$('transcription-follow').checked=prefs?.follow??true;previewError('');
  }
  $('transcription-preview').hidden=activeScene!=='transcript';
  if(activeScene!=='transcript'){previewVideo.pause();previewAudio.pause();return;}
  renderPreviewRows(job);
  if(!job.input_file){previewVideo.hidden=true;$('transcription-audio-shell').hidden=true;previewStatus('原文件准备完成后即可播放。');return;}
  const key=job.id+'|'+job.input_file+'|'+job.raw+'|'+job.corrected+'|'+JSON.stringify(job.structure);
  if(key===previewRequestKey)return;previewRequestKey=key;const epoch=++previewRequestEpoch;previewStatus('正在读取参考…');
  api('/jobs/'+job.id+'/reference/info').then(info=>{
    if(epoch!==previewRequestEpoch||previewProject!==job.id||currentId!==job.id)return;
    previewInfo=info;const mode=info.has_video&&previewMode!=='audio'?'video':'audio';
    if(!info.has_video&&!info.has_audio){previewError('这个文件没有可预览的音视频轨道。');return;}
    // Polling can update text while playing; only a different URL may reload the media.
    const media=mode==='video'?previewVideo:previewAudio,route=mode==='video'?'media':'audio';
    const src=`/api/jobs/${job.id}/reference/${route}?v=${encodeURIComponent(info.source_hash)}`;
    if(media.getAttribute('src')!==src)setPreviewSource(mode);else previewStatus(media.paused?'点击播放，边听边核对。':'正在播放…');
    renderPreviewRows(current);refreshPreviewClock();
  }).catch(error=>{if(epoch===previewRequestEpoch&&previewProject===job.id){previewError(error.message);previewStatus('暂时无法预览');previewRequestKey='';}});
}
$('transcription-video-mode').onclick=()=>{if(previewMode!=='video')setPreviewSource('video',activePreviewMedia().currentTime||0);};
$('transcription-audio-mode').onclick=()=>{if(previewMode!=='audio')setPreviewSource('audio',activePreviewMedia().currentTime||0);};
for(const [id,view] of [['transcription-view-corrected','corrected'],['transcription-view-raw','raw']])$(id).onclick=()=>{previewView=view;rememberPreview();renderPreviewRows(current);};
$('transcription-preview-rate').onchange=()=>{for(const player of [previewVideo,previewAudio])player.playbackRate=Number($('transcription-preview-rate').value);rememberPreview();};
$('transcription-follow').onchange=()=>{rememberPreview();if($('transcription-follow').checked)highlightPreviewRow();};
for(const player of [previewVideo,previewAudio]){
  player.addEventListener('loadedmetadata',()=>{if(player!==activePreviewMedia())return;if(previewPendingSeek!==null){player.currentTime=Math.min(previewPendingSeek,Math.max(0,player.duration-.01));previewPendingSeek=null;}previewStatus('点击播放，边听边核对。');refreshPreviewClock();});
  player.addEventListener('timeupdate',()=>{if(player===activePreviewMedia())highlightPreviewRow();});
  player.addEventListener('play',()=>{if(player===activePreviewMedia())previewStatus('正在播放…');});
  player.addEventListener('pause',()=>{if(player===activePreviewMedia()&&player.getAttribute('src'))previewStatus('已暂停，可继续核对文字。');});
  player.addEventListener('ended',()=>{if(player===activePreviewMedia())previewStatus('播放完成。');});
  player.addEventListener('error',()=>{if(player!==activePreviewMedia()||!player.getAttribute('src'))return;previewStatus('播放未就绪');previewError(previewMode==='video'?'当前视频格式无法在浏览器播放，可切换「仅听音频」继续核对。':'音频预览未能加载，请检查原文件是否含音轨，或重新打开当前参考。');});
}
document.addEventListener('play',event=>{if(event.target instanceof HTMLMediaElement)document.querySelectorAll('video,audio').forEach(player=>{if(player!==event.target)player.pause();});},true);
if(current)renderTranscriptPreview(current);
