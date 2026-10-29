'use strict';
(() => {
  const bridge = window.contentHubNative;
  if (!bridge) return;
  document.title = '编导台 · 内容中台';
  document.body.classList.add('content-hub-integrated');
  const brand = document.querySelector('.brand strong');
  if (brand) brand.textContent = '编导台';
  const edition = document.querySelector('.brand .edition');
  if (edition) edition.textContent = '内容中台';
  let sentContext='';
  function publishContext(job){const value={name:job?.project||job?.title||'编导台',product:job?.product_label||''},signature=JSON.stringify(value);if(sentContext===signature)return;sentContext=signature;void bridge.setContext(value);}
  const previousRender=render;
  render=function(job,...args){const result=previousRender(job,...args);publishContext(job);return result;};
  bridge.onState(state=>{if(state.section==='editor')sentContext='';else publishContext(current);});
  const original = enhanceNarrationCard;
  enhanceNarrationCard = function(info) {
    original(info);
    const button = document.createElement('button');
    button.type = 'button';button.className = 'primary content-hub-handoff';button.textContent = '用此稿进入剪辑台';
    const status = document.createElement('span');status.className = 'hint';status.setAttribute('role','status');
    info.heading.append(button);info.card.append(status);
    button.onclick = async () => {
      button.disabled = true;status.textContent = '正在保存成稿并创建剪辑工程…';
      try {
        await flushNarrations(info.data);
        const row = info.data.rows[info.index];
        if (!row.segments) throw new Error('请先在逐段对照中确认成稿段落。');
        const result = await bridge.handoff({jobId:info.data.job.id,batchId:info.data.batch.id,index:info.index,revision:row.revision});
        if (!result.ok) throw new Error(result.error);
        status.textContent = `已交接成稿 v${row.revision}，剪辑台已打开。`;
      } catch (e) { status.textContent = e.message || '交接失败，请重试。'; }
      finally { button.disabled = false; }
    };
  };
})();
