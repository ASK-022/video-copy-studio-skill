"""Single-purpose runner draft: reassemble verified public software, upload one EXE.

No EXE execution, deletion, clobber, release creation/publication, tag/ref update,
feed change, personal credential input, artifacts/cache, or automatic retry.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,math,os,re,sys,urllib.request,urllib.parse

REPO='ASK-022/video-copy-studio-skill';ACTOR='ASK-022';VERSION='1.2.3';DEV='1.2.3-dev.2'
SOURCE='993d63870cd734d23177d6204f262918fdd5291c19df3ebba4579c57a23099a7'
RELEASE=432615900;COMMIT='0fa95cfeead68ccee142566a615a6d55df75b3ea';TAG='contenthub-v1.2.3'
NAME='ContentHub-Setup-v1.2.3-x64.exe';SIZE=526209783;SHA='3604ed0b50249c60636143471c0c30b485c04030314fec872510c24988d1ab48';CHUNK=16*1024**2
WORKFLOW='.github/workflows/contenthub-installer-recovery-v123.yml'

def need(v,message):
 if not v:raise RuntimeError(message)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe_name(n):need(type(n)is str and n and Path(n).name==n and not any(c in n for c in '/\\:\0\r\n') and n not in {'.','..'},'Unsafe public software filename');return n
def chunk_layout(item):
 need(type(item['bytes'])is int and 0<item['bytes']<2*1024**3,'Invalid public software size')
 count=math.ceil(item['bytes']/CHUNK)
 return [{'index':i,'name':safe_name(item['name'])+f'.part{i:03d}','bytes':min(CHUNK,item['bytes']-(i-1)*CHUNK)} for i in range(1,count+1)]
def validate_descriptor(d):
 need(set(d)=={'format','repository','version','development_version','source_sha256','release_id','release_commit','tag','installer','prior_assets','chunk_bytes','chunks'},'Only pure public descriptor fields are accepted')
 need(d['format']=='contenthub/runner-installer-descriptor/v1' and d['repository']==REPO and d['version']==VERSION and d['development_version']==DEV and d['source_sha256']==SOURCE and d['release_id']==RELEASE and d['release_commit']==COMMIT and d['tag']==TAG,'Wrong fixed recovery release/source')
 need(d['installer']=={'name':NAME,'bytes':SIZE,'sha256':SHA} and d['chunk_bytes']==CHUNK and d['chunks']==chunk_layout(d['installer']) and len(d['chunks'])==32,'Exact original installer/chunk layout required')
 rows=d['prior_assets'];need(type(rows)is list and len(rows)==47 and len({r['name'] for r in rows})==47 and all(set(r)=={'name','bytes','sha256'} for r in rows),'Exactly47 unique pure public prior descriptors required')
 for r in rows: safe_name(r['name']);need(r['name']!=NAME and type(r['bytes'])is int and 0<r['bytes']<2*1024**3 and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Invalid prior public software descriptor')
 return d
def fresh(stamp,clock=None):
 try:issued=datetime.fromisoformat(stamp['issued_at_utc'].replace('Z','+00:00'))
 except (ValueError,TypeError):raise RuntimeError('Unfilled or invalid issued_at')
 need(issued.tzinfo is not None,'Issued time must have UTC offset');age=((clock or datetime.now(timezone.utc))-issued).total_seconds();need(0<=age<=180,'Expired/future root stamp; stop without upload');return age
def validate_event(stamp,descriptor_sha,env,event):
 need(set(stamp)=={'format','action','repository','branch_ref','expected_event_before','actor','issued_at_utc','nonce','source_sha256','release_id','installer_sha256','descriptor_sha256'},'Unexpected permit fields')
 need(stamp['format']=='contenthub/runner-installer-stamp/v1' and stamp['action']=='upload-one-missing-installer-only' and stamp['repository']==REPO and stamp['actor']==ACTOR and stamp['source_sha256']==SOURCE and stamp['release_id']==RELEASE and stamp['installer_sha256']==SHA and stamp['descriptor_sha256']==descriptor_sha,'Wrong root stamp binding')
 need(stamp['branch_ref'].startswith('refs/heads/recovery/contenthub-v1.2.3-') and re.fullmatch('[A-Za-z0-9._/-]+',stamp['branch_ref']) and '__' not in stamp['branch_ref'] and re.fullmatch('[a-f0-9]{40}',stamp['expected_event_before']) and stamp['expected_event_before']!='0'*40 and re.fullmatch('[a-f0-9]{32}',stamp['nonce']),'Recovery branch/head/nonce placeholders are not armed')
 need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REF')==stamp['branch_ref'] and env.get('GITHUB_ACTOR')==ACTOR and env.get('GITHUB_TRIGGERING_ACTOR')==ACTOR and env.get('GITHUB_RUN_ATTEMPT')=='1','Wrong runner repo/ref/event/actor/attempt')
 need(env.get('EXPECTED_RECOVERY_REF')==stamp['branch_ref'] and env.get('EXPECTED_EVENT_BEFORE')==stamp['expected_event_before'],'Workflow literal branch/parent differs from stamp')
 sha=env.get('GITHUB_SHA','');need(re.fullmatch('[a-f0-9]{40}',sha) and env.get('GITHUB_WORKFLOW_SHA')==sha,'Workflow and pushed source commit must coincide')
 need(env.get('GITHUB_WORKFLOW_REF')==REPO+'/'+WORKFLOW+'@'+stamp['branch_ref'],'Only the dedicated one-shot workflow may invoke this script')
 need(event.get('ref')==stamp['branch_ref'] and event.get('before')==stamp['expected_event_before'] and event.get('after')==sha and event.get('head_commit',{}).get('id')==sha and event.get('repository',{}).get('full_name')==REPO and event.get('sender',{}).get('login')==ACTOR,'Actual GitHub push event differs from armed root stamp')
 need(event.get('created') is False and event.get('deleted') is False and event.get('forced') is False,'Only the single normal push after the chunk commit is allowed');fresh(stamp)
def assemble(d,folder,output):
 folder=Path(folder).resolve();output=Path(output);need(output.name==NAME and not output.exists(),'Recovery output must be a new fixed software EXE')
 sha=hashlib.sha256();total=0
 with output.open('xb') as target:
  for row in d['chunks']:
   p=folder/safe_name(row['name']);need(p.is_file() and not p.is_symlink() and p.resolve().parent==folder and p.stat().st_size==row['bytes'],'Missing, redirected, or wrong-size exact chunk')
   with p.open('rb') as source:
    while raw:=source.read(1024**2):target.write(raw);sha.update(raw);total+=len(raw)
 need(total==d['installer']['bytes'] and sha.hexdigest()==d['installer']['sha256'],'Reassembled installer full size/SHA differs');return output
def native_state(release,d):
 need(release.get('id')==RELEASE and release.get('tag_name')==TAG and release.get('target_commitish')==COMMIT and release.get('draft') is True and release.get('prerelease') is False,'Exact owned draft changed')
 rows=release.get('assets',[]);assets={r['name']:r for r in rows};need(len(assets)==len(rows),'Duplicate native assets')
 prior={r['name']:r for r in d['prior_assets']};need(set(assets) in (set(prior),set(prior)|{NAME}),'Unknown/missing native software asset')
 for name,e in prior.items():
  r=assets[name];need(r.get('state')=='uploaded' and r.get('size')==e['bytes'] and r.get('digest')=='sha256:'+e['sha256'],'Prior47 native assets changed or unresolved')
 if NAME in assets:
  r=assets[NAME];e=d['installer'];need(r.get('state')=='uploaded' and r.get('size')==e['bytes'] and r.get('digest')=='sha256:'+e['sha256'],'Existing installer is a starter/mismatch; never clobber');return 'exact-installer-already-present'
 return 'only-installer-missing'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise RuntimeError('Official recovery API redirect is forbidden')
class OfficialAPI:
 def __init__(self,token):
  need(token and not any(c in token for c in '\r\n\0'),'Missing/invalid ephemeral job token');self.token=token;self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 def request(self,method,url,body=None,size=None):
  u=urllib.parse.urlsplit(url);expected='api.github.com' if method=='GET' else 'uploads.github.com';need(u.scheme=='https' and u.hostname==expected and u.port is None and u.username is None and u.password is None and not u.fragment,'Only exact official recovery HTTPS hosts')
  headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','User-Agent':'ContentHub-one-shot-installer-recovery','X-GitHub-Api-Version':'2022-11-28'}
  if size is not None:headers.update({'Content-Type':'application/octet-stream','Content-Length':str(size)})
  with self.opener.open(urllib.request.Request(url,data=body,headers=headers,method=method),timeout=90) as response:
   need(response.status==(200 if method=='GET' else 201),'Official recovery API status differs');raw=response.read(2*1024**2+1);need(len(raw)<=2*1024**2,'Official metadata size bound');return json.loads(raw)
 def native(self):return self.request('GET',f'https://api.github.com/repos/{REPO}/releases/{RELEASE}')
 def upload(self,path,size):
  with Path(path).open('rb') as body:return self.request('POST',f'https://uploads.github.com/repos/{REPO}/releases/{RELEASE}/assets?name='+urllib.parse.quote(NAME,safe=''),body,size)
def recover(d,stamp,output,api):
 state=native_state(api.native(),d)
 if state=='exact-installer-already-present':return {'status':'no-op-exact-native-installer','root_full48_gate_still_required':True}
 fresh(stamp) # last time check before the sole permitted repo mutation
 try:
  ack=api.upload(output,d['installer']['bytes']);need(ack.get('name')==NAME and ack.get('state')=='uploaded' and ack.get('size')==d['installer']['bytes'] and ack.get('digest')=='sha256:'+d['installer']['sha256'],'Upload response lacks exact native installer ACK')
 except Exception:
  # One read-only reconciliation, no retransmission or remote deletion.
  need(native_state(api.native(),d)=='exact-installer-already-present','Upload failed without exact native ACK; root inspection required')
 need(native_state(api.native(),d)=='exact-installer-already-present','Post-upload exact48 native ACK failed')
 return {'status':'exact-native-installer-added','root_full48_gate_still_required':True}
def main():
 p=argparse.ArgumentParser();p.add_argument('--descriptor',type=Path,required=True);p.add_argument('--stamp',type=Path,required=True);p.add_argument('--chunks',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 raw=a.descriptor.read_bytes();d=validate_descriptor(json.loads(raw));stamp=read(a.stamp);event=read(os.environ['GITHUB_EVENT_PATH']);validate_event(stamp,digest(raw),os.environ,event)
 output=assemble(d,a.chunks,a.output);fresh(stamp);api=OfficialAPI(os.environ.get('GH_TOKEN',''));result=recover(d,stamp,output,api)
 print(json.dumps({'ok':True,**result,'name':NAME,'bytes':d['installer']['bytes'],'sha256':d['installer']['sha256'],'release_id':RELEASE,'publication_performed':False,'root_disable_this_workflow_after_full48_ACK':True}))
if __name__=='__main__':
 try:main()
 except Exception as error:print(json.dumps({'ok':False,'error_type':type(error).__name__,'reason':str(error) if type(error)is RuntimeError else 'transport-or-input-error','upload_or_verification_failed':True,'root_inspection_required':True}),file=sys.stderr);raise SystemExit(1)
