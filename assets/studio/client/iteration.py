"""Routes for recoverable generation, intake confirmation and editorial workflow."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import threading
import time
from pathlib import Path
from fastapi import File,Form,UploadFile,HTTPException,Query
from pydantic import BaseModel,Field
from client import manuscripts,document_imports,editorial
from client.script_previews import PreviewStore,suggest_parts


class MetadataInput(BaseModel):
    title:str=Field(min_length=1,max_length=160)
    project:str=Field(default='',max_length=100)
    product_label:str=Field(default='',max_length=200)
    tags:list[str]=Field(default_factory=list,max_length=10)
    base_version:int=Field(default=0,ge=0)


class EditorialRow(BaseModel):
    index:int=Field(ge=0)
    status:str=Field(pattern='^(review|edit|adopted|shoot|published|discarded)$')
    note:str=Field(default='',max_length=1000)
    base_version:int=Field(default=0,ge=0)


class EditorialInput(BaseModel):
    items:list[EditorialRow]=Field(min_length=1,max_length=500)


class ReviewInput(BaseModel):
    indices:list[int]=Field(min_length=1,max_length=300)
    threshold:int=Field(default=80,ge=50,le=100)


class PreviewInput(BaseModel):
    title:str=Field(default='粘贴的脚本',max_length=160)
    text:str=Field(min_length=1,max_length=20000)


class PreviewPart(BaseModel):
    title:str=Field(min_length=1,max_length=160)
    text:str=Field(min_length=1,max_length=20000)


class ConfirmInput(BaseModel):
    parts:list[PreviewPart]=Field(min_length=1,max_length=50)
    facts:str=Field(default='',max_length=5000)
    auto_ai:bool=True
    project:str=Field(default='',max_length=100)
    product_label:str=Field(default='',max_length=200)


def install(s):
    store=PreviewStore(s.STATE);s.SCRIPT_PREVIEWS=store;pool=ThreadPoolExecutor(max_workers=1)
    def job(id):
        item=s.get_job(id)
        if item.get('deleted_at'):raise HTTPException(410,'参考已移入回收站。')
        return item
    def batch(id,bid):
        value=next((b for b in job(id)['batches'] if b['id']==bid),None)
        if value is None:raise HTTPException(404,'生成批次不存在。')
        return value
    def preview(id):
        try:return store.get(id)
        except ValueError as exc:raise HTTPException(404,str(exc))

    @s.app.post('/api/jobs/{job_id}/drafts/{batch_id}/resume',status_code=202)
    def resume(job_id:str,batch_id:str):
        with s.LOCK:
            s.ready(job_id);value=batch(job_id,batch_id)
            if len(value['variants'])>=value.get('requested_count',len(value['variants'])):raise HTTPException(409,'这个批次已经完成，无需补齐。')
            provider=value.get('ai_provider',{})
            try:client=s.PROVIDERS.client(provider['id']) if provider.get('id') else s.ai_client()
            except ValueError as exc:raise HTTPException(400,'原批次服务不可用：'+str(exc))
            if provider.get('model') and client.model!=provider['model']:raise HTTPException(409,'原批次模型配置已改变，请先恢复该模型配置再补齐。')
            if provider.get('base_url') and client.base_url!=provider['base_url']:raise HTTPException(409,'原批次服务地址已改变，请先恢复配置再补齐。')
            data=copy.deepcopy(value.get('request',{}))
            data.update(mode=value['mode'],facts=value['facts'],direction=value.get('direction',''),count=value['requested_count'],
                focus=value.get('focus',{}),quality_check=value.get('quality_check',False),resume_batch_id=batch_id)
            s.CANCEL_EVENTS[job_id]=threading.Event()
            s.update(job_id,status='working',operation='generate',error='',message='正在按原批次资料补齐剩余文案…',
                generation_progress={'completed':len(value['variants']),'total':value['requested_count'],'batch_id':batch_id})
            s.AI_POOL.submit(s.ai_work,job_id,'generate',data,client)
        return {'id':job_id,'batch_id':batch_id,'remaining':value['requested_count']-len(value['variants'])}

    @s.app.patch('/api/jobs/{job_id}/metadata')
    def metadata(job_id:str,data:MetadataInput):
        with s.LOCK:
            item=job(job_id)
            if data.base_version!=item.get('metadata_version',0):raise HTTPException(409,'分类信息已被其他窗口更新，请重新打开后修改。')
            if not data.title.strip() or any(not tag.strip() or len(tag)>50 for tag in data.tags):raise HTTPException(400,'名称或标签格式有误，单个标签最多50字。')
            return s.update(job_id,title=data.title.strip(),project=data.project.strip(),product_label=data.product_label.strip(),
                tags=list(dict.fromkeys(tag.strip() for tag in data.tags)),metadata_version=data.base_version+1)

    @s.app.get('/api/library/catalog')
    def catalog():
        with s.LOCK:rows=[r for r in s.JOBS.values() if not r.get('deleted_at')]
        return {'projects':sorted({r['project'] for r in rows if r.get('project')}),
            'products':sorted({r['product_label'] for r in rows if r.get('product_label')}),
            'tags':sorted({tag for r in rows for tag in r.get('tags',[])})}

    @s.app.put('/api/jobs/{job_id}/drafts/{batch_id}/editorial')
    def set_editorial(job_id:str,batch_id:str,data:EditorialInput):
        with s.LOCK:
            value=batch(job_id,batch_id);saved=copy.deepcopy(value.get('editorial',{}));seen=set()
            for row in data.items:
                if row.index>=len(value['variants']) or row.index in seen:raise HTTPException(400,'稿件序号无效或重复。')
                seen.add(row.index);previous=saved.get(str(row.index),{})
                if previous.get('version',0)!=row.base_version:raise HTTPException(409,'稿件状态已被其他窗口修改，请刷新后重试。')
                history=previous.get('history',[])+[{'from':previous.get('status','review'),'to':row.status,'note':row.note.strip(),'created':time.time()}]
                saved[str(row.index)]={'status':row.status,'note':row.note.strip(),'version':row.base_version+1,'updated':time.time(),'history':history}
            value['editorial']=saved;s.update(job_id,batches=job(job_id)['batches'])
            return saved

    @s.app.post('/api/jobs/{job_id}/drafts/{batch_id}/review')
    def review(job_id:str,batch_id:str,data:ReviewInput):
        with s.LOCK:
            item=copy.deepcopy(job(job_id));value=batch(job_id,batch_id)
            if len(set(data.indices))!=len(data.indices) or any(i<0 or i>=len(value['variants']) for i in data.indices):raise HTTPException(400,'请选择有效且不重复的稿件序号。')
            rows=[dict(index=i,**manuscripts.current(s.directory(job_id),item,batch_id,i)) for i in data.indices]
            reference='\n\n'.join(p['text'] for p in value['reference'])
        return editorial.text_review(reference,rows,data.threshold)

    def read_preview(id,path=None,text=''):
        try:
            store.update(id,status='working',message='正在本机读取正文…')
            if path:text=document_imports.document_text(path,lambda note:store.update(id,message=note))
            text=document_imports.clean_text(text);title=store.get(id)['title']
            store.update(id,status='ready',source_text=text,parts=suggest_parts(text,title),message='请核对正文和拆分，再确认导入。')
        except Exception as exc:store.update(id,status='error',error=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else '正文读取失败，请换成 DOCX / TXT 后重试。')

    @s.app.post('/api/script-previews/text',status_code=202)
    def preview_text(data:PreviewInput):
        try:text=document_imports.clean_text(data.text)
        except ValueError as exc:raise HTTPException(400,str(exc))
        value=store.create(data.title);read_preview(value['id'],text=text);return store.get(value['id'])

    @s.app.post('/api/script-previews/document',status_code=202)
    async def preview_document(file:UploadFile=File(...)):
        value=None
        try:
            suffix=Path(file.filename or '').suffix.lower()
            if suffix not in document_imports.SUFFIXES:raise ValueError('请选择 DOCX、PDF 或 TXT。')
            value=store.create(Path(file.filename).name);path=store.folder(value['id'])/('source'+suffix)
            await s.save_document(file,path);pool.submit(read_preview,value['id'],path)
            return store.get(value['id'])
        except ValueError as exc:
            if value:store.update(value['id'],status='error',error=str(exc))
            raise HTTPException(400,str(exc))
        finally:await file.close()

    @s.app.get('/api/script-previews/{preview_id}')
    def get_preview(preview_id:str):return preview(preview_id)

    @s.app.post('/api/script-previews/{preview_id}/confirm',status_code=202)
    def confirm(preview_id:str,data:ConfirmInput):
        with s.LOCK,store.lock:
            value=preview(preview_id);digest=store.digest(data.model_dump())
            if value['jobs']:
                if digest!=value.get('confirmation_digest'):raise HTTPException(409,'这份预览已经导入；需要新版本时请重新提交预览。')
                return {'jobs':value['jobs'],'reused':True}
            if value['status']!='ready':raise HTTPException(409,'请等待正文读取完成后再确认导入。')
            for part in data.parts:
                try:document_imports.clean_text(part.text)
                except ValueError as exc:raise HTTPException(400,str(exc))
                if not part.title.strip():raise HTTPException(400,'每份脚本都需要名称。')
            try:client=s.ai_client() if data.auto_ai else None
            except ValueError as exc:raise HTTPException(400,str(exc))
            jobs=[]
            for part in data.parts:
                item=s.new_job(part.title.strip(),'script',data.facts);id=item['id'];jobs.append(id)
                s.update(id,raw=part.text.strip(),corrected=part.text.strip(),auto_ai=data.auto_ai,operation='script-import',
                    import_preview_id=preview_id,source_document_name=value['title'],project=data.project.strip(),product_label=data.product_label.strip(),
                    asr_timed=False,message='已确认导入，等待分析结构…')
            store.update(preview_id,jobs=jobs,confirmation_digest=digest,confirmed_parts=[p.model_dump() for p in data.parts],status='confirmed',message='已按确认的拆分分别导入。')
            for id in jobs:s.AI_POOL.submit(s.script_work,id,client)
        return {'jobs':jobs,'reused':False}

    @s.app.get('/api/tasks')
    def tasks():
        with s.LOCK:
            rows=[{'id':r['id'],'title':r['title'],'status':r['status'],'operation':r.get('operation',''),'message':r['message'],
                'progress':r.get('generation_progress'),'error_stage':r.get('error_stage','') if r['status']=='error' else '',
                'remaining':sum(max(0,b.get('requested_count',0)-len(b['variants'])) for b in r.get('batches',[])),
                'updated':r.get('updated',r['created'])} for r in s.JOBS.values() if not r.get('deleted_at')]
        return sorted(rows,key=lambda r:(r['status'] not in ('working','queued'),-r['updated']))
