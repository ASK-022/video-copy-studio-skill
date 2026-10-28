"""Durable, append-only script versions. Generated variants remain immutable."""
import copy
import hashlib
import json
from pathlib import Path
import re
import time


def source_text(variant):
    return '\n\n'.join(s['text'] for s in variant['segments'])


def script(item, batch_id, index):
    batch=next((b for b in item['batches'] if b['id']==batch_id),None)
    if batch is None or not 0<=index<len(batch['variants']):raise ValueError('未找到这个批次的脚本。')
    return batch,batch['variants'][index]


def aligned(reference, segments):
    if not isinstance(segments,list) or len(segments)!=len(reference):raise ValueError('段数必须与原结构一致。')
    if [(s.get('id'),s.get('role')) for s in segments]!=[(s['id'],s['role']) for s in reference]:
        raise ValueError('段落编号、功能和顺序必须与原结构一致。')
    if any(not isinstance(s.get('text'),str) or not s['text'].strip() for s in segments):raise ValueError('每段文案都需要填写内容。')
    return [{'id':s['id'],'role':s['role'],'text':s['text'].strip()} for s in segments]


def infer_segments(reference, text):
    parts=re.split(r'\n\s*\n',text.strip())
    if len(parts)!=len(reference):return None
    return [dict(id=s['id'],role=s['role'],text=t) for s,t in zip(reference,parts)]


def history_path(folder,batch_id,index):
    key=hashlib.sha256(batch_id.encode()).hexdigest()[:24]
    return Path(folder)/'manuscripts'/f'{key}-{index}.json'


def versions(folder,item,batch_id,index):
    batch,variant=script(item,batch_id,index)
    path=history_path(folder,batch_id,index)
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))['versions']
    return [{'revision':0,'created':batch.get('created',0),'kind':'generated','text':source_text(variant),
             'segments':copy.deepcopy(variant['segments']),'note':'生成原稿'}]


def current(folder,item,batch_id,index):
    value=copy.deepcopy(versions(folder,item,batch_id,index)[-1]);return value


def save(folder,item,batch_id,index,base_revision,text,segments=None,kind='edit',note='',restored_from=None):
    batch,variant=script(item,batch_id,index);rows=versions(folder,item,batch_id,index)
    if rows[-1]['revision']!=base_revision:raise FileExistsError('其他窗口已保存了新版本。当前修改仍保留，可在版本记录中另存。')
    text=text.replace('\r\n','\n').replace('\r','\n').strip()
    if not text or len(text)>20000 or '\x00' in text:raise ValueError('成稿需要 1–20000 字，不能包含无效字符。')
    if segments is not None:
        if text!='\n\n'.join(s.get('text','') for s in segments).strip():raise ValueError('完整文案与分段内容不一致。')
        segments=aligned(batch.get('reference',variant['segments']),segments)
        text='\n\n'.join(s['text'] for s in segments)
    else:segments=infer_segments(batch.get('reference',variant['segments']),text)
    if kind=='edit' and rows[-1]['text']==text and rows[-1].get('segments')==segments:return copy.deepcopy(rows[-1])
    value={'revision':rows[-1]['revision']+1,'created':time.time(),'kind':kind,'text':text,
           'segments':segments,'note':note[:500]}
    if restored_from is not None:value['restored_from']=restored_from
    path=history_path(folder,batch_id,index);path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix('.tmp');pending.write_text(json.dumps({'versions':rows+[value]},ensure_ascii=False),encoding='utf-8');pending.replace(path)
    return copy.deepcopy(value)


def attach(folder,item):
    for batch in item.get('batches',[]):
        for i,variant in enumerate(batch['variants']):
            if history_path(folder,batch['id'],i).exists():variant['manuscript']=current(folder,item,batch['id'],i)
    return item
