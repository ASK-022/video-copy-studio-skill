'use strict';
(() => {
  const pane=$('settings-services-pane'),box=document.createElement('section');box.className='compute-settings';
  const heading=document.createElement('h3');heading.textContent='本地转写设备';
  const description=document.createElement('p');description.className='hint';description.textContent='切换对下一次转写生效，当前任务继续使用启动时的设备。GPU 用于本地语音识别与对齐。';
  const label=document.createElement('label');label.textContent='计算设备';label.htmlFor='compute-mode';
  const select=document.createElement('select');select.id='compute-mode';
  for(const [value,text] of [['auto','自动选择 · 优先 GPU'],['gpu','GPU'],['cpu','CPU']])select.append(new Option(text,value));
  const status=document.createElement('p');status.id='compute-status';status.className='hint';status.setAttribute('role','status');
  const actions=document.createElement('div');actions.className='editorial-actions';
  const refresh=document.createElement('button');refresh.type='button';refresh.className='secondary';refresh.textContent='重新检测';
  const save=document.createElement('button');save.type='button';save.className='primary';save.textContent='保存设备设置';
  actions.append(refresh,save);box.append(heading,description,label,select,status,actions);pane.querySelector('.settings-intro').after(box);
  function show(value){select.value=value.mode;const gpu=value.gpu;
    status.textContent=(gpu.available?'GPU 可用：'+gpu.name+'；':'GPU：'+gpu.reason+'；')+'下次转写：'+({gpu:'GPU',cpu:'CPU',unavailable:'GPU 不可用，请重新检测或选择 CPU'}[value.selected_device])+'。';
    if(value.last_run)status.textContent+=' 最近一次启动：'+value.last_run.name+(value.last_run.fallback_reason?'（'+value.last_run.fallback_reason+'）':'')+'。';
    status.textContent+=' 截图、OCR 和场景检测仍使用各自的处理方式。';
  }
  async function load(force=false){refresh.disabled=save.disabled=true;status.textContent='正在检测本机转写设备…';try{show(await api('/compute'+(force?'?refresh=true':'')));}catch(e){status.textContent=e.message;}finally{refresh.disabled=save.disabled=false;}}
  refresh.onclick=()=>load(true);save.onclick=async()=>{save.disabled=true;try{show(await api('/compute',{method:'PUT',body:JSON.stringify({mode:select.value})}));toast('设备设置已保存，下次转写生效。');}catch(e){status.textContent=e.message;}finally{save.disabled=false;}};
  const previous=$('settings-open').onclick;$('settings-open').onclick=async()=>{await previous?.();void load();};
})();
