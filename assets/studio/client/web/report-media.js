'use strict';
let reportImageDialog=null,reportImageJob='';
function reportElement(tag,cls='',text=''){const node=document.createElement(tag);node.className=cls;node.textContent=text;return node;}
function reportFrameURL(job,frame){return `/api/jobs/${encodeURIComponent(job.id)}/frames/${frame.id}`;}
function openReportImage(job,frame){
  if(!reportImageDialog){reportImageDialog=reportElement('dialog','report-image-dialog');document.body.append(reportImageDialog);}
  reportImageJob=job.id;reportImageDialog.replaceChildren();
  const head=reportElement('div','report-image-head'),title=reportElement('strong','',`参考抽样画面 · ${markerClock(frame.time)}`),close=reportElement('button','quiet','关闭');
  close.onclick=()=>reportImageDialog.close();head.append(title,close);
  const img=reportElement('img');img.src=reportFrameURL(job,frame);img.alt=title.textContent;
  const locate=reportElement('button','secondary','定位到原片');locate.onclick=()=>{if(current?.id!==job.id)return;reportImageDialog.close();openInspection();locateReference(frame.time);};
  reportImageDialog.append(head,img,reportElement('p','hint','来自本机缓存的真实抽样画面；不是精确切镜边界。'),locate);
  if(!reportImageDialog.open)reportImageDialog.showModal();
}
function reportFrameBlock(job,picked){
  const block=reportElement('div','report-row-frames');
  for(const frame of picked.frames){
    const button=reportElement('button','report-frame-button');button.type='button';button.setAttribute('aria-label',`查看 ${markerClock(frame.time)} 抽样截图`);
    const img=reportElement('img');img.src=reportFrameURL(job,frame);img.loading='lazy';img.alt=`${markerClock(frame.time)} 参考截图`;
    const caption=reportElement('span','',`${picked.nearby?'邻近抽样 · ':''}${markerClock(frame.time)} · 点击放大`);
    img.onerror=()=>{img.hidden=true;caption.textContent='截图文件不可用';button.disabled=true;};
    button.append(img,caption);button.onclick=()=>openReportImage(job,frame);block.append(button);
  }
  if(!picked.frames.length)block.append(reportElement('span','hint','暂无对应抽样截图'));
  return block;
}
function enhanceReportMedia(job,scene,record){
  if(reportImageDialog?.open&&reportImageJob!==job.id)reportImageDialog.close();
  if(!['breakdown','storyboard'].includes(scene))return;
  const evidence=job.evidence||{},segments=new Map((record.segments||[]).map(s=>[s.id,s]));
  const data=scene==='breakdown'?record.data?.structure:record.data?.shots;if(!data?.length)return;
  for(const wrap of $('scene-report-body').querySelectorAll('.report-table')){
    const table=wrap.querySelector('table'),head=table.tHead?.rows[0];if(!head)continue;
    const labels=Array.from(head.cells,c=>c.textContent);
    if(scene==='breakdown'&&!labels.includes('手法')||scene==='storyboard'&&!labels.includes('画面内容'))continue;
    if(wrap.dataset.mediaReady)return;
    const rows=Array.from(table.tBodies[0].rows);if(rows.length!==data.length)continue;
    wrap.dataset.mediaReady='1';wrap.classList.add('report-media-table',`report-${scene}-table`);
    let imageColumn=labels.indexOf('画面内容');
    if(scene==='breakdown'){imageColumn=3;head.insertBefore(reportElement('th','','画面截图'),head.cells[imageColumn]);}
    rows.forEach((row,index)=>{
      const value=data[index],segment=segments.get(value.segment_id);
      const picked=ReportMediaRules.chooseFrames(segment,evidence.frames,value.evidence_frame_ids||[],evidence.sample_interval);
      let cell;if(scene==='breakdown'){cell=reportElement('td');row.insertBefore(cell,row.cells[imageColumn]);}else cell=row.cells[imageColumn];
      cell.classList.add('report-visual-cell');cell.prepend(reportFrameBlock(job,picked));
      if(row.cells[0])row.cells[0].classList.add('report-time-cell');
    });
    const frame=reportElement('section','report-reading-frame'),toolbar=reportElement('div','report-reading-toolbar'),toggle=reportElement('button','secondary','逐段阅读 · 免横滑');toggle.type='button';toggle.setAttribute('aria-pressed','false');
    toolbar.append(reportElement('span','hint','表头与时间列固定 · 截图可点击放大'),toggle);
    const rail=reportElement('div','report-scroll-rail'),railInner=reportElement('div');rail.tabIndex=0;rail.setAttribute('role','region');rail.setAttribute('aria-label','表格顶部横向滚动条');rail.append(railInner);
    wrap.before(frame);frame.append(toolbar,rail,wrap);wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',scene==='breakdown'?'爆款拆解分段表':'分镜脚本表');
    let syncing=false;const sync=(from,to)=>{if(syncing)return;syncing=true;to.scrollLeft=from.scrollLeft;syncing=false;};rail.onscroll=()=>sync(rail,wrap);wrap.onscroll=()=>sync(wrap,rail);
    const resize=()=>{if(!wrap.isConnected){observer.disconnect();return;}railInner.style.width=table.scrollWidth+'px';rail.hidden=frame.classList.contains('reading-cards')||table.scrollWidth<=wrap.clientWidth+1;};
    const observer=new ResizeObserver(resize);observer.observe(wrap);requestAnimationFrame(resize);
    const cards=reportElement('div','report-reading-cards');cards.hidden=true;
    const headers=Array.from(head.cells,c=>c.textContent);
    for(const row of rows){const card=reportElement('article','report-reading-card');card.append(reportElement('h4','',row.cells[0].textContent));Array.from(row.cells).slice(1).forEach((cell,index)=>{const part=reportElement('section');part.append(reportElement('strong','',headers[index+1]));const copy=reportElement('div','report-card-value');for(const child of cell.childNodes)copy.append(child.cloneNode(true));copy.querySelectorAll('.report-frame-button').forEach((button,i)=>{const original=cell.querySelectorAll('.report-frame-button')[i];button.onclick=original.onclick;});part.append(copy);card.append(part);});cards.append(card);}
    frame.append(cards);toggle.onclick=()=>{const active=!frame.classList.contains('reading-cards');frame.classList.toggle('reading-cards',active);wrap.hidden=active;cards.hidden=!active;toggle.textContent=active?'返回表格':'逐段阅读 · 免横滑';toggle.setAttribute('aria-pressed',String(active));resize();};
  }
}
