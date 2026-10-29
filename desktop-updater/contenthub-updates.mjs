/** Signed, versioned Windows updates. Downloads never contain personal state. */
import {createHash,createPublicKey,verify as rsaVerify,randomUUID} from 'node:crypto';
import {createReadStream,createWriteStream,existsSync,mkdirSync,readFileSync,writeFileSync,renameSync,copyFileSync,unlinkSync} from 'node:fs';
import {join,resolve,sep,dirname} from 'node:path';
import {spawn} from 'node:child_process';
import {pipeline} from 'node:stream/promises';
import {Readable,Transform} from 'node:stream';

export const REPOSITORY='ASK-022/video-copy-studio-skill';
export const MIRRORS=['https://fastly.jsdelivr.net','https://gcore.jsdelivr.net'];
export const FEEDS=[...MIRRORS.map(host=>`${host}/gh/${REPOSITORY}@main/releases/contenthub/latest.json`),`https://raw.githubusercontent.com/${REPOSITORY}/main/releases/contenthub/latest.json`];
const publicKey=JSON.parse(readFileSync(new URL('./contenthub-update-public.json',import.meta.url),'utf8').replace(/^\uFEFF/,''));
export const canonical=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a<b?-1:a>b?1:0)):v);
export function version(value){if(typeof value!=='string'||!/^\d{1,5}\.\d{1,5}\.\d{1,5}$/.test(value))throw Error('version');return value.split('.').map(Number);}
export function newer(a,b){const x=version(a),y=version(b);return x.some((v,i)=>v!==y[i]&&x.slice(0,i).every((v,j)=>v===y[j])&&v>y[i]);}
export function verifyManifest(envelope,key=publicKey){
  const payload=envelope.payload;
  const pub=createPublicKey({key:{kty:'RSA',n:Buffer.from(key.modulus,'base64').toString('base64url'),e:'AQAB'},format:'jwk'});
  if(!rsaVerify('RSA-SHA256',Buffer.from(canonical(payload)),pub,Buffer.from(envelope.signature,'base64')))throw Error('signature');
  if(payload.format!=='contenthub-desktop-update/v1'||payload.repository!==REPOSITORY||payload.resource_contract!==1)throw Error('product');
  version(payload.version);version(payload.min_version);
  if(!Array.isArray(payload.packages)||!payload.packages.length||payload.packages.length>20)throw Error('packages');
  for(const item of payload.packages){
    if(item.base_version!=='*')version(item.base_version);
    if(!/^ContentHub-[A-Za-z0-9._-]+\.zip$/.test(item.name)||!/^[0-9a-f]{64}$/.test(item.sha256)||!Number.isSafeInteger(item.bytes)||item.bytes<=0||item.bytes>=2*1024**3||!Array.isArray(item.parts)||!item.parts.length||item.parts.length>150)throw Error('package');
    let bytes=0;
    for(const part of item.parts){
      if(!/^ContentHub-[A-Za-z0-9._-]+\.part\d{3}$/.test(part.name)||!/^[0-9a-f]{64}$/.test(part.sha256)||!Number.isSafeInteger(part.bytes)||part.bytes<=0||part.bytes>19*1024**2)throw Error('part');
      const tag=`contenthub-v${payload.version}`;
      const urls=[...MIRRORS.map(host=>`${host}/gh/${REPOSITORY}@${tag}/releases/contenthub/files/${part.name}`),`https://github.com/${REPOSITORY}/releases/download/${tag}/${part.name}`];
      if(JSON.stringify(part.urls)!==JSON.stringify(urls))throw Error('source');bytes+=part.bytes;
    }
    if(bytes!==item.bytes)throw Error('size');
  }
  return payload;
}
const json=path=>JSON.parse(readFileSync(path,'utf8').replace(/^\uFEFF/,''));
function save(path,value){mkdirSync(dirname(path),{recursive:true});writeFileSync(path+'.tmp',JSON.stringify(value));renameSync(path+'.tmp',path);}
const digest=async path=>{const hash=createHash('sha256');for await(const chunk of createReadStream(path))hash.update(chunk);return hash.digest('hex');};
export async function downloadPackage(item,directory,{request=fetch,progress=()=>{}}={}){
  mkdirSync(directory,{recursive:true});const archive=join(directory,item.name);let received=0;
  for(const part of item.parts){
    const file=join(directory,part.name);
    if(existsSync(file)&&await digest(file)===part.sha256){received+=part.bytes;progress(received/item.bytes*100);continue;}
    let completed=false;
    for(const url of part.urls){
      try{
        const response=await request(url,{signal:AbortSignal.timeout(180000),headers:{'user-agent':'ContentHub-Desktop-Update'}});
        if(!response.ok||!response.body)throw Error('download');let size=0;const hash=createHash('sha256');
        const bounded=new Transform({transform(chunk,_,next){size+=chunk.length;if(size>part.bytes)return next(Error('size'));hash.update(chunk);progress((received+size)/item.bytes*100);next(null,chunk);}});
        await pipeline(Readable.fromWeb(response.body),bounded,createWriteStream(file+'.tmp'));
        if(size!==part.bytes||hash.digest('hex')!==part.sha256)throw Error('checksum');renameSync(file+'.tmp',file);completed=true;break;
      }catch{try{unlinkSync(file+'.tmp');}catch{}}
    }
    if(!completed)throw Error('download');received+=part.bytes;
  }
  const out=createWriteStream(archive+'.tmp');
  try{for(const part of item.parts)for await(const chunk of createReadStream(join(directory,part.name)))if(!out.write(chunk))await new Promise(r=>out.once('drain',r));out.end();await new Promise((r,f)=>{out.once('finish',r);out.once('error',f);});}
  catch(error){out.destroy();throw error;}
  if(await digest(archive+'.tmp')!==item.sha256)throw Error('checksum');renameSync(archive+'.tmp',archive);return archive;
}
export function createContentHubUpdates({root,dataDir,version:currentVersion,onState=()=>{},prepareRestart,beforeInstall,quit,showMessage,request=fetch,start=spawn,feeds=FEEDS,key=publicKey}){
  root=resolve(root);dataDir=resolve(dataDir);let envelope=null,selected=null,archive=null,pending=null,installing=false,timer=null;
  let state={status:'idle',version:currentVersion,channel:'stable',availableVersion:null,progress:0,checkedAt:null,error:null};
  try{const last=json(join(dataDir,'desktop-update-result.json'));if(last.status==='rolled-back')state={...state,error:'rolled-back'};}catch{}
  const publish=change=>{state={...state,...change};onState({...state});return {...state};};
  const snapshot=()=>({...state});
  async function check(){
    if(['ready','installing'].includes(state.status))return snapshot();
    if(pending)return pending;
    pending=(async()=>{
      publish({status:'checking',error:null});let payload;
      for(const url of feeds){try{const r=await request(url,{signal:AbortSignal.timeout(12000),headers:{'user-agent':'ContentHub-Desktop-Update','cache-control':'no-cache'}});if(!r.ok)throw Error('feed');const body=await r.text();if(body.length>256000)throw Error('size');const found=JSON.parse(body);const valid=verifyManifest(found,key);if(!payload||newer(valid.version,payload.version)){payload=valid;envelope=found;}}catch{}}
      if(!payload)return publish({status:'error',error:'check-failed',checkedAt:Date.now()});
      if(!newer(payload.version,currentVersion))return publish({status:'current',checkedAt:Date.now(),error:null});
      if(newer(payload.min_version,currentVersion))return publish({status:'error',error:'full-installer-required',checkedAt:Date.now()});
      selected=payload.packages.find(p=>p.base_version===currentVersion)||payload.packages.find(p=>p.base_version==='*');
      if(!selected)return publish({status:'error',error:'full-installer-required'});
      publish({status:'downloading',availableVersion:payload.version,progress:0});
      try{archive=await downloadPackage(selected,join(dataDir,'updates','downloads',payload.version),{request,progress:value=>publish({progress:Math.min(100,value)})});return publish({status:'ready',progress:100,checkedAt:Date.now()});}
      catch{return publish({status:'error',error:'download-failed'});}
    })().finally(()=>{pending=null;});return pending;
  }
  async function perform(operation){
    if(installing||(operation!=='rollback'&&state.status!=='ready'))return {ok:false,error:'not-ready'};
    installing=true;
    try{
      if(dataDir===root||dataDir.startsWith(root+sep))throw Error('data-inside-install');
      if(operation==='rollback'&&!json(join(root,'current.json')).previous)return {ok:false,error:'no-previous-version'};
      const ready=await prepareRestart();if(!ready.ok){publish({error:ready.error});return ready;}
      const jobPath=join(dataDir,'updates','requests',randomUUID()+'.json');
      save(jobPath,{operation,root,data:dataDir,parent_pid:process.pid,parent_exe:process.execPath,...(operation==='rollback'?{}:{envelope,package:selected.name,archive})});
      const agent=join(dataDir,'updates','agents',randomUUID()+'.exe');mkdirSync(dirname(agent),{recursive:true});copyFileSync(join(root,'ContentHub.exe'),agent);
      await beforeInstall();
      const child=start(agent,['--apply',jobPath],{env:{...process.env,ASKFILM_USER_DATA:dataDir},detached:true,windowsHide:true,stdio:'ignore'});
      await new Promise((done,fail)=>{child.once('spawn',done);child.once('error',fail);});child.unref();publish({status:'installing'});quit();return {ok:true};
    }catch(error){publish({status:archive?'ready':'error',error:'install-failed'});return {ok:false,error:'install-failed'};}
    finally{installing=false;}
  }
  return {packaged:true,snapshot,check,restart:()=>perform('update'),rollback:()=>perform('rollback'),
    channel:()=> 'stable',setChannel:()=>{},installAtLaunch:async()=>({installing:false,dismiss:()=>{}}),
    async manualCheck(){const value=await check();await showMessage({type:value.status==='error'?'warning':'info',message:value.status==='ready'?`新版 ${value.availableVersion} 已准备好`:value.status==='current'?'当前已是最新版本':'暂未完成更新检查',detail:value.status==='ready'?'点击顶部“更新并重启”。资料、Key 和模型继续保留；启动失败会恢复旧版。':value.error||''});},
    schedule(){timer=setTimeout(()=>void check(),30000);timer.unref?.();},close(){if(timer)clearTimeout(timer);},
  };
}
