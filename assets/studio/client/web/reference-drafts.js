'use strict';
class ReferenceDrafts {
  constructor(){this.items=new Map();this.defaultProvider='local';this.space='video';}
  setSpace(space){this.space=space==='script'?'script':'video';}
  setDefault(provider){const old=this.defaultProvider;this.defaultProvider=provider;for(const [key,fresh] of this.items)if(key.startsWith('__new__:')&&fresh.provider===old)fresh.provider=provider;}
  key(job){return job?.id||'__new__:'+this.space;}
  get(job){
    const key=this.key(job);
    if(!this.items.has(key))this.items.set(key,{
      mode:job?.kind==='script'||(!job&&this.space==='script')?'script':job?.kind==='link'?'link':'file',file:null,
      scriptText:job?.kind==='script'?job.raw||'':'',scriptFiles:job?.script_file?[{id:'job-'+job.id,name:job.title,size:null,file:null,status:'imported',jobId:job.id,error:''}]:[],
      fileName:job?.kind==='upload'?job.title:'',link:job?.source||'',
      facts:job?.facts||'',autoAI:job?.auto_ai!==false,provider:job?job.link_provider||'local':this.defaultProvider
    });
    return this.items.get(key);
  }
  save(job,values){const draft=this.get(job);Object.assign(draft,values);return draft;}
  removeScriptDocument(id,jobId=''){for(const draft of this.items.values())draft.scriptFiles=(draft.scriptFiles||[]).filter(row=>row.id!==id&&(!jobId||row.jobId!==jobId));}
  resetNew(){this.items.delete(this.key(null));return this.get(null);}
}
