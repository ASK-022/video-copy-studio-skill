import {test} from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign,createHash} from 'node:crypto';
import {mkdtempSync,readFileSync,rmSync,existsSync,mkdirSync,writeFileSync} from 'node:fs';
import {EventEmitter} from 'node:events';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {canonical,verifyManifest,createContentHubUpdates,downloadPackage,REPOSITORY,MIRRORS,newer} from './contenthub-updates.mjs';
import {acknowledgeDesktopBoot} from './contenthub-boot.mjs';
const pair=generateKeyPairSync('rsa',{modulusLength:3072});const jwk=pair.publicKey.export({format:'jwk'}),key={modulus:Buffer.from(jwk.n,'base64url').toString('base64'),exponent:65537};
const data=Buffer.from('signed package fixture'),sha=createHash('sha256').update(data).digest('hex');
const name='ContentHub-delta-v1.1.0.zip.part001';
const payload={format:'contenthub-desktop-update/v1',repository:REPOSITORY,version:'1.1.0',min_version:'1.0.1',resource_contract:1,packages:[{base_version:'1.0.1',name:'ContentHub-delta-v1.1.0.zip',bytes:data.length,sha256:sha,parts:[{name,bytes:data.length,sha256:sha,urls:[...MIRRORS.map(host=>`${host}/gh/${REPOSITORY}@contenthub-v1.1.0/releases/contenthub/files/${name}`),`https://github.com/${REPOSITORY}/releases/download/contenthub-v1.1.0/${name}`]}]}]};
const envelope=value=>({payload:value,signature:sign('RSA-SHA256',Buffer.from(canonical(value)),pair.privateKey).toString('base64')});
test('publisher signature, product, sources, sizes and version order are enforced',()=>{
 assert.equal(verifyManifest(envelope(payload),key).version,'1.1.0');
 const altered=envelope(payload);altered.payload={...payload,version:'9.0.0'};assert.throws(()=>verifyManifest(altered,key));
 for(const changed of [{...payload,resource_contract:2},{...payload,repository:'foreign/repo'},{...payload,packages:[{...payload.packages[0],parts:[{...payload.packages[0].parts[0],urls:['https://foreign.test/payload']}]}]}])assert.throws(()=>verifyManifest(envelope(changed),key));
 assert.ok(newer('1.1.0','1.0.9'));assert.equal(newer('1.1.0','1.1.0'),false);assert.equal(newer('1.0.9','1.1.0'),false);
});
test('corrupt downloads fall back; a verified cached part is reused',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'contenthub-download-'));let calls=0;
 try{
  const request=async()=>new Response(++calls===1?Buffer.from('bad'):data);
  const path=await downloadPackage(payload.packages[0],directory,{request});assert.deepEqual(readFileSync(path),data);assert.equal(calls,2);
  await downloadPackage(payload.packages[0],directory,{request:()=>{throw Error('must reuse cached part');}});
 }finally{rmSync(directory,{recursive:true,force:true});}
});
test('busy tasks keep the current process running and update ready',async()=>{
 const root=mkdtempSync(join(tmpdir(),'contenthub-update-')),profile=join(root,'profile');let stopped=false;
 try{
  const service=createContentHubUpdates({root:join(root,'app'),dataDir:profile,version:'1.0.1',key,feeds:['https://fixture.test/latest'],request:async url=>new Response(url.includes('latest')?JSON.stringify(envelope(payload)):data),prepareRestart:async()=>({ok:false,error:'director-busy'}),beforeInstall:async()=>{stopped=true;},quit:()=>{stopped=true;},showMessage:async()=>{}});
  assert.equal((await service.check()).status,'ready');assert.deepEqual(await service.restart(),{ok:false,error:'director-busy'});assert.equal(service.snapshot().status,'ready');assert.equal(stopped,false);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('failed signature or missing release never claims latest or installs',async()=>{
 const service=createContentHubUpdates({root:tmpdir(),dataDir:join(tmpdir(),'contenthub-state'),version:'1.0.1',key,feeds:['https://fixture.test/latest'],request:async()=>new Response('{}'),prepareRestart:async()=>({ok:true})});
 assert.equal((await service.check()).status,'error');assert.equal((await service.restart()).ok,false);
});
test('ready update hands a signed owned job to the external worker before quitting',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'contenthub-handoff-')),root=join(directory,'app'),profile=join(directory,'profile');mkdirSync(root);writeFileSync(join(root,'ContentHub.exe'),'fixture launcher');const order=[];let command;
 try{
  const service=createContentHubUpdates({root,dataDir:profile,version:'1.0.1',key,feeds:['https://fixture.test/latest'],request:async url=>new Response(url.includes('latest')?JSON.stringify(envelope(payload)):data),prepareRestart:async()=>({ok:true}),beforeInstall:async()=>{order.push('stopped');},start:(exe,args)=>{command={exe,args};const child=new EventEmitter();child.unref=()=>{};queueMicrotask(()=>child.emit('spawn'));order.push('worker');return child;},quit:()=>order.push('quit'),showMessage:async()=>{}});
  await service.check();assert.deepEqual(await service.restart(),{ok:true});assert.deepEqual(order,['stopped','worker','quit']);
  const job=JSON.parse(readFileSync(command.args[1],'utf8'));assert.equal(job.root,root);assert.equal(job.data,profile);assert.equal(job.parent_pid,process.pid);assert.equal(job.envelope.signature,envelope(payload).signature);assert.ok(existsSync(command.exe));
 }finally{rmSync(directory,{recursive:true,force:true});}
});
test('boot receipt requires both workbenches, expected nonce and owned profile path',()=>{
 const root=mkdtempSync(join(tmpdir(),'contenthub-boot-')),nonce='a'.repeat(48),path=join(root,'updates',`boot-${nonce}.json`),env={CONTENT_HUB_UPDATE_NONCE:nonce,CONTENT_HUB_UPDATE_ACK:path};
 try{
  assert.equal(acknowledgeDesktopBoot({dataDir:root,version:'1.1.0',director:false,editor:true},env),false);assert.equal(existsSync(path),false);
  assert.throws(()=>acknowledgeDesktopBoot({dataDir:root,version:'1.1.0',director:true,editor:true},{...env,CONTENT_HUB_UPDATE_ACK:join(root,'private.json')}));
  assert.equal(acknowledgeDesktopBoot({dataDir:root,version:'1.1.0',pid:123,director:true,editor:true},env),true);assert.equal(JSON.parse(readFileSync(path)).pid,123);
 }finally{rmSync(root,{recursive:true,force:true});}
});
