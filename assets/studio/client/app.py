"""Local, single-user video copy studio. Run using the installed transcription venv."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from client.ai import AIClient, product_facts_text
from client.media import MAX_BYTES, import_link
from client.security import seal, unseal
from client.providers import ProviderStore
from client import evidence as ev
from client import reports as reports_engine
from client.draft_exports import DraftTextExport, export_narrations
from client.feishu import FeishuSettings, FeishuStore
from client import manuscripts,products,planning
from client import product_imports,document_imports
from client.updates import check_update,local_version
from client.app_updates import AppUpdates

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('COPY_STUDIO_DATA', str(ROOT/'.studio'))).resolve()
STATE.mkdir(parents=True, exist_ok=True)
REPO = Path(os.environ.get('COPY_STUDIO_ASR_ROOT',str(ROOT/'tools/video-transcriber'))).resolve()
PYTHON = Path(os.environ.get('COPY_STUDIO_ASR_PYTHON',str(REPO/'.venv/Scripts/python.exe')))
FFMPEG = os.environ.get('FFMPEG_PATH','E:/openfilm/resources/runtime/ffmpeg/ffmpeg.exe')
PORT = int(os.environ.get('COPY_STUDIO_PORT','8777'))
ORIGIN = f'http://127.0.0.1:{PORT}'
SESSION = secrets.token_urlsafe(32)
LOCK = threading.RLock()
ASR_POOL = ThreadPoolExecutor(max_workers=1)
AI_POOL = ThreadPoolExecutor(max_workers=2)
PRODUCT_POOL = ThreadPoolExecutor(max_workers=1)
JOBS = {}
CANCEL_EVENTS = {}
AUDIO_PREVIEW_LOCKS = {}
MAX_TEXT = 20000
PROVIDERS = ProviderStore(STATE)
FEISHU = FeishuStore(STATE)
MATERIAL_IMPORTS={}
APP_UPDATES=AppUpdates()


def atomic_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


for path in STATE.glob('jobs/*/job.json'):
    try:
        item = json.loads(path.read_text(encoding='utf-8'))
        if item['status'] in ('queued','working'):
            item.update(status='error',message='上次任务因客户端退出而中断，可重试。',error='任务已中断。')
            atomic_json(path,item)
        JOBS[item['id']] = item
    except (ValueError, KeyError):
        pass

for path in STATE.glob('jobs/*/product-imports/*/result.json'):
    try:
        item=json.loads(path.read_text(encoding='utf-8'))
        if item['status'] in ('queued','working'):
            item.update(status='error',message='上次提取因客户端退出而中断，请重新提取。',error='提取已中断。')
            atomic_json(path,item)
        MATERIAL_IMPORTS[item['id']]=item
    except (ValueError,KeyError):pass


def directory(job_id):
    return STATE/'jobs'/job_id


def get_job(job_id):
    if job_id not in JOBS:
        raise HTTPException(404,'任务不存在。')
    return JOBS[job_id]


def update(job_id, **values):
    with LOCK:
        item = get_job(job_id)
        item.update(values,updated=time.time())
        atomic_json(directory(job_id)/'job.json',item)
        return copy.deepcopy(item)


def load_config():
    return PROVIDERS.active()


def ai_client():
    return PROVIDERS.client()


def ready(job_id):
    item = get_job(job_id)
    if item.get('deleted_at'):
        raise HTTPException(410,'该参考已移入回收站，请先恢复。')
    if item['status'] in ('working','queued'):
        raise HTTPException(409,'该任务正在处理中，请稍候。')
    return item


def new_job(title, kind, facts, source=''):
    with LOCK:
        job_id = uuid.uuid4().hex
        directory(job_id).mkdir(parents=True)
        JOBS[job_id] = {'id':job_id,'title':title[:160],'kind':kind,'source':source,
                        'status':'queued','message':'排队等待本地转写…','error':'','operation':'transcribe',
                        'created':time.time(),'updated':time.time(),'raw':'','corrected':'',
                        'facts':facts,'corrections':[],'uncertainties':[],'structure':[],'batches':[],
                        'input_file':'','auto_ai':True,'product_profile':None,'product_facts':'',
                        'product_source_text':'','product_warning':'','pinned':False,'pinned_at':0,
                        'deleted_at':None,'link_provider':'local','reports':{},'evidence':None,'markers':None}
        return update(job_id)


def run_process(command, cwd, logfile, timeout=1800):
    env = os.environ.copy()
    env.update(PYTHONIOENCODING='utf-8',FFMPEG_PATH=FFMPEG)
    env['PATH'] = str(Path(FFMPEG).parent)+os.pathsep+env.get('PATH','')
    with logfile.open('w',encoding='utf-8') as output:
        proc = subprocess.Popen(command,cwd=cwd,env=env,stdout=output,stderr=output,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise ValueError('本地处理超时，请缩短视频后重试。')
    if code:
        raise ValueError('本地转写失败，请检查文件是否含有可播放的音轨。详细日志保存在该任务目录。')


def correction_pipeline(job_id, client, text, facts):
    update(job_id,message='AI 正在纠正错别字，保留原文表达…')
    result = client.correct(text,facts)
    update(job_id,corrected=result['text'],corrections=result['corrections'],
           uncertainties=result['uncertainties'],structure=[],product_profile=None,
           product_facts='',product_source_text='',product_warning='')
    update(job_id,message='正在识别参考文案结构…')
    structure = client.analyze_script(result['text']) if get_job(job_id)['kind']=='script' else client.analyze(result['text'])
    update(job_id,structure=structure)
    extract_product(job_id,client,result['text'],facts)


def extract_product(job_id, client, text, facts):
    update(job_id,message='正在自动提取商品名称和卖点…')
    try:
        profile=client.extract_product(text,facts)
        summary=product_facts_text(profile)
        update(job_id,product_profile=profile,product_facts=summary,product_source_text=text,
               product_warning='' if summary else '未识别到明确的商品资料，可以手动填写。')
    except (ValueError,RuntimeError):
        update(job_id,product_warning='商品卖点提取未完成，可点击「重新提取」或手动填写；已有结构仍可使用。')


def generate_in_batches(job_id, data, client):
    snapshot=copy.deepcopy(get_job(job_id))
    stop=CANCEL_EVENTS.setdefault(job_id,threading.Event())
    if data['mode']=='original':
        update(job_id,message='正在根据方向、受众和目标时长设计原创骨架…')
        from client.ai import Structure
        original=client.call('根据给定商品/主题资料创作一份中文短视频原创脚本骨架。id从1连续递增，role为各段功能，text为成品口播。'
          '按目标时长、目的、受众和方向安排节奏；不要沿用参考视频内容，不虚构商品事实。',
          {'facts':data['facts'],'direction':data['direction'],'purpose':data.get('purpose','种草'),
           'audience':data.get('audience',''),'duration':data.get('target_duration',60)},Structure)
        if [s.id for s in original.segments]!=list(range(1,len(original.segments)+1)):
            raise ValueError('原创骨架编号不连续，请重试。')
        snapshot['structure']=original.model_dump()['segments'];snapshot['duration']=data.get('target_duration',60)
    batch={'id':uuid.uuid4().hex,'mode':data['mode'],'created':time.time(),
           'facts':data['facts'],'direction':data['direction'],'reference':snapshot['structure'],
           'variants':[],'review_notes':[],'requested_count':data['count'],'complete':False}
    focus=planning.Focus.model_validate(data.get('focus',{}))
    batch.update(focus=focus.model_dump(),product_snapshot=data.get('product_snapshot'),quality_check=data.get('quality_check',False))
    if isinstance(getattr(client,'provider_id',None),str):
        batch['ai_provider']={'id':client.provider_id,'name':client.provider_name,'model':client.model}
    try:
        while len(batch['variants'])<data['count'] and not stop.is_set():
            completed=len(batch['variants'])
            count=min(2,data['count']-completed)
            update(job_id,message=f"正在生成第 {completed+1}–{completed+count} 条，共 {data['count']} 条…",
                   generation_progress={'completed':completed,'total':data['count']})
            direction=data['direction']+f'\n本轮生成第 {completed+1}–{completed+count} 条，使用不同的口语表达。'
            directions=[planning.direction(focus,i) for i in range(completed+1,completed+count+1)]
            if focus.enabled:direction+='\n逐条方向（严格按以下顺序输出，不改变原结构）：\n'+'\n'.join(f'第 {completed+i+1} 条：{v}' for i,v in enumerate(directions))
            if batch['variants']:
                direction+='避免重复此前版本的标题和切入角度：'+'；'.join(x['title'] for x in batch['variants'][-6:])
            generated=client.generate(snapshot['structure'],'same' if data['mode']=='original' else data['mode'],data['facts'],count,direction)
            for offset,variant in enumerate(generated['variants']):
                manuscripts.aligned(snapshot['structure'],variant['segments'])
                if data.get('quality_check',False):
                    update(job_id,message=f"正在质检第 {len(batch['variants'])+1} 条脚本，低分项将改写一轮…")
                    try:
                        variant=reports_engine.enrich_variant(client,variant,snapshot['structure'],'same' if data['mode']=='original' else data['mode'],data['facts'],data['direction']+'\n本条方向：'+directions[offset],snapshot.get('duration',60))
                    except (ValueError,RuntimeError):
                        variant['quality_error']='文案已生成，六维质检未完成；可保留成稿，稍后重新生成或人工检查。'
                        batch['review_notes']=list(dict.fromkeys(batch['review_notes']+[variant['quality_error']]))
                variant['generation_focus']=directions[offset]
                batch['variants'].append(variant)
                update(job_id,batches=snapshot['batches']+[copy.deepcopy(batch)],
                       generation_progress={'completed':len(batch['variants']),'total':data['count']})
            batch['review_notes']=list(dict.fromkeys(batch['review_notes']+generated['review_notes']))
            batch['complete']=len(batch['variants'])==data['count']
            update(job_id,batches=snapshot['batches']+[copy.deepcopy(batch)],
                   generation_progress={'completed':len(batch['variants']),'total':data['count']})
        complete=len(batch['variants'])==data['count']
        update(job_id,status='done',operation='',error='',message=(
            f"已生成 {len(batch['variants'])} 条文案。" if complete else
            f"已停止生成，保留已完成的 {len(batch['variants'])} 条文案。"))
    finally:
        CANCEL_EVENTS.pop(job_id,None)


def transcribe(job_id):
    try:
        item = update(job_id,status='working',error='',operation='transcribe',message='准备导入媒体…')
        folder = directory(job_id)
        if item['kind']=='link' and not item['input_file']:
            if item.get('link_provider')=='tikhub':
                from client.tikhub import TikHubClient,key_from_config
                media=TikHubClient(key_from_config(STATE)).download(item['source'],folder,lambda message:update(job_id,message=message))
            else:
                media = import_link(item['source'],folder,lambda message:update(job_id,message=message))
            update(job_id,input_file=media.name)
        else:
            media = folder/item['input_file']
        update(job_id,message='正在检查媒体音轨…')
        probe = subprocess.run([str(Path(FFMPEG).with_name('ffprobe.exe')),'-v','error','-show_entries',
                                'format=duration:stream=codec_type','-of','json',str(media)],
                               capture_output=True,text=True,encoding='utf-8',timeout=30,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if probe.returncode:
            raise ValueError('无法读取该媒体文件，请选择正常可播放的视频或音频。')
        info = json.loads(probe.stdout)
        if not any(x.get('codec_type')=='audio' for x in info.get('streams',[])):
            raise ValueError('该视频没有音轨，无法提取口播。')
        duration = float(info.get('format',{}).get('duration',0))
        if duration > 1800:
            raise ValueError('第一版支持 30 分钟以内的视频，请先裁剪。')
        update(job_id,duration=duration,message='SenseVoice 正在本机转写，首次加载模型可能需要等待…')
        out = folder/'asr.json'
        run_process([str(PYTHON),'webmain.py','transcribe',str(media),'--model','sensevoice-small',
                     '--language','zh','--timestamp-mode','sentence','--format','json','--output',str(out),'--quiet'],
                    REPO,folder/'transcribe.log')
        result = json.loads(out.read_text(encoding='utf-8-sig'))
        text = result.get('text','').strip()
        if not text:
            raise ValueError('未识别到可用口播，可能只有音乐或声音过小。')
        update(job_id,raw=text,corrected=text,structure=[],batches=[],corrections=[],uncertainties=[],asr_timed=True,
               product_profile=None,product_facts='',product_source_text='',product_warning='',reports={},evidence=None,markers=None)
        # Local inspection does not depend on an AI account or a successful cloud call.
        try:
            inspect_reference(job_id,{})
        except Exception:
            update(job_id,marker_warning='检测尚未完成，可在「检测标记」中重试；已有口播和结构保留。')
        if item['auto_ai'] and load_config().get('encrypted_key'):
            if len(text)>MAX_TEXT:
                raise ValueError('本地转写已完成；文字超过 2 万字，请手动缩短后再做 AI 处理。')
            correction_pipeline(job_id,ai_client(),text,item['facts'])
            message = '本地转写、AI 纠错和结构分析完成。'
        else:
            message = '本地转写完成。可校对原文，配置 AI 后再纠错和拆结构。'
        if get_job(job_id).get('markers'):message+=' 本地检测标记已更新。'
        update(job_id,status='done',operation='',message=message)
    except Exception as exc:
        fail(job_id,exc)


def fail(job_id, exc):
    # Never persist arbitrary network errors which could echo an API credential or signed URL.
    message = str(exc) if isinstance(exc,(ValueError,RuntimeError)) else '处理失败，请检查配置或网络后重试。'
    update(job_id,status='error',operation='',error=message[:1000],message='本次处理未完成，已有文字和结果仍保留。')


def ai_work(job_id, operation, data, client):
    try:
        item = get_job(job_id)
        if operation=='correct':
            correction_pipeline(job_id,client,data['text'],data['facts'])
        elif operation=='analyze':
            update(job_id,message='正在按原文识别结构…')
            structure = client.analyze_script(data['text']) if item['kind']=='script' else client.analyze(data['text'])
            update(job_id,structure=structure)
            extract_product(job_id,client,data['text'],data['facts'])
        elif operation=='extract-product':
            extract_product(job_id,client,data['text'],data['facts'])
        else:
            generate_in_batches(job_id,data,client)
            return
        update(job_id,status='done',operation='',error='',message='处理完成。请校对商品事实和不确定用词。')
    except Exception as exc:
        fail(job_id,exc)


app = FastAPI(title='文案工坊', docs_url=None,redoc_url=None,openapi_url=None)
SERVER = None


@app.middleware('http')
async def local_only(request:Request, call_next):
    # No CORS; reject cross-site writes and DNS rebinding. Random local session cookie.
    if request.headers.get('host') not in (f'127.0.0.1:{PORT}',f'localhost:{PORT}'):
        return JSONResponse({'detail':'仅限本机访问。'},403)
    if request.url.path.startswith('/api/'):
        if request.cookies.get('studio_session') != SESSION:
            return JSONResponse({'detail':'请重新打开客户端。'},403)
        if request.method not in ('GET','HEAD'):
            origin = request.headers.get('origin')
            if origin and origin not in (ORIGIN,f'http://localhost:{PORT}'):
                return JSONResponse({'detail':'请求来源不匹配。'},403)
            if request.headers.get('x-studio-request') != '1':
                return JSONResponse({'detail':'请求缺少本地校验。'},403)
    writing=request.method not in ('GET','HEAD') and request.url.path not in ('/api/updates/apply','/api/client/close')
    if writing:
        with APP_UPDATES.lock:
            if APP_UPDATES.busy:return JSONResponse({'detail':'正在更新程序，请等待客户端重新打开后继续编辑。'},409)
            APP_UPDATES.writers+=1
    try:response = await call_next(request)
    finally:
        if writing:
            with APP_UPDATES.lock:APP_UPDATES.writers-=1
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response


@app.get('/')
def index():
    response = FileResponse(Path(__file__).parent/'web/index.html')
    response.set_cookie('studio_session',SESSION,httponly=True,samesite='strict')
    return response


@app.get('/api/health')
def health():
    with LOCK:active=sum(r['status'] in ('queued','working') for r in MATERIAL_IMPORTS.values())
    return {'ok':True,'asr_ready':PYTHON.exists(),'ai_configured':bool(load_config().get('encrypted_key')),'product_imports_active':active,
            'instance':os.environ.get('COPY_STUDIO_INSTANCE',''),'offline_resources':bool(os.environ.get('VIDEO_COPY_STUDIO_OFFLINE_MODELS')),
            'version':local_version(),'update_ready':(Path(__file__).parent/'web/app.js').is_file()}


@app.get('/api/updates')
def updates():
    try:return dict(check_update(local_version()),one_click=APP_UPDATES.supported)
    except ValueError as exc:raise HTTPException(503,str(exc)) from exc


@app.get('/api/updates/state')
def update_state():return APP_UPDATES.state()


@app.post('/api/updates/apply',status_code=202)
def apply_update(data:dict):
    with LOCK:
        def busy():return any(item.get('status') in ('queued','working') for item in JOBS.values()) or any(item.get('status') in ('queued','working') for item in MATERIAL_IMPORTS.values())
        try:APP_UPDATES.begin(data.get('version'),busy)
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    return APP_UPDATES.state()


@app.post('/api/client/close')
def close_offline_client(data:dict):
    instance=os.environ.get('COPY_STUDIO_INSTANCE','')
    if not instance or not os.environ.get('VIDEO_COPY_STUDIO_OFFLINE_MODELS'):raise HTTPException(404,'此入口仅供离线客户端使用。')
    if data.get('instance')!=instance:raise HTTPException(403,'客户端实例不匹配。')
    with LOCK:
        if any(item.get('status') in ('queued','working') for item in JOBS.values()) or any(item.get('status') in ('queued','working') for item in MATERIAL_IMPORTS.values()):
            raise HTTPException(409,'仍有任务正在处理，完成后再退出或切换客户端。')
    if SERVER is None:raise HTTPException(409,'当前服务无法自动退出。')
    def stop():SERVER.should_exit=True
    threading.Timer(.3,stop).start()
    return {'ok':True}


@app.get('/api/settings')
def settings():
    data = load_config()
    return {'base_url':data['base_url'],'model':data['model'],'has_key':bool(data.get('encrypted_key')),
            'provider_id':data['id'],'provider_name':data['name']}


class SettingsInput(BaseModel):
    base_url: str = Field(min_length=8,max_length=300)
    model: str = Field(min_length=1,max_length=100)
    key: str = Field(default='',max_length=1000)
    clear_key: bool = False


@app.put('/api/settings')
def save_settings(data:SettingsInput):
    old=load_config()
    try:
        result=PROVIDERS.save(old['id'],name=old['name'],**data.model_dump())
        return {'saved':True,'has_key':result['has_key']}
    except ValueError as exc:raise HTTPException(400,str(exc))


class ProviderInput(SettingsInput):
    name:str=Field(min_length=1,max_length=80)
    json_mode:bool|None=None


class ProviderSelection(BaseModel):
    provider_id:str=Field(min_length=1,max_length=100)


@app.get('/api/providers')
def list_providers():
    return PROVIDERS.listing()


@app.post('/api/providers',status_code=201)
def create_provider(data:ProviderInput):
    try:return PROVIDERS.save(None,**data.model_dump())
    except ValueError as exc:raise HTTPException(400,str(exc))


@app.put('/api/providers/active')
def select_provider(data:ProviderSelection):
    try:return PROVIDERS.select(data.provider_id)
    except ValueError as exc:raise HTTPException(400,str(exc))


@app.put('/api/providers/{provider_id}')
def edit_provider(provider_id:str,data:ProviderInput):
    try:return PROVIDERS.save(provider_id,**data.model_dump())
    except ValueError as exc:raise HTTPException(400,str(exc))


@app.delete('/api/providers/{provider_id}')
def delete_provider(provider_id:str):
    try:PROVIDERS.remove(provider_id);return {'removed':True}
    except ValueError as exc:raise HTTPException(400,str(exc))


@app.post('/api/providers/{provider_id}/test')
def test_provider(provider_id:str):
    try:PROVIDERS.client(provider_id).check();return {'ok':True}
    except Exception as exc:
        raise HTTPException(400,str(exc) if isinstance(exc,(ValueError,RuntimeError)) else '服务商连接失败，请检查地址、模型、Key 和网络。')


@app.post('/api/settings/test')
def test_settings():
    try:
        ai_client().check()
        return {'ok':True}
    except Exception as exc:
        raise HTTPException(400,str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'AI 连接失败，请检查网络和接口地址。')


@app.get('/api/jobs')
def list_jobs(trash:bool=False):
    with LOCK:
        items=[x for x in JOBS.values() if bool(x.get('deleted_at'))==trash]
        items.sort(key=lambda x:(not bool(x.get('pinned')), -float(x.get('pinned_at') or x['created']) if x.get('pinned') else -x['created']))
        return [{k:x.get(k) for k in ('id','kind','title','status','created','message','pinned','pinned_at','deleted_at')} for x in items]


class TikHubSettings(BaseModel):
    key:str=Field(default='',max_length=2000)
    clear_key:bool=False


@app.get('/api/tikhub/settings')
def tikhub_settings():
    from client.tikhub import config_path,ENDPOINT
    path=config_path(STATE)
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return {'has_key':bool(data.get('encrypted_key')),'endpoint':ENDPOINT}


@app.get('/api/preferences')
def preferences():
    path=STATE/'preferences.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'default_link_provider':'local'}


class PreferencesInput(BaseModel):
    default_link_provider:str=Field(pattern='^(local|tikhub)$')


class ServiceSelection(PreferencesInput):
    ai_provider_id:str=Field(min_length=1,max_length=100)


@app.get('/api/services')
def service_selection():
    return {**preferences(),'ai_provider_id':PROVIDERS.active()['id']}


@app.put('/api/services')
def save_service_selection(data:ServiceSelection):
    with LOCK:
        if data.default_link_provider=='tikhub' and not tikhub_settings()['has_key']:
            raise HTTPException(400,'请先配置 TikHub API Key。')
        choices=PROVIDERS.listing()
        profile=next((p for p in choices['providers'] if p['id']==data.ai_provider_id),None)
        if not profile:raise HTTPException(400,'所选文字服务商不存在。')
        if data.ai_provider_id!=choices['active_ai_id']:
            try:PROVIDERS.select(data.ai_provider_id)
            except ValueError as exc:raise HTTPException(400,str(exc))
        atomic_json(STATE/'preferences.json',{'default_link_provider':data.default_link_provider})
    return data.model_dump()


@app.put('/api/preferences')
def save_preferences(data:PreferencesInput):
    if data.default_link_provider=='tikhub' and not tikhub_settings()['has_key']:
        raise HTTPException(400,'请先配置 TikHub API Key。')
    with LOCK:atomic_json(STATE/'preferences.json',data.model_dump())
    return data.model_dump()


@app.put('/api/tikhub/settings')
def save_tikhub_settings(data:TikHubSettings):
    from client.tikhub import config_path
    with LOCK:
        path=config_path(STATE)
        old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        try:
            encrypted='' if data.clear_key else seal(data.key.strip()) if data.key.strip() else old.get('encrypted_key','')
        except ValueError as exc:raise HTTPException(400,str(exc))
        atomic_json(path,{'encrypted_key':encrypted})
        if data.clear_key:
            pref_path=STATE/'preferences.json'
            if pref_path.exists():
                pref=json.loads(pref_path.read_text(encoding='utf-8'))
                if pref.get('default_link_provider')=='tikhub':atomic_json(pref_path,{'default_link_provider':'local'})
    return {'saved':True,'has_key':bool(encrypted)}


class TikHubTestInput(BaseModel):
    url:str=Field(min_length=8,max_length=4000)


@app.post('/api/tikhub/test')
def test_tikhub(data:TikHubTestInput):
    from client.tikhub import TikHubClient,key_from_config
    try:
        result=TikHubClient(key_from_config(STATE)).resolve(data.url)
        return {'ok':True,'has_video_url':True,'title':result['title'],'video_id':result['video_id'],
                'elapsed_seconds':result['elapsed_seconds'],'request_id':result['request_id']}
    except (ValueError,RuntimeError) as exc:raise HTTPException(400,str(exc))


@app.get('/api/jobs/{job_id}')
def job(job_id:str):
    with LOCK:
        item=get_job(job_id)
        if item.get('deleted_at'):raise HTTPException(404,'该参考已移入回收站。')
        return manuscripts.attach(directory(job_id),copy.deepcopy(item))


class PinInput(BaseModel):
    pinned:bool


@app.post('/api/jobs/{job_id}/history/pin')
def pin_job(job_id:str,data:PinInput):
    with LOCK:
        item=get_job(job_id)
        if item.get('deleted_at'):raise HTTPException(409,'请先恢复该参考。')
        if data.pinned and not item.get('pinned') and sum(bool(x.get('pinned')) and not x.get('deleted_at') for x in JOBS.values())>=3:
            raise HTTPException(409,'最多置顶 3 个参考，请先取消一个置顶。')
        update(job_id,pinned=data.pinned,pinned_at=(item.get('pinned_at') or time.time()) if data.pinned else 0)
    return {'pinned':data.pinned}


@app.delete('/api/jobs/{job_id}')
def trash_job(job_id:str):
    with LOCK:
        ready(job_id)
        if any(r['job_id']==job_id and r['status'] in ('queued','working') for r in MATERIAL_IMPORTS.values()):
            raise HTTPException(409,'商品资料正在提取，请完成后再删除参考。')
        update(job_id,deleted_at=time.time(),pinned=False,pinned_at=0)
    return {'deleted':True,'recoverable':True}


@app.post('/api/jobs/{job_id}/history/restore')
def restore_job(job_id:str):
    with LOCK:
        get_job(job_id)
        update(job_id,deleted_at=None,pinned=False,pinned_at=0)
    return {'restored':True}


@app.post('/api/jobs/upload',status_code=202)
async def upload(file:UploadFile=File(...), facts:str=Form(''), auto_ai:bool=Form(True)):
    if len(facts)>5000:
        raise HTTPException(400,'商品资料请控制在 5000 字以内。')
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ('.mp4','.mov','.mkv','.avi','.webm','.m4v','.mp3','.m4a','.wav','.aac','.flac'):
        raise HTTPException(400,'请选择常见视频或音频文件。')
    item = new_job(file.filename or '本地视频','upload',facts)
    job_id = item['id']
    path = directory(job_id)/('source'+suffix)
    try:
        size=0
        with path.open('wb') as output:
            while chunk:= await file.read(1024*1024):
                size+=len(chunk)
                if size>MAX_BYTES:
                    raise ValueError('文件超过 500 MB。')
                output.write(chunk)
        if size<100:
            raise ValueError('文件为空或过小。')
        update(job_id,input_file=path.name,auto_ai=auto_ai)
        ASR_POOL.submit(transcribe,job_id)
        return {'id':job_id}
    except Exception as exc:
        path.unlink(missing_ok=True)
        fail(job_id,exc)
        raise HTTPException(400,str(exc))
    finally:
        await file.close()


async def save_document(file,path):
    size=0
    try:
        with path.open('wb') as output:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>document_imports.MAX_BYTES:raise ValueError('文档超过 20 MB，请拆分后上传。')
                output.write(chunk)
        if not size:raise ValueError('文档为空，请选择有正文的文件。')
    except Exception:
        path.unlink(missing_ok=True)
        raise


def script_work(job_id,client=None):
    try:
        item=update(job_id,status='working',operation='script-import',error='',message='正在读取脚本原文…')
        text=item.get('raw','')
        if item.get('script_file'):
            text=document_imports.document_text(directory(job_id)/item['script_file'],lambda note:update(job_id,message=note))
        text=document_imports.clean_text(text)
        update(job_id,raw=text,corrected=text,asr_timed=False,structure=[])
        if client:
            # Written copy is already the source of truth: analyze without ASR correction.
            update(job_id,message='正在分析原文结构，保留原句与顺序…')
            update(job_id,structure=client.analyze_script(text))
            extract_product(job_id,client,text,item['facts'])
        update(job_id,status='done',operation='',message='脚本已导入，可保留原结构生成新版本。' if client else '脚本已导入，请点击「按当前文案重拆结构」后生成。')
    except Exception as exc:fail(job_id,exc)


class ScriptInput(BaseModel):
    text:str=Field(min_length=1,max_length=MAX_TEXT)
    title:str=Field(default='',max_length=160)
    facts:str=Field(default='',max_length=5000)
    auto_ai:bool=True


@app.post('/api/jobs/script',status_code=202)
def import_script(data:ScriptInput):
    try:
        text=document_imports.clean_text(data.text)
        client=ai_client() if data.auto_ai else None
    except ValueError as exc:raise HTTPException(400,str(exc))
    item=new_job(data.title.strip() or '脚本 · '+text.splitlines()[0][:32],'script',data.facts)
    update(item['id'],raw=text,corrected=text,auto_ai=data.auto_ai,operation='script-import',message='准备分析脚本…',asr_timed=False)
    AI_POOL.submit(script_work,item['id'],client)
    return {'id':item['id']}


@app.post('/api/jobs/script/upload',status_code=202)
async def upload_script(file:UploadFile=File(...),facts:str=Form(''),auto_ai:bool=Form(True)):
    item=None
    try:
        suffix=Path(file.filename or '').suffix.lower()
        if suffix not in document_imports.SUFFIXES:raise ValueError('请选择 DOCX、PDF 或 TXT 脚本文档。')
        if len(facts)>5000:raise ValueError('商品资料请控制在 5000 字以内。')
        client=ai_client() if auto_ai else None
        item=new_job(Path(file.filename).name,'script',facts)
        path=directory(item['id'])/('script'+suffix)
        await save_document(file,path)
        update(item['id'],script_file=path.name,auto_ai=auto_ai,asr_timed=False,operation='script-import',message='准备读取脚本文档…')
        AI_POOL.submit(script_work,item['id'],client)
        return {'id':item['id']}
    except ValueError as exc:
        if item:fail(item['id'],exc)
        raise HTTPException(400,str(exc))
    finally:await file.close()


class LinkInput(BaseModel):
    url:str=Field(min_length=8,max_length=4000)
    facts:str=Field(default='',max_length=5000)
    auto_ai:bool=True
    provider:str=Field(default='local',pattern='^(local|tikhub)$')


@app.post('/api/jobs/link',status_code=202)
def link(data:LinkInput):
    from client.media import extract_url
    try:
        clean = extract_url(data.url)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    item = new_job('链接视频 · '+urlparse(clean).hostname,'link',data.facts,clean)
    update(item['id'],auto_ai=data.auto_ai,link_provider=data.provider)
    ASR_POOL.submit(transcribe,item['id'])
    return {'id':item['id']}


class RetryOptions(BaseModel):
    facts:str=Field(default='',max_length=5000)
    auto_ai:bool=True
    provider:str=Field(default='local',pattern='^(local|tikhub)$')


@app.post('/api/jobs/{job_id}/retry',status_code=202)
def retry(job_id:str,options:RetryOptions|None=None):
    with LOCK:
        item = ready(job_id)
        if options:
            update(job_id,facts=options.facts,auto_ai=options.auto_ai,link_provider=options.provider)
        if item['kind']=='script':
            try:client=ai_client() if get_job(job_id)['auto_ai'] else None
            except ValueError as exc:raise HTTPException(400,str(exc))
            update(job_id,status='queued',error='',operation='script-import',message='准备重新读取脚本…')
            AI_POOL.submit(script_work,job_id,client)
            return {'id':job_id}
        if item['kind']=='link':
            # Resolved platform assets can expire or contain a video-only track.
            update(job_id,input_file='')
        update(job_id,status='queued',error='',operation='transcribe',message='准备重新转写…')
        ASR_POOL.submit(transcribe,job_id)
    return {'id':job_id}


class TextInput(BaseModel):
    text:str=Field(min_length=1,max_length=MAX_TEXT)
    facts:str=Field(default='',max_length=5000)


@app.post('/api/jobs/{job_id}/{operation}',status_code=202)
def process_text(job_id:str,operation:str,data:TextInput):
    if operation not in ('correct','analyze','extract-product'):
        raise HTTPException(404,'操作不存在。')
    with LOCK:
        item=ready(job_id)
        if not data.text.strip():
            raise HTTPException(400,'请先导入视频或填写文案。')
        try:
            client=ai_client()
        except ValueError as exc:
            raise HTTPException(400,str(exc))
        update(job_id,corrected=data.text,facts=data.facts,
               structure=[] if data.text != item['corrected'] else item['structure'],
               product_profile=None if data.text != item['corrected'] else item.get('product_profile'),
               product_facts='' if data.text != item['corrected'] else item.get('product_facts',''),
               product_source_text='' if data.text != item['corrected'] else item.get('product_source_text',''),
               status='working',operation=operation,error='',message='准备 AI 处理…')
        AI_POOL.submit(ai_work,job_id,operation,data.model_dump(),client)
    return {'id':job_id}


class GenerateInput(BaseModel):
    mode:str=Field(pattern='^(same|switch|original)$')
    facts:str=Field(min_length=1,max_length=5000)
    count:int=Field(default=3,ge=1,strict=True)
    direction:str=Field(default='',max_length=2000)
    reference_text:str=Field(min_length=1,max_length=MAX_TEXT)
    quality_check:bool=True
    target_duration:int=Field(default=60,ge=10,le=1800)
    audience:str=Field(default='',max_length=300)
    purpose:str=Field(default='种草',max_length=100)
    focus:planning.Focus=Field(default_factory=planning.Focus)
    product_id:str=Field(default='',max_length=100)
    product_version:int=Field(default=0,ge=0,strict=True)


# Register before the generic /{operation} POST route using a distinct extra path component.
@app.post('/api/jobs/{job_id}/drafts/generate',status_code=202)
def generate(job_id:str,data:GenerateInput):
    with LOCK:
        item=ready(job_id)
        if not item['structure'] and data.mode!='original':
            raise HTTPException(400,'请先完成 AI 纠错或结构分析。')
        if data.mode!='original' and data.reference_text != item['corrected']:
            raise HTTPException(409,'文案已修改，请先点击「按当前文案重拆结构」，再生成。')
        if not data.facts.strip():
            raise HTTPException(400,'请填写已确认的商品名称和卖点。')
        try:
            client=ai_client()
        except ValueError as exc:
            raise HTTPException(400,str(exc))
        payload=data.model_dump()
        if data.product_id:
            try:
                selected=products.get(STATE,data.product_id)
                if selected['version']!=data.product_version:raise FileExistsError('商品资料已更新，请重新选择商品后生成。')
                if data.facts!=products.material(selected):raise ValueError('商品资料已被修改，请重新选择商品，或以手动资料生成。')
                payload['product_snapshot']={k:v for k,v in selected.items() if k!='history'}
                if selected.get('forbidden'):payload['direction']+='\n不可使用以下表述（不是商品事实）：'+selected['forbidden']
            except FileExistsError as exc:raise HTTPException(409,str(exc))
            except ValueError as exc:raise HTTPException(400,str(exc))
        if any(int(k)>data.count for k in data.focus.custom):raise HTTPException(400,'自定义方向序号超过生成条数。')
        CANCEL_EVENTS[job_id]=threading.Event()
        update(job_id,status='working',operation='generate',error='',message='准备生成文案…',
               generation_progress={'completed':0,'total':data.count})
        AI_POOL.submit(ai_work,job_id,'generate',payload,client)
    return {'id':job_id}


@app.post('/api/jobs/{job_id}/drafts/stop')
def stop_generation(job_id:str):
    with LOCK:
        item=get_job(job_id)
        if item['status']!='working' or item['operation']!='generate' or job_id not in CANCEL_EVENTS:
            raise HTTPException(409,'当前没有正在生成的任务。')
        CANCEL_EVENTS[job_id].set()
        update(job_id,message='已请求停止，当前一轮返回后会保留结果并停止后续生成。')
    return {'stopping':True}


def speech_rows(job_id):
    item=get_job(job_id);folder=directory(job_id);media=folder/item['input_file'];timed=folder/'asr.json'
    result=json.loads(timed.read_text(encoding='utf-8-sig')) if timed.exists() else {}
    valid=item.get('asr_timed') and timed.exists() and timed.stat().st_mtime>=media.stat().st_mtime and ev.timeline(result)
    if not valid:
        timed=folder/f'asr-timed-{ev.fingerprint(media)[:12]}.json'
        legacy=folder/'asr-timed.json'
        if not timed.exists() and legacy.exists() and legacy.stat().st_mtime>=media.stat().st_mtime:timed=legacy
        if not timed.exists():
            update(job_id,message='正在本机补齐音频时间戳，原文和结构保持不变…')
            run_process([str(PYTHON),'webmain.py','transcribe',str(media),'--model','sensevoice-small','--language','zh',
                '--timestamp-mode','sentence','--format','json','--output',str(timed),'--quiet'],REPO,folder/'alignment.log')
        result=json.loads(timed.read_text(encoding='utf-8-sig'))
    return ev.timeline(result)


def inspect_reference(job_id,options):
    from client.markers import analyze,Options,all_markers
    item=copy.deepcopy(get_job(job_id));folder=directory(job_id);media=folder/item['input_file']
    if not item.get('input_file') or not media.is_file():raise ValueError('找不到参考原文件，请重新导入。')
    rows=speech_rows(job_id)
    probe=subprocess.run([str(Path(FFMPEG).with_name('ffprobe.exe')),'-v','error','-show_entries',
        'stream=codec_type:format=duration','-of','json',str(media)],capture_output=True,text=True,encoding='utf-8',timeout=30,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if probe.returncode:raise ValueError('参考文件无法读取，请检查文件后重试。')
    info=json.loads(probe.stdout);duration=float(info.get('format',{}).get('duration') or item.get('duration',0))
    result=analyze(media,folder,FFMPEG,duration,rows,any(s['codec_type']=='video' for s in info.get('streams',[])),
                   Options(**options),lambda msg:update(job_id,message=msg))
    valid_ids={m['id'] for m in all_markers(result)}
    # User review choices survive a scan of the same source and the same candidate.
    previous=item.get('markers') or {};decisions=previous.get('decisions',{}) if previous.get('source_hash')==result['source_hash'] else {}
    result.update(created=time.time(),decisions={k:v for k,v in decisions.items() if k in valid_ids})
    update(job_id,markers=result,marker_warning='')
    return result


def marker_work(job_id,options):
    try:
        result=inspect_reference(job_id,options)
        update(job_id,status='done',operation='',error='',message='本地检测已完成，仅做标记，原片与原结构均保留。' if 'error' not in result['statuses'].values() else '本地检测部分完成，可查看提示并重试；原内容均保留。')
    except Exception as exc:fail(job_id,exc)


class MarkerOptions(BaseModel):
    silence_db:float=Field(default=-35,ge=-80,le=-10)
    silence_seconds:float=Field(default=.6,ge=.2,le=5)
    repeat_similarity:float=Field(default=88,ge=70,le=100)
    scene_threshold:float=Field(default=3,ge=1.2,le=10)
    min_scene_seconds:float=Field(default=.5,ge=.2,le=5)


@app.post('/api/jobs/{job_id}/markers/run',status_code=202)
def run_markers(job_id:str,data:MarkerOptions):
    with LOCK:
        item=ready(job_id)
        if not item.get('input_file'):raise HTTPException(400,'请先导入参考视频或音频。')
        update(job_id,status='working',operation='markers',error='',message='准备本机参考检测…')
        ASR_POOL.submit(marker_work,job_id,data.model_dump())
    return {'id':job_id}


class MarkerDecision(BaseModel):
    decision:str=Field(pattern='^(pending|keep|reviewed)$')


@app.put('/api/jobs/{job_id}/markers/{marker_id}/decision')
def mark_decision(job_id:str,marker_id:str,data:MarkerDecision):
    from client.markers import all_markers
    with LOCK:
        item=ready(job_id);result=copy.deepcopy(item.get('markers') or {})
        if not any(m['id']==marker_id for m in all_markers(result)):raise HTTPException(404,'检测标记不存在。')
        result.setdefault('decisions',{})[marker_id]=data.decision;update(job_id,markers=result)
    return {'decision':data.decision}


@app.get('/api/jobs/{job_id}/markers/export')
def export_markers(job_id:str,format:str='md'):
    from client.markers import markdown
    item=job(job_id);result=item.get('markers')
    if not result:raise HTTPException(404,'请先运行参考检测。')
    if format not in ('md','json'):raise HTTPException(400,'格式仅支持 md 或 json。')
    content=markdown(result,item['title']) if format=='md' else json.dumps(result,ensure_ascii=False,indent=2)
    return Response(content.encode('utf-8-sig'),media_type='text/plain; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="markers-{job_id[:8]}.{format}"'})


def reference_path(job_id):
    item=job(job_id)
    if not item.get('input_file'):raise HTTPException(404,'参考原文件不存在。')
    path=directory(job_id)/Path(item['input_file']).name
    if not path.is_file():raise HTTPException(404,'参考原文件不存在。')
    return item,path


def cached_speech_rows(item,path):
    """Preview must never launch a model or infer timestamps just to open a player."""
    source_hash=ev.fingerprint(path);evidence=item.get('evidence') or {}
    if evidence.get('source_hash')==source_hash and evidence.get('speech_timeline'):return evidence['speech_timeline']
    folder=path.parent
    candidates=([folder/'asr.json'] if item.get('asr_timed') else [])+[
        folder/f'asr-timed-{source_hash[:12]}.json',folder/'asr-timed.json']
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_mtime>=path.stat().st_mtime:
            try:
                rows=ev.timeline(json.loads(candidate.read_text(encoding='utf-8-sig')))
                if rows:return rows
            except (ValueError,OSError):pass
    return []


@app.get('/api/jobs/{job_id}/reference/info')
def reference_info(job_id:str):
    item,path=reference_path(job_id)
    try:
        probe=subprocess.run([str(Path(FFMPEG).with_name('ffprobe.exe')),'-v','error','-show_entries',
            'stream=codec_type:format=duration','-of','json',str(path)],capture_output=True,text=True,encoding='utf-8',
            timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if probe.returncode:raise ValueError()
        info=json.loads(probe.stdout)
    except (OSError,ValueError,subprocess.TimeoutExpired):raise HTTPException(400,'参考文件无法读取，请检查原文件。')
    rows=cached_speech_rows(item,path)
    corrected=ev.segment_times(item.get('structure',[]),rows,item.get('corrected','')) if rows else []
    return {'has_video':any(s.get('codec_type')=='video' for s in info.get('streams',[])),
            'has_audio':any(s.get('codec_type')=='audio' for s in info.get('streams',[])),
            'duration':float(info.get('format',{}).get('duration') or item.get('duration',0)),
            'source_hash':ev.fingerprint(path),'raw_segments':rows,'corrected_segments':corrected}


def serve_reference_file(path,request):
    raw_range=request.headers.get('range')
    if not raw_range:return FileResponse(path,headers={'Accept-Ranges':'bytes'})
    import re,mimetypes
    size=path.stat().st_size;match=re.fullmatch(r'bytes=(\d*)-(\d*)',raw_range) if len(raw_range)<100 else None
    try:
        if not match or not size:raise ValueError()
        first,last=match.groups()
        if not first:
            count=int(last)
            if count<=0:raise ValueError()
            start=max(0,size-count);end=size-1
        else:start=int(first);end=min(size-1,int(last)) if last else size-1
        if start>=size or end<start:raise ValueError()
    except ValueError:
        return Response(status_code=416,headers={'Content-Range':f'bytes */{size}','Accept-Ranges':'bytes'})
    def stream():
        remaining=end-start+1
        with path.open('rb') as file:
            file.seek(start)
            while remaining:
                chunk=file.read(min(65536,remaining))
                if not chunk:break
                remaining-=len(chunk);yield chunk
    return StreamingResponse(stream(),status_code=206,media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
        headers={'Accept-Ranges':'bytes','Content-Range':f'bytes {start}-{end}/{size}','Content-Length':str(end-start+1)})


@app.get('/api/jobs/{job_id}/reference/media')
def reference_media(job_id:str,request:Request):
    _,path=reference_path(job_id)
    return serve_reference_file(path,request)


@app.get('/api/jobs/{job_id}/reference/audio')
def reference_audio(job_id:str,request:Request):
    _,path=reference_path(job_id);target=path.parent/f'preview-audio-{ev.fingerprint(path)[:16]}.mp3'
    with AUDIO_PREVIEW_LOCKS.setdefault(job_id,threading.Lock()):
        if not target.exists():
            temp=target.with_suffix('.tmp')
            try:
                made=subprocess.run([FFMPEG,'-hide_banner','-loglevel','error','-y','-i',str(path),'-vn',
                    '-ac','2','-ar','44100','-c:a','libmp3lame','-b:a','128k','-f','mp3',str(temp)],
                    capture_output=True,timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if made.returncode or not temp.exists() or not temp.stat().st_size:raise ValueError()
                temp.replace(target)
            except (OSError,ValueError,subprocess.TimeoutExpired):
                temp.unlink(missing_ok=True)
                raise HTTPException(400,'音频预览未能准备完成，请检查原文件是否含音轨。')
    return serve_reference_file(target,request)


def prepare_evidence(job_id,mode,vision_client=None):
    item=get_job(job_id);folder=directory(job_id);media=folder/item['input_file']
    if not item.get('input_file') or not media.is_file():raise ValueError('找不到原视频，请重新导入。')
    source_hash=ev.fingerprint(media);cache=folder/'evidence-local.json'
    if cache.exists() and json.loads(cache.read_text(encoding='utf-8')).get('source_hash')==source_hash:
        evidence=json.loads(cache.read_text(encoding='utf-8'))
    else:
        evidence=ev.local_frames(media,folder,item.get('duration',0),FFMPEG,lambda msg:update(job_id,message=msg))
        evidence['source_hash']=source_hash;atomic_json(cache,evidence)
    evidence['speech_timeline']=speech_rows(job_id)
    if not evidence['speech_timeline']:raise ValueError('音频时间戳未能对齐，请重新转写后再试。')
    if mode=='vision':
        provider_id=vision_client.provider_id;visual_cache=folder/f'evidence-vision-{provider_id}.json'
        observer=reports_engine.text_hash(vision_client.base_url+'|'+vision_client.model)
        if visual_cache.exists() and json.loads(visual_cache.read_text(encoding='utf-8')).get('source_hash')==source_hash and json.loads(visual_cache.read_text(encoding='utf-8')).get('observer')==observer:
            observed=json.loads(visual_cache.read_text(encoding='utf-8'))
        else:
            picked,images=ev.image_payloads(folder,evidence['frames'])
            if not images:raise ValueError('该文件没有可用视频画面，可以改用本机 OCR。')
            update(job_id,message='所选视觉模型正在分析抽样画面（最多12张）…')
            def validate(r):
                if [f.frame_id for f in r.frames]!=[f['id'] for f in picked]:raise ValueError('画面编号必须逐一对应输入图片。')
                return r
            observed=vision_client.call('根据按序提供的图片逐帧描述可见主体、动作、构图、光线与色彩。'
              'frame_id对应frames_metadata。只写可见证据，不根据字幕猜测动作，不识别真人身份或虚构前后镜头。',
              {'frames_metadata':[{'id':f['id'],'time':f['time']} for f in picked]},reports_engine.Observations,validate,images=images).model_dump()
            observed.update(source_hash=source_hash,observer=observer);atomic_json(visual_cache,observed)
        evidence['observations']=observed['frames'];evidence['visual_source']='vision'
        evidence['limitations']=[evidence['limitations'][0],'视觉描述来自最多12张抽样图，可能误识别；镜头变化与人物身份需人工核对。']+observed['limitations']
    elif mode=='cue':
        if item['kind']!='link':raise ValueError('Cue 公开链接解析需要粘贴链接；本地视频可用 OCR 或视觉模型。')
        cue_cache=folder/'evidence-cue.json'
        parsed=json.loads(cue_cache.read_text(encoding='utf-8')) if cue_cache.exists() else {}
        if parsed.get('source_hash')!=source_hash or parsed.get('source')!=item['source']:
            from client.cue import parse,key_for
            parsed=parse(key_for(STATE),item['source'],lambda msg:update(job_id,message=msg))
            parsed.update(source_hash=source_hash,source=item['source']);atomic_json(cue_cache,parsed)
        evidence['cue_text']=parsed['text'];evidence['visual_source']='cue';evidence['cue_billing']=parsed.get('billing',{})
        evidence['limitations']=[evidence['limitations'][0],'Cue 远程画面识别可能误判，口播以本机校对稿为准；运镜等仍属推断。']
    update(job_id,evidence=evidence)
    return evidence


def report_work(job_id,data,client,vision_client=None):
    try:
        item=get_job(job_id)
        evidence=prepare_evidence(job_id,data['visual_mode'],vision_client)
        if not item['structure']:
            update(job_id,message='正在拆分原文结构…');update(job_id,structure=client.analyze(item['corrected']))
        item=copy.deepcopy(get_job(job_id));segments=ev.segment_times(item['structure'],evidence['speech_timeline'],item['corrected'])
        scenes=list(reports_engine.SCENES) if data['scene']=='all' else [data['scene']]
        for scene in scenes:
            update(job_id,message='正在生成'+reports_engine.SCENES[scene]+'…')
            result=reports_engine.generate_report(client,scene,item,evidence,segments)
            record={'scene':scene,'created':time.time(),'source_hash':reports_engine.text_hash(item['corrected']),
              'visual_mode':data['visual_mode'],'data':result,'segments':segments,
              'ai_provider':{'name':client.provider_name,'model':client.model},
              'markdown':reports_engine.markdown(scene,result,item,evidence,segments)}
            saved=copy.deepcopy(get_job(job_id).get('reports',{}));saved[scene]=record
            update(job_id,reports=saved)
        update(job_id,status='done',operation='',error='',message='场景报告已完成，可复制或导出 Markdown / JSON。')
    except Exception as exc:
        import traceback
        (directory(job_id)/'report-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        fail(job_id,exc)


class ReportInput(BaseModel):
    scene:str=Field(pattern='^(all|transcript|summary|breakdown|storyboard|prompts)$')
    visual_mode:str=Field(default='local',pattern='^(local|cue|vision)$')
    vision_provider_id:str=Field(default='',max_length=80)
    reference_text:str=Field(min_length=1,max_length=MAX_TEXT)


@app.post('/api/jobs/{job_id}/reports/run',status_code=202)
def run_report(job_id:str,data:ReportInput):
    with LOCK:
        item=ready(job_id)
        if data.reference_text!=item['corrected']:raise HTTPException(409,'文案已修改，请先重拆结构保存，再生成报告。')
        try:
            client=ai_client();vision=None
            if data.visual_mode=='vision':
                if not data.vision_provider_id:raise ValueError('请选择支持图片输入的视觉模型服务商。')
                vision=PROVIDERS.client(data.vision_provider_id)
            elif data.visual_mode=='cue':
                if item['kind']!='link':raise ValueError('Cue 适用于公开链接，本地视频请选 OCR 或视觉模型。')
                from client.cue import key_for
                key_for(STATE)
        except ValueError as exc:raise HTTPException(400,str(exc))
        update(job_id,status='working',operation='report',error='',message='正在准备画面与时间线证据…')
        ASR_POOL.submit(report_work,job_id,data.model_dump(),client,vision)
    return {'id':job_id}


@app.get('/api/jobs/{job_id}/reports/{scene}/export')
def export_report(job_id:str,scene:str,format:str='md'):
    item=job(job_id);report=item.get('reports',{}).get(scene)
    if not report:raise HTTPException(404,'该场景尚未生成。')
    if format not in ('md','json'):raise HTTPException(400,'格式仅支持 md 或 json。')
    content=report['markdown'] if format=='md' else json.dumps(report,ensure_ascii=False,indent=2)
    return Response(content.encode('utf-8-sig'),media_type='text/plain; charset=utf-8',headers={
      'Content-Disposition':f'attachment; filename="{scene}-{job_id[:8]}.{format}"'})


@app.get('/api/jobs/{job_id}/frames/{frame_id}')
def frame_image(job_id:str,frame_id:int):
    item=job(job_id);frames=(item.get('evidence') or {}).get('frames',[])
    frame=next((f for f in frames if f['id']==frame_id),None)
    if not frame:raise HTTPException(404,'抽样画面不存在。')
    return FileResponse(directory(job_id)/'frames'/Path(frame['file']).name,media_type='image/jpeg')


class CueSettings(BaseModel):
    key:str=Field(default='',max_length=1000)
    clear_key:bool=False
    import_existing:bool=False


@app.get('/api/cue/settings')
def cue_settings():
    path=STATE/'cue.json';data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    from client.cue import legacy_key
    return {'has_key':bool(data.get('encrypted_key')),'existing_available':bool(legacy_key())}


@app.put('/api/cue/settings')
def save_cue(data:CueSettings):
    from client.cue import legacy_key
    path=STATE/'cue.json';saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    value=legacy_key() if data.import_existing else data.key.strip()
    if data.clear_key:saved['encrypted_key']=''
    elif value:saved['encrypted_key']=seal(value)
    atomic_json(path,saved);return cue_settings()


@app.get('/api/jobs/{job_id}/export')
def export(job_id:str):
    item=job(job_id)
    lines=[item['title'],'','【参考口播】',item['corrected'],'','【结构】']
    lines.extend(f"{x['id']}. {x['role']}\n{x['text']}" for x in item['structure'])
    for batch in item['batches']:
        lines.extend(['','【'+{'same':'同商品裂变','switch':'换商品套结构','original':'原创脚本'}.get(batch['mode'],'脚本')+'】'])
        for variant in batch['variants']:
            lines.extend(['',variant['title']])
            lines.extend(f"{x['id']}. {x['role']}\n{x['text']}" for x in variant['segments'])
            if variant.get('production_segments'):
                lines.extend(['','【分段拍摄表；时长为创作预算】',reports_engine.table(['功能','秒','口播','屏幕文字建议'],[
                  (s['role'],s['duration_budget'],s['text'],s['screen_suggestion']) for s in variant['production_segments']])])
            if variant.get('quality'):lines.extend(['','【六维质检】',reports_engine.score_markdown(variant['quality'])])
            if variant.get('revision',{}).get('performed'):lines.append('已自动改写一轮：'+variant['revision']['reason'])
        if batch.get('review_notes'):
            lines.extend(['','【编辑提示，不属于口播】',*batch['review_notes']])
    if item['uncertainties']:
        lines.extend(['','【待确认】',*item['uncertainties']])
    for report in item.get('reports',{}).values():lines.extend(['',report['markdown']])
    return Response('\n\n'.join(lines).encode('utf-8-sig'),media_type='text/plain; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="copy-{job_id[:8]}.txt"'})


@app.get('/api/jobs/{job_id}/drafts/export')
def export_drafts(job_id:str):
    item=job(job_id)
    for batch in item['batches']:
        for variant in batch['variants']:variant.pop('manuscript',None)
    return Response(json.dumps({'title':item['title'],'batches':item['batches']},ensure_ascii=False,indent=2).encode('utf-8-sig'),
      media_type='application/json',headers={'Content-Disposition':f'attachment; filename="scripts-{job_id[:8]}.json"'})


@app.post('/api/jobs/{job_id}/drafts/text-export')
def export_draft_text(job_id:str, data:DraftTextExport):
    item=job(job_id)
    try:
        body,media_type=export_narrations(item,data)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    return Response(body,media_type=media_type,headers={
        'Content-Disposition':f'attachment; filename="narrations-{job_id[:8]}.{data.format}"'})


@app.get('/api/feishu/settings')
def feishu_settings():
    return FEISHU.public()


@app.put('/api/feishu/settings')
def save_feishu(data:FeishuSettings):
    try:return FEISHU.save(data)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc


@app.post('/api/feishu/test')
def test_feishu():
    try:return FEISHU.test()
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc


@app.post('/api/jobs/{job_id}/drafts/feishu')
def sync_feishu(job_id:str,data:DraftTextExport):
    try:return FEISHU.sync(job(job_id),data)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc


def material_folder(job_id,import_id):
    return directory(job_id)/'product-imports'/import_id


def material_update(import_id,**values):
    with LOCK:
        record=MATERIAL_IMPORTS[import_id];record.update(values,updated=time.time())
        atomic_json(material_folder(record['job_id'],import_id)/'result.json',record)
        return copy.deepcopy(record)


def material_record(job_id,import_id):
    job(job_id)
    value=MATERIAL_IMPORTS.get(import_id)
    if not value or value['job_id']!=job_id:raise HTTPException(404,'这份商品提取记录不存在。')
    return copy.deepcopy(value)


def new_material(job_id,mode,kind,client):
    if mode not in ('same','switch'):raise HTTPException(400,'请选择同商品或换商品模式。')
    with LOCK:
        job(job_id)
        if any(x['job_id']==job_id and x['mode']==mode and x['status'] in ('queued','working') for x in MATERIAL_IMPORTS.values()):
            raise HTTPException(409,'这一模式已有商品资料正在提取，请等待完成。')
        import_id=uuid.uuid4().hex;material_folder(job_id,import_id).mkdir(parents=True)
        provider={k:getattr(client,a,'') if isinstance(getattr(client,a,''),str) else '' for k,a in [('id','provider_id'),('name','provider_name'),('model','model')]}
        MATERIAL_IMPORTS[import_id]={'id':import_id,'job_id':job_id,'mode':mode,'kind':kind,'status':'queued',
            'created':time.time(),'message':'等待提取商品资料…','error':'','source_text':'','profile':None,'facts':'','provider':provider}
        return material_update(import_id)


def material_work(import_id,client,text='',paths=None,document=None):
    try:
        material_update(import_id,status='working',message='正在准备商品资料…')
        if paths:
            text=product_imports.image_text(paths,lambda note:material_update(import_id,message=note))
        if document:
            text=document_imports.document_text(document,lambda note:material_update(import_id,message=note))
        material_update(import_id,source_text=text,message='正在用所选文字服务提取商品名称与卖点…')
        profile=client.extract_product_material(text)
        from client.ai import ProductProfile,validate_product
        # Validate again at the boundary: every item must have a real source quote.
        profile=validate_product(ProductProfile.model_validate(profile),text,'').model_dump()
        material_update(import_id,status='done',profile=profile,facts=product_facts_text(profile),
            message='提取完成，请核对后填入当前商品资料。')
    except Exception as exc:
        message=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else '商品资料处理未完成，请检查图片、文档或文字后重试。'
        material_update(import_id,status='error',error=message,message=message)


class MaterialTextInput(BaseModel):
    mode:str=Field(pattern='^(same|switch)$')
    text:str=Field(min_length=1,max_length=20000)


@app.post('/api/jobs/{job_id}/product-imports/text',status_code=202)
def material_text(job_id:str,data:MaterialTextInput):
    if not data.text.strip():raise HTTPException(400,'请先粘贴商品文案。')
    try:client=ai_client()
    except ValueError as exc:raise HTTPException(400,str(exc))
    record=new_material(job_id,data.mode,'text',client)
    PRODUCT_POOL.submit(material_work,record['id'],client,data.text.strip())
    return record


@app.post('/api/jobs/{job_id}/product-imports/images',status_code=202)
async def material_images(job_id:str,mode:str=Form(...),files:list[UploadFile]=File(...)):
    record=None;paths=[]
    try:
        if not 1<=len(files)<=product_imports.MAX_IMAGES:raise HTTPException(400,'每次请选择 1–5 张商品图片。')
        try:client=ai_client()
        except ValueError as exc:raise HTTPException(400,str(exc))
        record=new_material(job_id,mode,'images',client);total=0
        for index,file in enumerate(files):
            path=material_folder(job_id,record['id'])/f'image-{index+1}.bin';paths.append(path);size=0
            with path.open('wb') as output:
                while chunk:=await file.read(256*1024):
                    size+=len(chunk);total+=len(chunk)
                    if size>product_imports.MAX_IMAGE_BYTES or total>product_imports.MAX_TOTAL_BYTES:
                        raise HTTPException(400,'单张图片最多 12 MB，每次合计最多 30 MB。')
                    output.write(chunk)
            if size<20:raise HTTPException(400,'图片为空或无法读取，请重新选择。')
        PRODUCT_POOL.submit(material_work,record['id'],client,'',paths)
        return record
    except Exception as exc:
        if record:
            material_update(record['id'],status='error',message='图片导入未完成，请重新选择。',error='图片导入未完成。')
            for path in paths:path.unlink(missing_ok=True)
        raise
    finally:
        for file in files:await file.close()


@app.post('/api/jobs/{job_id}/product-imports/document',status_code=202)
async def material_document(job_id:str,mode:str=Form(...),file:UploadFile=File(...)):
    record=None
    try:
        suffix=Path(file.filename or '').suffix.lower()
        if suffix not in document_imports.SUFFIXES:raise ValueError('请选择 DOCX、PDF 或 TXT 文档；旧版 DOC 请另存为 DOCX。')
        client=ai_client();record=new_material(job_id,mode,'document',client)
        path=material_folder(job_id,record['id'])/('document'+suffix)
        await save_document(file,path)
        record=material_update(record['id'],document_name=Path(file.filename).name[:200])
        PRODUCT_POOL.submit(material_work,record['id'],client,'',None,path)
        return record
    except ValueError as exc:
        if record:material_update(record['id'],status='error',error=str(exc),message=str(exc))
        raise HTTPException(400,str(exc))
    finally:await file.close()


@app.get('/api/jobs/{job_id}/product-imports')
def material_list(job_id:str,mode:str='switch'):
    job(job_id)
    with LOCK:
        rows=[copy.deepcopy(r) for r in MATERIAL_IMPORTS.values() if r['job_id']==job_id and r['mode']==mode]
        return sorted(rows,key=lambda r:r['created'],reverse=True)[:5]


@app.get('/api/jobs/{job_id}/product-imports/{import_id}')
def get_material(job_id:str,import_id:str):
    with LOCK:return material_record(job_id,import_id)


class MaterialDraftInput(BaseModel):
    mode:str=Field(pattern='^(same|switch)$')
    text:str=Field(default='',max_length=5000)
    source_id:str=Field(default='',max_length=100)
    active:bool=True


@app.put('/api/jobs/{job_id}/product-material')
def save_material_draft(job_id:str,data:MaterialDraftInput):
    with LOCK:
        item=job(job_id);drafts=copy.deepcopy(item.get('material_drafts',{}))
        if data.active:
            record=material_record(job_id,data.source_id)
            if record['mode']!=data.mode or record['status']!='done':raise HTTPException(409,'提取记录与当前模式不匹配，或尚未完成。')
            if not data.text.strip():raise HTTPException(400,'请核对并补充商品名称和可用卖点。')
            drafts[data.mode]={'text':data.text.strip(),'source_id':record['id'],'profile':record['profile'],
                'kind':record['kind'],'updated':time.time(),'active':True}
        elif data.mode in drafts:drafts[data.mode]['active']=False
        update(job_id,material_drafts=drafts)
        return drafts


class ManuscriptInput(BaseModel):
    base_revision:int=Field(ge=0,strict=True)
    text:str=Field(min_length=1,max_length=20000)
    segments:list[dict]|None=Field(default=None,max_length=40)


class RestoreInput(BaseModel):
    base_revision:int=Field(ge=0,strict=True)
    revision:int=Field(ge=0,strict=True)


class RewriteInput(BaseModel):
    base_revision:int=Field(ge=0,strict=True)
    direction:str=Field(default='',max_length=1500)


def workspace_error(exc):
    raise HTTPException(409 if isinstance(exc,FileExistsError) else 400,str(exc)) from exc


@app.get('/api/jobs/{job_id}/drafts/{batch_id}/{index}/versions')
def script_versions(job_id:str,batch_id:str,index:int):
    with LOCK:
        try:
            item=job(job_id);rows=manuscripts.versions(directory(job_id),item,batch_id,index)
            return {'current':rows[-1],'versions':[{k:v for k,v in r.items() if k not in ('text','segments')} for r in reversed(rows)]}
        except ValueError as exc:workspace_error(exc)


@app.get('/api/jobs/{job_id}/drafts/{batch_id}/{index}/versions/{revision}')
def script_version(job_id:str,batch_id:str,index:int,revision:int):
    with LOCK:
        try:
            rows=manuscripts.versions(directory(job_id),job(job_id),batch_id,index)
            found=next((r for r in rows if r['revision']==revision),None)
            if found is None:raise ValueError('版本不存在。')
            return found
        except ValueError as exc:workspace_error(exc)


@app.put('/api/jobs/{job_id}/drafts/{batch_id}/{index}/manuscript')
def save_script(job_id:str,batch_id:str,index:int,data:ManuscriptInput):
    with LOCK:
        try:return manuscripts.save(directory(job_id),job(job_id),batch_id,index,data.base_revision,data.text,data.segments)
        except (ValueError,FileExistsError) as exc:workspace_error(exc)


@app.post('/api/jobs/{job_id}/drafts/{batch_id}/{index}/restore')
def restore_script(job_id:str,batch_id:str,index:int,data:RestoreInput):
    with LOCK:
        try:
            item=job(job_id);rows=manuscripts.versions(directory(job_id),item,batch_id,index)
            found=next((r for r in rows if r['revision']==data.revision),None)
            if found is None:raise ValueError('版本不存在。')
            return manuscripts.save(directory(job_id),item,batch_id,index,data.base_revision,found['text'],found['segments'],
                kind='restore',note=f'恢复版本 v{data.revision}',restored_from=data.revision)
        except (ValueError,FileExistsError) as exc:workspace_error(exc)


def rewrite_script_work(job_id,batch_id,index,data,client):
    try:
        item=copy.deepcopy(get_job(job_id));batch,variant=manuscripts.script(item,batch_id,index)
        previous=manuscripts.current(directory(job_id),item,batch_id,index)
        reference=batch.get('reference',variant['segments'])
        direction='仅重写这一条，完整保留原段数、id、role和顺序。\n'+batch.get('direction','')+'\n'+variant.get('generation_focus','')
        direction+='\n本次要求：'+data.direction+'\n当前稿（作为改写对象，不新增事实）：'+previous['text']
        product=batch.get('product_snapshot') or {}
        if product.get('forbidden'):direction+='\n不可使用：'+product['forbidden']
        result=client.generate(reference,'same' if batch['mode']=='original' else batch['mode'],batch['facts'],1,direction)
        if len(result.get('variants',[]))!=1:raise ValueError('重写结果不是单条稿件，原版本已保留。')
        segments=manuscripts.aligned(reference,result['variants'][0]['segments'])
        with LOCK:
            manuscripts.save(directory(job_id),get_job(job_id),batch_id,index,data.base_revision,
                '\n\n'.join(s['text'] for s in segments),segments,kind='rewrite',note=data.direction or '按当前方向重写')
            update(job_id,status='done',operation='',error='',message=f'第 {index+1} 条已重写并保存为新版本，其他稿件保持原样。')
    except Exception as exc:fail(job_id,exc)


@app.post('/api/jobs/{job_id}/drafts/{batch_id}/{index}/rewrite',status_code=202)
def rewrite_script(job_id:str,batch_id:str,index:int,data:RewriteInput):
    with LOCK:
        try:
            item=ready(job_id);manuscripts.script(item,batch_id,index)
            if manuscripts.current(directory(job_id),item,batch_id,index)['revision']!=data.base_revision:
                raise FileExistsError('成稿版本已变化，请刷新后重写。')
            client=ai_client()
            update(job_id,status='working',operation='rewrite',error='',message=f'正在重写第 {index+1} 条，原版本保留…')
            AI_POOL.submit(rewrite_script_work,job_id,batch_id,index,data,client)
            return {'id':job_id}
        except (ValueError,FileExistsError) as exc:workspace_error(exc)


@app.get('/api/products')
def product_list():
    with LOCK:return [{k:v for k,v in p.items() if k!='history'} for p in products.list_products(STATE)]


@app.post('/api/products',status_code=201)
def product_create(data:products.ProductInput):
    with LOCK:
        try:return products.save(STATE,data)
        except (ValueError,FileExistsError) as exc:workspace_error(exc)


@app.get('/api/products/{product_id}')
def product_get(product_id:str):
    with LOCK:
        try:return products.get(STATE,product_id)
        except ValueError as exc:workspace_error(exc)


@app.put('/api/products/{product_id}')
def product_update(product_id:str,data:products.ProductInput):
    with LOCK:
        try:return products.save(STATE,data,product_id)
        except (ValueError,FileExistsError) as exc:workspace_error(exc)


@app.delete('/api/products/{product_id}')
def product_archive(product_id:str):
    with LOCK:
        try:products.archive(STATE,product_id);return {'archived':True}
        except ValueError as exc:workspace_error(exc)


class PlanInput(BaseModel):
    count:int=Field(ge=1,strict=True)
    focus:planning.Focus=Field(default_factory=planning.Focus)
    offset:int=Field(default=0,ge=0)
    limit:int=Field(default=14,ge=1,le=30)


@app.post('/api/drafts/plan')
def preview_plan(data:PlanInput):
    return {'count':data.count,'items':[{'index':i,'label':data.focus.custom.get(str(i),planning.ANGLES[(i-1)%len(planning.ANGLES)]),'direction':planning.direction(data.focus,i)}
        for i in range(data.offset+1,min(data.count,data.offset+data.limit)+1)]}


app.mount('/static',StaticFiles(directory=Path(__file__).parent/'web'),name='static')


if __name__=='__main__':
    import uvicorn
    SERVER=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=PORT,access_log=False))
    SERVER.run()
