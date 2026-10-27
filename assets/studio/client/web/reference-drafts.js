'use strict';
class ReferenceDrafts {
  constructor(){this.items=new Map();this.defaultProvider='local';}
  setDefault(provider){const old=this.defaultProvider;this.defaultProvider=provider;const fresh=this.items.get('__new__');if(fresh&&fresh.provider===old)fresh.provider=provider;}
  key(job){return job?.id||'__new__';}
  get(job){
    const key=this.key(job);
    if(!this.items.has(key))this.items.set(key,{
      mode:job?.kind==='link'?'link':'file',file:null,
      fileName:job?.kind==='upload'?job.title:'',link:job?.source||'',
      facts:job?.facts||'',autoAI:job?.auto_ai!==false,provider:job?job.link_provider||'local':this.defaultProvider
    });
    return this.items.get(key);
  }
  save(job,values){const draft=this.get(job);Object.assign(draft,values);return draft;}
  resetNew(){this.items.delete('__new__');return this.get(null);}
}
