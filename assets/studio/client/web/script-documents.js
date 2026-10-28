'use strict';
// A batch stays a list of independent references; failed files can be retried alone.
class ScriptDocuments {
  constructor(rows=[]){this.rows=rows.map(row=>({...row}));}
  snapshot(){return this.rows.map(row=>({...row}));}
  pending(){return this.rows.filter(row=>row.file&&!row.jobId&&row.status!=='uploading');}
  async submit(send,notify=()=>{}){
    const pending=this.pending(),results=[];
    for(const [index,row] of pending.entries()){
      row.status='uploading';row.error='';notify(index+1,pending.length);
      try{const reply=await send(row.file);if(!reply?.id)throw new Error('上传未返回脚本编号，请检查后重试。');row.jobId=reply.id;row.status='imported';row.file=null;results.push(reply);}
      catch(error){row.status='error';row.error=error.message||'上传未完成，请重试。';}
      notify(index+1,pending.length);
    }
    return {first:results[0],imported:results.length,failed:pending.filter(row=>row.status==='error').length};
  }
  add(files){
    const rejected=[];let added=0;
    for(const file of files){
      if(!/\.(docx|pdf|txt)$/i.test(file.name)||file.size>20*1024*1024||!file.size){rejected.push(file.name);continue;}
      if(this.rows.some(row=>row.name===file.name&&row.size===file.size&&row.modified===file.lastModified))continue;
      this.rows.push({id:'document-'+crypto.randomUUID(),name:file.name,size:file.size,modified:file.lastModified,file,status:'ready',jobId:'',error:''});added++;
    }
    return {added,rejected};
  }
  remove(id){const row=this.rows.find(row=>row.id===id);if(!row||row.status==='uploading')return false;this.rows=this.rows.filter(row=>row.id!==id);return true;}
}
