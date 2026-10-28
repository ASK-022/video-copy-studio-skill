const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const Documents=vm.runInNewContext(fs.readFileSync('assets/studio/client/web/script-documents.js','utf8')+'\nScriptDocuments;',{crypto:require('node:crypto').webcrypto});
const file=(name,size=1024)=>({name,size,lastModified:100});
(async()=>{
  const q=new Documents();q.add([file('脚本A.docx'),file('脚本B.pdf')]);q.add([file('脚本A.docx'),file('脚本C.txt')]);
  assert.equal(q.rows.length,3);assert.equal(q.add([file('旧格式.doc'),file('空.txt',0),file('太大.pdf',21*1024*1024)]).rejected.length,3);
  const removed=q.rows[2].id;assert.equal(q.remove(removed),true);assert.equal(q.pending().length,2);
  const snapshot=q.snapshot();const other=new Documents(snapshot);other.rows[0].status='uploading';assert.equal(q.rows[0].status,'ready');assert.equal(other.remove(other.rows[0].id),false);
  const requests=[],progress=[];
  const first=await q.submit(async f=>{requests.push(f.name);if(f.name==='脚本B.pdf')throw Error('本次网络失败');return {id:'job-a'};},(i,total)=>progress.push([i,total]));
  assert.equal(first.imported,1);assert.equal(first.failed,1);assert.equal(q.rows[0].file,null);assert.equal(q.rows[0].jobId,'job-a');assert.equal(q.rows[1].error,'本次网络失败');assert.equal(q.pending().length,1);
  assert.equal(progress.length,4);assert.deepEqual(requests,['脚本A.docx','脚本B.pdf']);
  const retry=await q.submit(async f=>{requests.push(f.name);return {id:'job-b'};});
  assert.equal(retry.imported,1);assert.equal(retry.failed,0);assert.deepEqual(requests,['脚本A.docx','脚本B.pdf','脚本B.pdf']);assert.equal(q.pending().length,0);
  assert.equal(q.remove(q.rows[0].id),true);assert.equal(q.rows[0].jobId,'job-b');
  console.log('Script documents: multi-file append, validation, removal, reference isolation and partial-failure retry passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
