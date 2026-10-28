'use strict';
// Keep edits separate for each reference and each creation mode.
class ProductDrafts {
  static libraryCandidate(job,mode,text){
    const applied=job.material_drafts?.[mode],profile=applied?.active?applied.profile:(mode==='same'?job.product_profile:null);
    const named=text.match(/^商品[：:]\s*(.+)$/m);
    return {name:named?.[1]?.trim()||profile?.product?.value||'',
      facts:text.replace(/^商品[：:].*\n?/,'').replace(/^(卖点|已确认卖点)[：:]\n?/,''),
      pending:(profile?.needs_confirmation||[]).map(p=>p.value).join('\n').slice(0,2000),
      source:applied?.active?`自己的商品${({images:'图片',text:'文案',document:'文档'}[applied.kind]||'资料')}提取 · 记录 ${applied.source_id}`:(mode==='same'?(job.source||job.title):'')};
  }
  constructor(){this.jobs=new Map();}
  sync(job){
    const automatic=job.product_facts||job.facts||'';
    let draft=this.jobs.get(job.id);
    if(!draft){const applied=job.material_drafts||{};draft={same:applied.same?.active?applied.same.text:automatic,switch:applied.switch?.active?applied.switch.text:'',sameEdited:!!applied.same?.active,lastAutomatic:automatic};this.jobs.set(job.id,draft);}
    if(draft.lastAutomatic!==automatic){if(!draft.sameEdited)draft.same=automatic;draft.lastAutomatic=automatic;}
    return draft;
  }
  value(job,mode){return this.sync(job)[mode];}
  edit(job,mode,value){const draft=this.sync(job);draft[mode]=value;if(mode==='same')draft.sameEdited=true;}
  restore(job){const draft=this.sync(job);draft.same=job.product_facts||job.facts||'';draft.sameEdited=false;return draft.same;}
}
