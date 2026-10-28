'use strict';
let feishuConfig=null,tableSnapshot=null,tableBusy=false,tableEpoch=0;
const tableExportPrefs=new TableExportPrefs(narrationStorage);
let tableMeta=null;
const tableMetaFields=['product','reference_url','required_time','completion','quantity','shot_requirements','shot_reference_1','shot_reference_2'];
const tableTemplateNames={script:'脚本文案表',shooting:'拍摄需求表',archive:'详细归档'};
function saveTableMeta(){
  if(!tableSnapshot||!tableMeta)return;
  tableMeta.template=$('table-template').value;
  for(const key of tableMetaFields)tableMeta[key]=$('table-'+key).value;
  if(!tableExportPrefs.save(tableSnapshot.job,tableSnapshot.batch,tableMeta))toast('表格补充资料暂未保存到浏览器，请及时导出。');
}
function currentTableOptions(){
  const options={};for(const key of tableMetaFields)options[key]=$('table-'+key).value;
  options.quantity=$('table-template').value!=='shooting'||options.quantity===''?null:Number(options.quantity);
  return options;
}
for(const key of tableMetaFields)$('table-'+key).oninput=()=>{if(key==='shot_requirements'&&tableMeta)tableMeta.shotsEdited=true;saveTableMeta();};
$('table-template').onchange=()=>{saveTableMeta();tableMode();};
function feishuMessage(message,error=false){$('feishu-message').hidden=false;$('feishu-message').textContent=message;$('feishu-message').classList.toggle('error',error);}
function feishuSheetOptions(config,sheets=[]){
  const select=$('feishu-sheet');select.replaceChildren();
  const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='测试连接后选择工作表';select.append(placeholder);
  if(config.sheet_id&&!sheets.some(s=>s.id===config.sheet_id))sheets.unshift({id:config.sheet_id,title:config.sheet_id});
  for(const sheet of sheets){const option=document.createElement('option');option.value=sheet.id;option.textContent=sheet.title+' · '+sheet.id;select.append(option);}
  select.value=config.sheet_id||'';
}
async function refreshFeishu(){
  const config=await api('/feishu/settings');feishuConfig=config;
  $('feishu-app-id').value=config.app_id;$('feishu-secret').value='';$('feishu-url').value=config.target_url;
  feishuSheetOptions(config);providerStatus('provider-feishu-status',config.has_secret);
  $('feishu-secret-status').textContent=config.has_secret?'已加密保存；留空不修改':'未配置';
  return config;
}
$('feishu-manage').onclick=()=>{$('feishu-config-panel').hidden=!$('feishu-config-panel').hidden;};
$('feishu-form').onsubmit=e=>{e.preventDefault();saveFeishu(false);};
$('settings-dialog').addEventListener('close',()=>{$('feishu-secret').value='';});
$('feishu-url').onchange=()=>feishuSheetOptions({sheet_id:''});
$('feishu-test').onclick=()=>saveFeishu(true);
async function saveFeishu(test){
  if(!$('feishu-form').reportValidity())return;
  $('feishu-test').disabled=true;$('feishu-save').disabled=true;
  try{
    const config=await api('/feishu/settings',{method:'PUT',body:JSON.stringify({app_id:$('feishu-app-id').value,secret:$('feishu-secret').value,target_url:$('feishu-url').value,sheet_id:$('feishu-sheet').value})});
    await refreshFeishu();feishuMessage('配置已保存。');
    if(test){feishuMessage('正在读取飞书工作表，不写入文案…');const result=await api('/feishu/test',{method:'POST'});feishuSheetOptions({...config,sheet_id:result.sheet_id},result.sheets);feishuMessage(result.message);}
  }catch(e){feishuMessage(e.message,true);}finally{$('feishu-test').disabled=false;$('feishu-save').disabled=false;}
}
$('feishu-clear').onclick=async()=>{try{await api('/feishu/settings',{method:'PUT',body:JSON.stringify({clear:true})});await refreshFeishu();feishuMessage('已清除本机飞书连接配置，表格内容保留。');}catch(e){feishuMessage(e.message,true);}};
function tableMode(){
  const cloud=$('table-destination').value==='feishu';$('table-cloud-info').hidden=!cloud;$('table-local-info').hidden=cloud;
  const template=$('table-template').value;
  $('table-common-fields').hidden=template==='archive';$('table-shooting-fields').hidden=template!=='shooting';
  $('table-completion-label').textContent=template==='shooting'?'完成情况':'拍摄完成时间 / 情况';
  $('table-layout-note').textContent=template==='script'?'产品｜脚本文案｜参考视频链接｜需求时间｜拍摄完成时间。每条脚本一行，产品按脚本编号区分。':template==='shooting'?'产品｜素材需求数量｜参考视频1｜画面镜头需求｜镜头参考1｜镜头参考2｜需求时间｜完成情况。所选脚本汇总为一条素材需求；数量和日期按填写内容导出。':'保留原来的八列：序号、标题、完整口播、字数、生成方式、参考来源、生成时间、稿件版本。';
  $('table-submit').textContent=cloud?'追加到飞书':'下载 Excel';
  $('table-submit').disabled=tableBusy||!tableSnapshot?.items.length||(cloud&&!feishuConfig?.has_secret);
}
$('table-destination').onchange=tableMode;
$('table-close').onclick=()=>{if(!tableBusy)$('table-dialog').close();};
$('table-dialog').addEventListener('cancel',e=>{if(tableBusy)e.preventDefault();});
$('table-configure').onclick=async()=>{$('table-dialog').close();await openSettings('feishu');};
$('narration-table').onclick=async()=>{
  const data=activeNarrations();if(!data)return;
  try{if(typeof flushNarrations==='function')await flushNarrations(data);}catch(e){toast(e.message);return;}
  const epoch=++tableEpoch;
  tableSnapshot={jobId:data.job.id,title:data.job.title,batchId:data.batch.id,job:{id:data.job.id,title:data.job.title},batch:{id:data.batch.id,mode:data.batch.mode},items:data.rows.flatMap((r,index)=>r.selected?[{index,text:r.text,revision:r.revision}]:[])};
  tableMeta=tableExportPrefs.load(data.job,data.batch);
  if(!tableMeta.shotsEdited)tableMeta.shot_requirements=tableExportPrefs.suggestions(data.batch,tableSnapshot.items.map(r=>r.index));
  $('table-template').value=tableMeta.template;
  for(const key of tableMetaFields)$('table-'+key).value=tableMeta[key];
  $('table-summary').textContent=`${data.job.title} · ${narrationModes[data.batch.mode]} · 已选 ${tableSnapshot.items.length} 条。使用当前修改后的完整口播。`;
  $('table-message').hidden=true;$('table-target').textContent='正在读取配置…';tableMode();$('table-dialog').showModal();
  try{const config=await api('/feishu/settings');if(epoch!==tableEpoch)return;feishuConfig=config;$('table-target').textContent=config.has_secret?config.target_url+(config.sheet_id?' · 工作表 '+config.sheet_id:' · 若有多张工作表，请先测试并选择'):'尚未配置飞书应用与目标表格';tableMode();}
  catch(e){$('table-target').textContent=e.message;}
};
$('table-submit').onclick=async()=>{
  const snapshot=tableSnapshot;if(!snapshot||tableBusy)return;
  const quantity=$('table-quantity');if($('table-template').value==='shooting'&&!quantity.reportValidity())return;
  saveTableMeta();snapshot.template=$('table-template').value;snapshot.table_options=currentTableOptions();
  if($('table-destination').value==='excel'){
    $('table-dialog').close();await exportNarrations('xlsx',snapshot);return;
  }
  tableBusy=true;tableMode();$('table-close').disabled=true;$('table-configure').disabled=true;$('table-destination').disabled=true;
  $('table-message').hidden=false;$('table-message').classList.remove('error');$('table-message').textContent='正在追加文案，请等待结果…';
  try{
    const result=await api(`/jobs/${snapshot.jobId}/drafts/feishu`,{method:'POST',body:JSON.stringify({batch_id:snapshot.batchId,format:'xlsx',items:snapshot.items,template:snapshot.template,table_options:snapshot.table_options})});
    const unit=snapshot.template==='shooting'?'条拍摄需求':'条文案';
    $('table-message').textContent=result.duplicate?`这 ${result.count} ${unit}此前已写入「${result.sheet_title}」，本次未重复追加。`:`已追加 ${result.count} ${unit}到「${result.sheet_title}」。`;
  }catch(e){$('table-message').textContent=e.message;$('table-message').classList.add('error');}
  finally{tableBusy=false;tableMode();$('table-close').disabled=false;$('table-configure').disabled=false;$('table-destination').disabled=false;}
};
