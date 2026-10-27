'use strict';
class TableExportPrefs {
  constructor(storage=null){this.storage=storage;this.cache=new Map();}
  key(job,batch){return 'studio-table-options-v1:'+job.id+':'+batch.id;}
  load(job,batch){
    const key=this.key(job,batch);if(this.cache.has(key))return this.cache.get(key);
    let saved=null;try{saved=JSON.parse(this.storage?.getItem(key)||'null');}catch(_){}
    const named=(batch.facts||'').match(/^(?:商品|产品|商品名称|产品名称)[：:]\s*(.+)$/m);
    const product=named?.[1]||(batch.mode==='same'?job.product_profile?.product?.value:'')||'';
    const data={template:'script',product,reference_url:job.kind==='link'?job.source||'':'',required_time:'',completion:'',quantity:'',shot_requirements:'',shot_reference_1:'',shot_reference_2:'',shotsEdited:false};
    if(saved&&typeof saved==='object')for(const key of Object.keys(data))if(typeof saved[key]===typeof data[key])data[key]=saved[key];
    if(!['script','shooting','archive'].includes(data.template))data.template='script';
    this.cache.set(key,data);return data;
  }
  save(job,batch,data){
    this.cache.set(this.key(job,batch),data);
    try{this.storage?.setItem(this.key(job,batch),JSON.stringify(data));return true;}catch(_){return false;}
  }
  suggestions(batch,indices){
    const lines=[];
    for(const index of indices)for(const segment of batch.variants[index]?.production_segments||[]){
      const text=String(segment.screen_suggestion||'').trim();if(text&&!lines.includes(text))lines.push(text);
    }
    return lines.length?'【脚本生成的拍摄建议，待确认】\n'+lines.join('\n'):'';
  }
}
