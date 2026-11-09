"""One-shot public-software assembler. The only remote write is asset POST.

It never executes software, publishes, deletes, changes refs/feeds or registers
anything locally. Plan/code bytes and the nonce are fixed by the workflow.
"""
from pathlib import Path, PurePosixPath
import base64, hashlib, hmac, json, os, re, shutil, time
import urllib.error, urllib.parse, urllib.request

REPO='ASK-022/video-copy-studio-skill'
VERSION='1.4.0'
PUBLIC_KEY_SHA='f8edbc1fb4b2f82d3d1cc47c86eb35f4ace7f143bbe845a1c561d1d932afd2c0'
PART_BYTES=6*1024**2
TAG='contenthub-v'+VERSION
class Failure(RuntimeError):pass
def need(value,message):
    if not value:raise Failure(message)
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def file_sha(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
def git_blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def name_ok(value):return isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9_.-]+',value)) and value not in ('.','..')
def sha_ok(value):return isinstance(value,str) and bool(re.fullmatch('[a-f0-9]{64}',value))
def commit_ok(value):return isinstance(value,str) and bool(re.fullmatch('[a-f0-9]{40}',value))
def exact_asset(actual,row):return actual.get('name')==row['name'] and actual.get('state')=='uploaded' and actual.get('size')==row['bytes'] and actual.get('digest')=='sha256:'+row['sha256']
def native_budget(total,existing,reserve=20):
    """Remaining normal calls after initial owned(), plus a fixed safety reserve."""
    need(type(total) is int and type(existing) is int and 0<=existing<=total<=158,'Invalid native budget composition')
    pages=lambda count:count//100+1
    return sum(6+pages(existing+i) for i in range(total-existing))+4+pages(total)+reserve

def verify_envelope(raw,key_raw,expected_sha,expected_version=VERSION):
    need(digest(raw)==expected_sha and digest(key_raw)==PUBLIC_KEY_SHA,'Envelope/public trust key bytes changed')
    envelope=json.loads(raw);key=json.loads(key_raw);payload=envelope['payload']
    signature=base64.b64decode(envelope['signature'],validate=True);modulus=int.from_bytes(base64.b64decode(key['modulus'],validate=True),'big')
    need(key['exponent']==65537 and modulus.bit_length()==3072 and len(signature)==384 and int.from_bytes(signature,'big')<modulus,'Signature/key format differs')
    message=pow(int.from_bytes(signature,'big'),65537,modulus).to_bytes(384,'big')
    encoded=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(canonical(payload)).digest()
    need(hmac.compare_digest(message,b'\0\1'+b'\xff'*(384-len(encoded)-3)+b'\0'+encoded),'Production RSA signature rejected')
    need(payload.get('format')=='contenthub-desktop-update/v1' and payload.get('repository')==REPO and payload.get('version')==expected_version and payload.get('resource_contract')==1,'Signed product/version differs')
    need(isinstance(payload.get('min_version'),str) and bool(re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}',payload['min_version'])) and tuple(map(int,payload['min_version'].split('.')))<=tuple(map(int,expected_version.split('.'))),'Signed minimum version differs')
    need(len(payload.get('packages',[]))==1 and payload['packages'][0].get('base_version')=='*','Only the signed full program package is allowed')
    package=payload['packages'][0];need(package['name']==f'ContentHub-App-v{expected_version}-x64.zip' and sha_ok(package['sha256']) and type(package['bytes']) is int and 0<package['bytes']<2*1024**3,'Signed full ZIP differs')
    parts=package.get('parts',[]);need(1<=len(parts)<=150,'Signed part count differs');total=0
    for index,part in enumerate(parts,1):
        need(part['name']==package['name']+f'.part{index:03d}' and type(part['bytes']) is int and 0<part['bytes']<=PART_BYTES and sha_ok(part['sha256']),'Signed part metadata differs')
        urls=[f'https://{host}/gh/{REPO}@contenthub-v{expected_version}/releases/contenthub/files/{part["name"]}' for host in ('fastly.jsdelivr.net','gcore.jsdelivr.net')]+[f'https://github.com/{REPO}/releases/download/contenthub-v{expected_version}/{part["name"]}']
        need(part['urls']==urls,'Signed part sources differ');total+=part['bytes']
    need(total==package['bytes'],'Signed part byte sum differs');return payload

def validate_plan(plan,signature_check=verify_envelope):
    need(plan.get('format')=='contenthub/one-shot-software-cache/v1' and plan.get('repository')==REPO and plan.get('version')==VERSION and plan.get('tag')==TAG,'Wrong cache plan product')
    nonce=plan.get('nonce');need(isinstance(nonce,str) and bool(re.fullmatch('[a-f0-9]{32}',nonce)),'Invalid one-shot nonce')
    prefix=f'releases/contenthub/staging/{VERSION}/{nonce}/'
    need(plan.get('cache_prefix')==prefix and plan.get('branch')==f'release/contenthub-v{VERSION}-artifacts-{nonce}','Unexpected fixed branch/prefix')
    need(type(plan.get('release_id')) is int and plan['release_id']>0 and commit_ok(plan.get('stage_commit')) and sha_ok(plan.get('source_sha256')) and sha_ok(plan.get('installer_sha256')) and sha_ok(plan.get('release_body_sha256')),'Draft/source identity incomplete')
    need(isinstance(plan.get('standalone_latest'),str) and bool(re.fullmatch(r'v\d+\.\d+\.\d+',plan['standalone_latest'])),'Independent latest pin missing')
    need(sha_ok(plan.get('runner_sha256')) and plan.get('runner_path')==prefix+'runner.py' and plan.get('plan_path')==prefix+'plan.json','Pinned public runner paths differ')
    raw=base64.b64decode(plan['signed_envelope_base64'],validate=True);key=base64.b64decode(plan['public_key_base64'],validate=True)
    need(len(raw)<=256000 and len(key)<=8192,'Oversized public signature inputs')
    payload=signature_check(raw,key,plan['envelope_sha256']);package=payload['packages'][0];parts={p['name']:p for p in package['parts']}
    expected={f'ContentHub-Setup-v{VERSION}-x64.exe','update.json',package['name'],f'ContentHub-Offline-Install-v{VERSION}.exe','VC_redist.x64.exe','contenthub-resources-r1.json','README-ContentHub-Offline.txt','SHA256SUMS-OFFLINE.txt'}|set(parts)
    need(plan.get('publication_mode','canonical-offline') in ('canonical-offline','program-update-only'),'Unknown publication mode')
    if plan.get('publication_mode')=='program-update-only':expected={f'ContentHub-Setup-v{VERSION}-x64.exe','update.json',package['name'],'contenthub-resources-r1.json'}|set(parts)
    rows=plan.get('assets',[]);need(len(rows)==len(expected) and {r.get('name') for r in rows}==expected,'Exact public software allowlist differs')
    assets={r['name']:r for r in rows};need(sum(r['bytes'] for r in rows)<8*1024**3,'Oversized public software plan')
    for row in rows:
        need(name_ok(row['name']) and type(row.get('bytes')) is int and 0<row['bytes']<2*1024**3 and sha_ok(row.get('sha256')),'Invalid public asset metadata')
        sources=row.get('sources',[]);need(1<=len(sources)<=150 and sum(s['bytes'] for s in sources)==row['bytes'],'Asset cache recipe size differs')
        for source in sources:
            path=source.get('git_path');need(type(source.get('bytes')) is int and 0<source['bytes']<=PART_BYTES and sha_ok(source.get('sha256')) and commit_ok(source.get('git_blob_sha1')),'Invalid bounded public cache source')
            need(isinstance(path,str) and not PurePosixPath(path).is_absolute() and '..' not in PurePosixPath(path).parts,'Unsafe public cache path')
            if source.get('ref')=='stage':
                if path==f'releases/contenthub/v{VERSION}.json':need(row['name']=='update.json' and source['sha256']==plan['envelope_sha256'],'Unexpected stage envelope source')
                else:
                    name=path.removeprefix('releases/contenthub/files/');part=parts.get(name)
                    need(path=='releases/contenthub/files/'+name and part is not None and all(source[k]==part[k] for k in ('bytes','sha256')),'Unexpected signed stage source')
            else:need(source.get('ref')=='cache' and path.startswith(prefix+'cache/') and name_ok(path[len(prefix+'cache/'):]),'Cache source escaped this nonce')
        if row['name'] in parts:need(row['bytes']==parts[row['name']]['bytes'] and row['sha256']==parts[row['name']]['sha256'] and len(sources)==1 and sources[0]['git_path']=='releases/contenthub/files/'+row['name'] and sources[0]['ref']=='stage','Signed part asset differs')
    need(assets[package['name']]['bytes']==package['bytes'] and assets[package['name']]['sha256']==package['sha256'],'Full ZIP asset differs from signed package')
    need([(s['git_path'],s['bytes'],s['sha256'],s['ref']) for s in assets[package['name']]['sources']]==[('releases/contenthub/files/'+p['name'],p['bytes'],p['sha256'],'stage') for p in package['parts']],'Full ZIP must reuse its exact signed Git blobs')
    need(assets[f'ContentHub-Setup-v{VERSION}-x64.exe']['sha256']==plan['installer_sha256'] and assets['update.json']['sha256']==plan['envelope_sha256'],'Installer/envelope allowlist pin differs')
    return assets,payload

def validate_environment(plan,env):
    need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REF_NAME')==plan['branch'] and commit_ok(env.get('GITHUB_SHA')) and env.get('GITHUB_RUN_ATTEMPT','1')=='1' and env.get('CONTENTHUB_NONCE')==plan['nonce'],'Wrong repository/branch/event/one-shot run')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*_):raise Failure('Redirect refused; credentials stay at the official GitHub endpoint')
class Transport:
    def __init__(self,token):
        need(token and not any(c.isspace() for c in token),'Official Actions token missing');self.token=token;self.opener=urllib.request.build_opener(NoRedirect());self.remaining=None;self.native_requests=0
    def record_budget(self,response):
        self.native_requests+=1
        value=response.headers.get('X-RateLimit-Remaining')
        self.remaining=int(value) if isinstance(value,str) and value.isdigit() else None
    def get(self,path):
        need(isinstance(path,str) and path.startswith('/') and not path.startswith('//'),'Unsafe native API path')
        request=urllib.request.Request('https://api.github.com/repos/'+REPO+path,headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','User-Agent':'ContentHub-One-Shot-Software-Assembler'})
        try:
            with self.opener.open(request,timeout=120) as response:self.record_budget(response);return json.loads(response.read(4*1024*1024+1))
        except urllib.error.HTTPError as error:raise Failure('Official GitHub GET failed HTTP '+str(error.code)) from None
    def upload(self,release_id,row,path):
        url=f'https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets?name='+urllib.parse.quote(row['name'],safe='')
        with Path(path).open('rb') as source:
            request=urllib.request.Request(url,data=source,method='POST',headers={'Authorization':'Bearer '+self.token,'Content-Length':str(row['bytes']),'Content-Type':'application/octet-stream','User-Agent':'ContentHub-One-Shot-Software-Assembler'})
            try:
                with self.opener.open(request,timeout=1800) as response:self.record_budget(response);return json.loads(response.read(1024*1024+1))
            except urllib.error.HTTPError as error:raise Failure('Official asset POST failed HTTP '+str(error.code)) from None
    def download(self,url,path,limit):
        need(url.startswith('https://raw.githubusercontent.com/'+REPO+'/') and '?' not in url and '#' not in url,'Unexpected public cache URL')
        request=urllib.request.Request(url,headers={'User-Agent':'ContentHub-Public-Software-Assembler'})
        with self.opener.open(request,timeout=180) as response,Path(path).open('xb') as target:
            size=0
            while block:=response.read(1024*1024):size+=len(block);need(size<=limit,'Oversized public cache response');target.write(block)

class Assembler:
    def __init__(self,plan,env,transport,work,signature_check=verify_envelope):
        self.assets,self.payload=validate_plan(plan,signature_check);validate_environment(plan,env)
        self.plan,self.env,self.transport=plan,env,transport;self.work=Path(work).resolve();need(not self.work.exists(),'Preserve existing run output');self.work.mkdir();(self.work/'cache').mkdir();(self.work/'assets').mkdir();self.downloaded={};self.uploads=0;self.recovered=0
    def remote_assets(self):
        rows=[]
        for page in range(1,5):
            found=self.transport.get(f'/releases/{self.plan["release_id"]}/assets?per_page=100&page={page}');need(isinstance(found,list),'Native asset response invalid');rows.extend(found)
            if len(found)<100:break
        need(len(rows)==len({r.get('name') for r in rows}),'Duplicate native asset names')
        result={r['name']:r for r in rows};need(set(result)<=set(self.assets),'Unknown native asset; never delete or clobber')
        for name,row in result.items():need(exact_asset(row,self.assets[name]),'Existing native asset bytes differ; never clobber')
        return result
    def owned(self):
        p=self.plan;release=self.transport.get('/releases/'+str(p['release_id']))
        need(release.get('id')==p['release_id'] and release.get('tag_name')==TAG and release.get('draft') is True and release.get('prerelease') is False and release.get('target_commitish')==p['stage_commit'] and digest(release.get('body','').encode())==p['release_body_sha256'],'Exact owned draft changed')
        tag=self.transport.get('/git/ref/tags/'+TAG);need(tag.get('object',{}).get('type')=='commit' and tag['object']['sha']==p['stage_commit'],'Immutable tag changed')
        branch=self.transport.get('/git/ref/heads/'+p['branch']);need(branch.get('object',{}).get('sha')==self.env['GITHUB_SHA'],'Cache branch advanced; stale run must stop')
        need(self.transport.get('/releases/latest').get('tag_name')==p['standalone_latest'],'Independent latest changed')
        return self.remote_assets()
    def need_budget(self,existing,scope_already_done=False):
        missing=len(self.assets)-len(existing)
        if not missing:return
        required=native_budget(len(self.assets),len(existing))
        if scope_already_done:required-=4+len(existing)//100+1
        remaining=getattr(self.transport,'remaining',None)
        need(type(remaining) is int and remaining>=required,'Rate limit budget insufficient or unavailable before asset POST: required '+str(required)+', remaining '+str(remaining))
    def source_file(self,row):
        key=(row['sha256'],row['bytes']);path=self.work/'cache'/row['sha256']
        if key in self.downloaded:need(path.stat().st_size==row['bytes'] and file_sha(path)==row['sha256'],'Retained public chunk changed');return path
        commit=self.plan['stage_commit'] if row['ref']=='stage' else self.env['GITHUB_SHA'];url=f'https://raw.githubusercontent.com/{REPO}/{commit}/'+row['git_path']
        for attempt in range(3):
            temporary=path.with_name(path.name+f'.attempt{attempt}.tmp')
            try:
                self.transport.download(url,temporary,row['bytes']);need(temporary.stat().st_size==row['bytes'] and file_sha(temporary)==row['sha256'],'Public cache chunk bytes differ')
                with temporary.open('rb') as source:
                    h=hashlib.sha1(b'blob '+str(row['bytes']).encode()+b'\0')
                    for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
                need(h.hexdigest()==row['git_blob_sha1'],'Public Git blob bytes differ');temporary.replace(path);self.downloaded[key]=True;return path
            except Exception:
                if attempt==2:raise Failure('Bounded public cache GET failed for approved software') from None
                time.sleep(1+attempt)
        raise Failure('Cache download incomplete')
    def materialize(self,row):
        destination=self.work/'assets'/row['name'];h=hashlib.sha256();total=0
        with destination.open('xb') as out:
            for source in row['sources']:
                with self.source_file(source).open('rb') as incoming:
                    for block in iter(lambda:incoming.read(1024*1024),b''):out.write(block);total+=len(block);need(total<=row['bytes'],'Oversized assembled asset');h.update(block)
        need(total==row['bytes'] and h.hexdigest()==row['sha256'] and file_sha(destination)==row['sha256'],'Assembled whole asset differs');return destination
    def run(self):
        existing=self.owned()
        self.need_budget(existing)
        for index,(name,row) in enumerate(self.assets.items()):
            if name in existing:continue
            path=self.materialize(row);existing=self.owned()
            if name in existing:continue
            self.need_budget(existing,scope_already_done=True)
            try:
                answer=self.transport.upload(self.plan['release_id'],row,path);need(exact_asset(answer,row) and type(answer.get('id')) is int and answer['id']>0,'Native POST checksum/identity differs');self.uploads+=1
            except Exception:
                # Never blindly repeat an unknown POST. A matching native GET is
                # the only success recovery; otherwise preserve the failed run.
                found=self.owned()
                if name not in found:raise Failure('Unknown asset POST result; inspect native state before a newly authorized run') from None
                answer=found[name];self.recovered+=1
            actual=self.transport.get('/releases/assets/'+str(answer['id']));need(exact_asset(actual,row) and actual.get('id')==answer['id'],'Uploaded asset lacks exact native readback');existing[name]=actual
            print('NATIVE_ASSET_ACK '+name,flush=True)
        final=self.owned();need(set(final)==set(self.assets),'Exact draft asset set incomplete')
        proof={'format':'contenthub/one-shot-software-cache-result/v1','ok':True,'version':VERSION,'nonce':self.plan['nonce'],'release_id':self.plan['release_id'],'stage_commit':self.plan['stage_commit'],'cache_commit':self.env['GITHUB_SHA'],'source_sha256':self.plan['source_sha256'],'installer_sha256':self.plan['installer_sha256'],'envelope_sha256':self.plan['envelope_sha256'],'native_assets':len(final),'new_uploads':self.uploads,'unknown_posts_recovered_by_native_readback':self.recovered,'public_chunks_downloaded_once':len(self.downloaded),'published':False,'ref_or_feed_or_delete_writes':0}
        (self.work/'result.json').write_bytes(canonical(proof));print(json.dumps(proof),flush=True);return proof

def main():
    env=dict(os.environ);nonce=env.get('CONTENTHUB_NONCE','');need(bool(re.fullmatch('[a-f0-9]{32}',nonce)) and commit_ok(env.get('GITHUB_SHA')),'Missing pinned Actions identity')
    runner=Path(__file__).read_bytes();need(digest(runner)==env.get('CONTENTHUB_RUNNER_SHA'),'Runner source pin differs')
    prefix=f'releases/contenthub/staging/{VERSION}/{nonce}/';url=f'https://raw.githubusercontent.com/{REPO}/{env["GITHUB_SHA"]}/{prefix}plan.json'
    public=urllib.request.build_opener(NoRedirect())
    with public.open(url,timeout=120) as response:raw=response.read(2*1024*1024+1)
    need(len(raw)<=2*1024*1024 and digest(raw)==env.get('CONTENTHUB_PLAN_SHA'),'Public plan SHA/size differs')
    plan=json.loads(raw);need(plan.get('runner_sha256')==digest(runner),'Plan runner pin differs')
    assembler=Assembler(plan,env,Transport(env.get('GH_TOKEN','')),Path('contenthub-public-software-run'))
    assembler.run()
if __name__=='__main__':main()
