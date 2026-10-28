'use strict';
// File-backed manuscript versions are authoritative; local storage is an offline buffer.
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
      const source=this.source(variant),server=variant.manuscript||{revision:0,text:source,segments:variant.segments,kind:'generated'},old=saved[i];
      let row=old&&old.source===source&&typeof old.text==='string'?old:{source,text:server.text,selected:true,collapsed:false};
      if(row.revision===undefined){
        const legacy=!variant.manuscript&&row.text!==source;
        if(!legacy)row.text=server.text;
        Object.assign(row,{revision:server.revision,persistedText:server.text,segments:legacy?null:server.segments,dirty:legacy,saveStatus:legacy?'pending':'saved'});
      }else if(server.revision>row.revision&&(!row.dirty||row.text===server.text)){
        Object.assign(row,{text:server.text,segments:server.segments,revision:server.revision,persistedText:server.text,dirty:false,saveStatus:'saved'});
      }
      row.selected=row.selected!==false;row.collapsed=row.collapsed===true;
      return row;
    });
    this.cache.set(key,rows);return rows;
  }
  save(job,batch,rows){
    this.cache.set(this.key(job,batch),rows);
    try{this.storage?.setItem(this.key(job,batch),JSON.stringify(rows));return true;}
    catch(_){this.storageFailed=true;return false;}
  }
}
