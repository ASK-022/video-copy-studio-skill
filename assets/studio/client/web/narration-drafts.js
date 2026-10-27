'use strict';
// Browser-local export edits are separate from the generated structure and quality report.
class NarrationDrafts {
  constructor(storage=null){this.storage=storage;this.cache=new Map();this.projects=new Map();this.storageFailed=false;}
  source(variant){return (variant.segments||[]).map(s=>s.text||'').join('\n\n');}
  key(job,batch){return 'studio-narrations-v1:'+job.id+':'+batch.id;}
  batch(job){
    const latest=job.batches.at(-1);if(!latest)return null;
    let state=this.projects.get(job.id);
    if(!state){state={batch:latest.id,latest:latest.id,view:'summary'};this.projects.set(job.id,state);}
    if(state.latest!==latest.id){state.latest=latest.id;state.batch=latest.id;state.view='summary';}
    return job.batches.find(b=>b.id===state.batch)||latest;
  }
  rows(job,batch){
    const key=this.key(job,batch);
    if(!this.cache.has(key)){
      let saved=[];try{saved=JSON.parse(this.storage?.getItem(key)||'[]');}catch(_){}
      this.cache.set(key,Array.isArray(saved)?saved:[]);
    }
    const saved=this.cache.get(key);
    const rows=batch.variants.map((variant,i)=>{
      const source=this.source(variant),old=saved[i];
      return old&&old.source===source&&typeof old.text==='string'?{source,text:old.text,selected:old.selected!==false,collapsed:old.collapsed===true}:{source,text:source,selected:true,collapsed:false};
    });
    this.cache.set(key,rows);return rows;
  }
  save(job,batch,rows){
    this.cache.set(this.key(job,batch),rows);
    try{this.storage?.setItem(this.key(job,batch),JSON.stringify(rows));return true;}
    catch(_){this.storageFailed=true;return false;}
  }
}
