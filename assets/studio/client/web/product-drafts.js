'use strict';
// Keep edits separate for each reference and each creation mode.
class ProductDrafts {
  constructor(){this.jobs=new Map();}
  sync(job){
    const automatic=job.product_facts||job.facts||'';
    let draft=this.jobs.get(job.id);
    if(!draft){draft={same:automatic,switch:'',sameEdited:false,lastAutomatic:automatic};this.jobs.set(job.id,draft);}
    if(draft.lastAutomatic!==automatic){if(!draft.sameEdited)draft.same=automatic;draft.lastAutomatic=automatic;}
    return draft;
  }
  value(job,mode){return this.sync(job)[mode];}
  edit(job,mode,value){const draft=this.sync(job);draft[mode]=value;if(mode==='same')draft.sameEdited=true;}
  restore(job){const draft=this.sync(job);draft.same=job.product_facts||job.facts||'';draft.sameEdited=false;return draft.same;}
}
