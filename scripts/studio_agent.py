"""Stdlib-only JSON CLI for the local studio. Never accepts API keys as CLI arguments."""
import argparse
import http.client
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

from bootstrap import SKILL,home
from prepare_models import model_status
from browser_setup import browser_status,repair_browser
from extra_setup import extra_status


def settings(root):
    path=root/'runtime.json'
    if not path.exists():raise ValueError('尚未安装运行时。先执行 scripts/bootstrap.py --install --download-ffmpeg。')
    return json.loads(path.read_text(encoding='utf-8'))


class Studio:
    def __init__(self,url):
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
            raise ValueError('服务地址只能是本机 http://127.0.0.1:端口。')
        self.url=url.rstrip('/');self.parsed=parsed;self.cookies=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(self.cookies))
        self.opener.open(self.url+'/',timeout=10).close()

    def request(self,path,method='GET',data=None,binary=False):
        body=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
        req=urllib.request.Request(self.url+'/api'+path,data=body,method=method,headers={
            'Content-Type':'application/json','X-Studio-Request':'1'})
        try:
            with self.opener.open(req,timeout=240 if binary else 100) as response:raw=response.read()
        except urllib.error.HTTPError as exc:
            try:message=json.loads(exc.read()).get('detail','请求失败。')
            except ValueError:message='请求失败。'
            raise ValueError(str(message)[:1000]) from exc
        return raw if binary else json.loads(raw)

    def upload(self,path,facts,auto_ai,script=False):
        path=Path(path).expanduser().resolve()
        if not path.is_file():raise ValueError('输入媒体文件不存在。')
        if path.stat().st_size>(20 if script else 500)*1024*1024:raise ValueError('输入文件超过允许的大小。')
        if script and path.suffix.lower() not in ('.docx','.pdf','.txt'):raise ValueError('脚本文档支持 DOCX、PDF、TXT。')
        boundary='Studio'+uuid.uuid4().hex
        fields=''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k,v in [('facts',facts),('auto_ai','true' if auto_ai else 'false')])
        filename=path.name.replace('"','_').replace('\r','').replace('\n','')
        prefix=(fields+f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode('utf-8')
        suffix=f'\r\n--{boundary}--\r\n'.encode()
        connection=http.client.HTTPConnection(self.parsed.hostname,self.parsed.port or 80,timeout=240)
        try:
            connection.putrequest('POST','/api/jobs/script/upload' if script else '/api/jobs/upload')
            for key,value in {'Content-Type':f'multipart/form-data; boundary={boundary}','Content-Length':str(len(prefix)+path.stat().st_size+len(suffix)),
                 'Cookie':'; '.join(c.name+'='+c.value for c in self.cookies),'X-Studio-Request':'1'}.items():connection.putheader(key,value)
            connection.endheaders();connection.send(prefix)
            with path.open('rb') as source:
                while chunk:=source.read(1024*1024):connection.send(chunk)
            connection.send(suffix);response=connection.getresponse();body=json.loads(response.read())
            if response.status>=400:raise ValueError(str(body.get('detail','导入失败。')))
            return body
        finally:connection.close()


    def upload_materials(self,job_id,paths,mode,document=False):
        if not isinstance(paths,list) or not 1<=len(paths)<=5:raise ValueError('images 需要 1–5 个本机图片路径。')
        files=[Path(p).expanduser().resolve() for p in paths]
        if document and (len(files)!=1 or files[0].suffix.lower() not in ('.docx','.pdf','.txt')):raise ValueError('请选择一份 DOCX、PDF 或 TXT 文档。')
        if any(not p.is_file() or p.stat().st_size>(20 if document else 12)*1024*1024 for p in files) or sum(p.stat().st_size for p in files)>(20 if document else 30)*1024*1024:
            raise ValueError('图片文件必须存在，单张不超过 12 MB，合计不超过 30 MB。')
        boundary='Product'+uuid.uuid4().hex
        prefix=f'--{boundary}\r\nContent-Disposition: form-data; name="mode"\r\n\r\n{mode}\r\n'.encode()
        parts=[]
        for path in files:
            name=path.name.replace('"','_').replace('\r','').replace('\n','')
            field='file' if document else 'files'
            header=f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode('utf-8')
            parts.append((header,path))
        suffix=f'--{boundary}--\r\n'.encode();size=len(prefix)+sum(len(header)+path.stat().st_size+2 for header,path in parts)+len(suffix)
        connection=http.client.HTTPConnection(self.parsed.hostname,self.parsed.port or 80,timeout=100)
        try:
            connection.putrequest('POST','/api/jobs/'+urllib.parse.quote(job_id,safe='')+'/product-imports/'+('document' if document else 'images'))
            for k,v in {'Content-Type':f'multipart/form-data; boundary={boundary}','Content-Length':str(size),
                        'Cookie':'; '.join(c.name+'='+c.value for c in self.cookies),'X-Studio-Request':'1'}.items():connection.putheader(k,v)
            connection.endheaders();connection.send(prefix)
            for header,path in parts:
                connection.send(header)
                with path.open('rb') as source:
                    while chunk:=source.read(256*1024):connection.send(chunk)
                connection.send(b'\r\n')
            connection.send(suffix);response=connection.getresponse();body=json.loads(response.read())
            if response.status>=400:raise ValueError(str(body.get('detail','商品图片导入失败。')))
            return body
        finally:connection.close()


def save_output(path,content,overwrite=False):
    path=Path(path).expanduser().resolve()
    if path.exists() and not overwrite:raise ValueError('输出文件已存在；换路径或显式指定 overwrite=true。')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb' if overwrite else 'xb') as target:target.write(content)
    return {'output_path':str(path),'bytes':len(content)}


def selected_batch(job,params):
    batches=job.get('batches',[]);wanted=params.get('batch_id','latest')
    batch=batches[-1] if batches and wanted=='latest' else next((b for b in batches if b['id']==wanted),None)
    if not batch:raise ValueError('没有对应的生成批次。')
    indices=params.get('indices') or list(range(1,len(batch['variants'])+1))
    if not isinstance(indices,list) or any(type(i)!=int or i<1 or i>len(batch['variants']) for i in indices) or len(indices)!=len(set(indices)):
        raise ValueError('indices 必须是不重复的有效脚本序号，从 1 开始。')
    if not indices:raise ValueError('没有可导出的文案。')
    edits=params.get('edits',{})
    items=[]
    for i in sorted(indices):
        variant=batch['variants'][i-1];saved=variant.get('manuscript')
        row={'index':i-1,'text':edits.get(str(i),saved['text'] if saved else '\n\n'.join(s['text'] for s in variant['segments']))}
        if saved and str(i) not in edits:row['revision']=saved['revision']
        items.append(row)
    return batch,items


def invoke(client,params):
    for flag in ('auto_ai','write','overwrite','quality_check'):
        if flag in params and type(params[flag]) is not bool:raise ValueError(flag+' 必须是 JSON 布尔值 true/false。')
    action=params.get('action');job_id=params.get('job_id','')
    if action=='health':return client.request('/health')
    if action=='list':return client.request('/jobs')
    if action=='providers':return client.request('/providers')
    if action=='products':return client.request('/products')
    if action=='product-get':return client.request('/products/'+urllib.parse.quote(params['product_id'],safe=''))
    if action=='product-save':
        body=params['product']
        if body.get('confirmed') is not True:raise ValueError('请明确核对商品资料，再设置 product.confirmed=true；待确认信息不用于生成。')
        return client.request('/products'+('/'+urllib.parse.quote(params['product_id'],safe='') if params.get('product_id') else ''),'PUT' if params.get('product_id') else 'POST',body)
    if action=='plan':return client.request('/drafts/plan','POST',{k:params[k] for k in ('count','focus','offset','limit') if k in params})
    if action=='import':
        if bool(params.get('file'))==bool(params.get('url')):raise ValueError('file 与 url 必须且只能提供一个。')
        if params.get('file'):return client.upload(params['file'],params.get('facts',''),params.get('auto_ai',False))
        return client.request('/jobs/link','POST',{'url':params['url'],'facts':params.get('facts',''),'auto_ai':params.get('auto_ai',False),'provider':params.get('provider','local')})
    if action=='import-script':
        if bool(params.get('text'))==bool(params.get('file')):raise ValueError('text 与 file 必须且只能提供一个。')
        if params.get('file'):return client.upload(params['file'],params.get('facts',''),params.get('auto_ai',True),script=True)
        return client.request('/jobs/script','POST',{k:params[k] for k in ('text','title','facts','auto_ai') if k in params})
    if not job_id:raise ValueError('此操作需要 job_id。')
    job=client.request('/jobs/'+urllib.parse.quote(job_id,safe=''))
    if action=='get':return job
    if action=='extract-material':
        mode=params.get('mode','switch')
        if mode not in ('same','switch'):raise ValueError('商品提取 mode 仅支持 same/switch。')
        if sum(bool(params.get(k)) for k in ('text','images','document'))!=1:raise ValueError('text、images、document 必须且只能提供一个。')
        if params.get('document'):return client.upload_materials(job_id,[params['document']],mode,document=True)
        if params.get('images'):return client.upload_materials(job_id,params['images'],mode)
        return client.request(f'/jobs/{job_id}/product-imports/text','POST',{'mode':mode,'text':params['text']})
    if action in ('material-status','apply-material'):
        source_id=urllib.parse.quote(params['import_id'],safe='')
        record=client.request(f'/jobs/{job_id}/product-imports/{source_id}')
        if action=='material-status':return record
        if record['status']!='done':raise ValueError('商品资料尚未提取完成。')
        if not params.get('text','').strip():raise ValueError('应用时需要提供核对后的商品资料 text。')
        return client.request(f'/jobs/{job_id}/product-material','PUT',{'mode':record['mode'],'source_id':record['id'],'text':params['text']})
    if action in ('manuscript','save-manuscript','restore-manuscript','rewrite'):
        batches=job.get('batches',[]);batch=next((b for b in batches if b['id']==params.get('batch_id')),None) if params.get('batch_id','latest')!='latest' else (batches[-1] if batches else None)
        index=params.get('script_index',1)
        if not batch or type(index)!=int or not 1<=index<=len(batch['variants']):raise ValueError('请指定有效批次和从 1 开始的 script_index。')
        path=f'/jobs/{job_id}/drafts/{urllib.parse.quote(batch["id"],safe="")}/{index-1}'
        if action=='manuscript':return client.request(path+'/versions'+('/'+str(params['revision']) if 'revision' in params else ''))
        if type(params.get('base_revision'))!=int or params['base_revision']<0:raise ValueError('修改、恢复或重写需要 base_revision，请先读取当前成稿。')
        keys={'save-manuscript':('base_revision','text','segments'),'restore-manuscript':('base_revision','revision'),'rewrite':('base_revision','direction')}[action]
        suffix={'save-manuscript':'/manuscript','restore-manuscript':'/restore','rewrite':'/rewrite'}[action]
        return client.request(path+suffix,'PUT' if action=='save-manuscript' else 'POST',{k:params[k] for k in keys if k in params})
    if action=='stop':return client.request(f'/jobs/{job_id}/drafts/stop','POST')
    if action in ('correct','analyze','extract-product'):
        return client.request(f'/jobs/{job_id}/{action}','POST',{'text':params.get('text',job['corrected']),'facts':params.get('facts',job.get('facts',''))})
    if action=='generate':
        facts=params.get('facts',job.get('product_facts',''))
        if params.get('mode','same')=='switch' and not (params.get('facts') or params.get('product_id')):raise ValueError('换商品模式需要明确提供目标商品 facts 或 product_id。')
        data={k:params[k] for k in ('direction','quality_check','target_duration','audience','purpose','focus','product_id','product_version') if k in params}
        if params.get('product_id') and 'facts' not in params:
            product=client.request('/products/'+urllib.parse.quote(params['product_id'],safe=''))
            facts='商品：'+product['name']+'\n已确认卖点：\n'+product['facts']+('\n专有名词：'+product['aliases'] if product.get('aliases') else '')
            data.setdefault('product_version',product['version'])
        return client.request(f'/jobs/{job_id}/drafts/generate','POST',dict(data,mode=params.get('mode','same'),count=params.get('count',3),facts=facts,reference_text=job['corrected']))
    if action=='report':
        return client.request(f'/jobs/{job_id}/reports/run','POST',{'scene':params.get('scene','transcript'),'visual_mode':params.get('visual_mode','local'),
            'vision_provider_id':params.get('vision_provider_id',''),'reference_text':job['corrected']})
    if action=='markers':return client.request(f'/jobs/{job_id}/markers/run','POST',params.get('options',{}))
    if action=='export-report':
        scene=params.get('scene','transcript');fmt=params.get('format','md')
        if fmt not in ('md','json'):raise ValueError('报告仅支持 md/json。')
        raw=client.request(f'/jobs/{job_id}/reports/{urllib.parse.quote(scene,safe="")}/export?format={fmt}',binary=True)
        return save_output(params['output'],raw,params.get('overwrite',False))
    if action in ('export','feishu'):
        batch,items=selected_batch(job,params);fmt=params.get('format','xlsx')
        body={'batch_id':batch['id'],'format':fmt if fmt!='json' else 'txt','items':items,
              'template':params.get('template','script'),'table_options':params.get('table_options',{})}
        if action=='feishu':
            config=client.request('/feishu/settings')
            if not params.get('write',False):return {'preview':True,'target':config.get('target_url',''),'configured':config['has_secret'],'scripts':len(items),'template':body['template'],'next':'用户明确要求写入后，设置 write=true 再执行。'}
            return client.request(f'/jobs/{job_id}/drafts/feishu','POST',body)
        if fmt=='json':
            content={'job_id':job_id,'batch_id':batch['id'],'mode':batch['mode'],'variants':[dict(batch['variants'][row['index']],export_text=row['text'],index=row['index']+1) for row in items]}
            raw=json.dumps(content,ensure_ascii=False,indent=2).encode('utf-8')
        elif fmt in ('txt','zip','xlsx'):raw=client.request(f'/jobs/{job_id}/drafts/text-export','POST',body,binary=True)
        else:raise ValueError('文案导出支持 txt/zip/json/xlsx。')
        return save_output(params['output'],raw,params.get('overwrite',False))|{'scripts':len(items),'format':fmt,'template':body['template']}
    raise ValueError('未知 action；请阅读 references/parameters.md。')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-home',type=Path,default=home());parser.add_argument('--base-url')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');sub.add_parser('repair-browser');start=sub.add_parser('start');start.add_argument('--open',action='store_true')
    call=sub.add_parser('invoke');call.add_argument('--request',type=Path,required=True)
    wait=sub.add_parser('wait');wait.add_argument('--job-id',required=True);wait.add_argument('--timeout',type=float,default=30)
    args=parser.parse_args();root=args.runtime_home.resolve()
    config=json.loads((root/'runtime.json').read_text(encoding='utf-8')) if (root/'runtime.json').exists() else {}
    url=args.base_url or f'http://127.0.0.1:{config.get("port",8777)}'
    if args.command=='repair-browser':
        try:return repair_browser(root,settings(root))
        except RuntimeError as exc:raise ValueError(str(exc)) from exc
    if args.command=='doctor':
        try:service=Studio(url).request('/health')
        except Exception:service=None
        return {'skill_version':(SKILL/'VERSION').read_text().strip(),'windows_runtime_supported':os.name=='nt','runtime_registered':bool(config),
                'service_url':url,'service':service,'models_ready':model_status(root/'models-ready.json',config.get('model_cache')),
                'browser_ready':browser_status(config.get('python'),config.get('browser_path')),
                'dependencies_ready':extra_status(config.get('python')),
                'launcher':str(root/'打开文案工坊.cmd'),'model_weights_in_zip':False,'credentials_in_zip':False}
    if args.command=='start':
        config=settings(root)
        try:
            if Studio(url).request('/health').get('ok') is not True:raise ValueError('当前端口不是可用的文案工坊服务。')
        except Exception:
            parsed=urllib.parse.urlsplit(url)
            if parsed.hostname not in ('127.0.0.1','localhost'):raise ValueError('只允许启动本机服务。')
            env=dict(os.environ,COPY_STUDIO_ASR_ROOT=config['asr_root'],COPY_STUDIO_ASR_PYTHON=config['python'],
                FFMPEG_PATH=config['ffmpeg'],COPY_STUDIO_PORT=str(parsed.port or 8777),COPY_STUDIO_DATA=config['data_dir'],PYTHONIOENCODING='utf-8')
            if config.get('model_cache'):
                env.update(MODELSCOPE_CACHE=config['model_cache'],MODEL_CACHE_DIR=config['model_cache'])
            if config.get('browser_path'):
                env['PLAYWRIGHT_BROWSERS_PATH']=config['browser_path']
            env['PATH']=str(Path(config['ffmpeg']).parent)+os.pathsep+env.get('PATH','')
            root.mkdir(parents=True,exist_ok=True)
            with (root/'server.log').open('ab') as log:
                child=subprocess.Popen([config['python'],'-m','client.app'],cwd=SKILL/'assets/studio',env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (root/'service-pid.json').write_text(json.dumps({'pid':child.pid,'url':url}),encoding='utf-8')
            for _ in range(60):
                try:Studio(url).request('/health');break
                except Exception:time.sleep(.4)
            else:raise ValueError('服务启动失败，请查看 runtime-home 下的 server.log。')
        if args.open:webbrowser.open(url)
        return {'service_url':url,'ready':True}
    client=Studio(url)
    if args.command=='invoke':
        request=json.loads(args.request.read_text(encoding='utf-8-sig'))
        if not isinstance(request,dict):raise ValueError('请求文件必须是 JSON 对象。')
        return invoke(client,request)
    if args.command=='wait':
        if not 0<=args.timeout<=60:raise ValueError('单次 wait 的 timeout 为 0..60 秒；仍运行时稍后继续查询。')
        deadline=time.monotonic()+args.timeout
        while True:
            item=client.request('/jobs/'+urllib.parse.quote(args.job_id,safe=''))
            if item['status'] not in ('working','queued') or time.monotonic()>=deadline:
                return {'job_id':item['id'],'status':item['status'],'pending':item['status'] in ('working','queued'),
                    'message':item['message'],'error':item.get('error',''),'generation_progress':item.get('generation_progress')}
            time.sleep(min(2,max(0,deadline-time.monotonic())))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    try:print(json.dumps({'ok':True,'data':main()},ensure_ascii=False))
    except (Exception,KeyboardInterrupt) as exc:
        # Network exception strings can carry signed URLs; do not reflect them.
        detail=str(exc) if isinstance(exc,(ValueError,KeyError,FileNotFoundError)) else type(exc).__name__
        print(json.dumps({'ok':False,'error':detail[:1000]},ensure_ascii=False));sys.exit(1)
