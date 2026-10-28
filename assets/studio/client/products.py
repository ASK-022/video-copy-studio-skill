"""Reusable local product facts with explicit confirmation and version history."""
import copy
import json
from pathlib import Path
import time
import uuid
from pydantic import BaseModel,Field


class ProductInput(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    aliases:str=Field(default='',max_length=500)
    facts:str=Field(min_length=1,max_length=4000)
    pending:str=Field(default='',max_length=2000)
    forbidden:str=Field(default='',max_length=1500)
    audience:str=Field(default='',max_length=300)
    tone:str=Field(default='',max_length=100)
    source:str=Field(default='',max_length=2000)
    confirmed:bool=False
    base_version:int=Field(default=0,ge=0,strict=True)


def load(root):
    path=Path(root)/'products.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'products':[]}


def write(root,data):
    path=Path(root)/'products.json';pending=path.with_suffix('.tmp')
    pending.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');pending.replace(path)


def list_products(root):
    return [copy.deepcopy(p) for p in load(root)['products'] if not p.get('archived')]


def get(root,product_id):
    product=next((p for p in load(root)['products'] if p['id']==product_id and not p.get('archived')),None)
    if product is None:raise ValueError('商品不存在或已归档。')
    return copy.deepcopy(product)


def material(product):
    text='商品：'+product['name']+'\n已确认卖点：\n'+product['facts']
    if product.get('aliases'):text+='\n专有名词：'+product['aliases']
    return text


def save(root,data,product_id=None):
    if not data.confirmed:raise ValueError('请核对已确认卖点，并勾选确认；待确认信息不会用于生成。')
    if not data.name.strip() or not data.facts.strip():raise ValueError('请填写商品名称与已确认卖点。')
    saved=load(root);old=next((p for p in saved['products'] if p['id']==product_id),None) if product_id else None
    if product_id and (old is None or old.get('archived')):raise ValueError('商品不存在或已归档。')
    if data.base_version!=(old['version'] if old else 0):raise FileExistsError('商品已在其他窗口更新，请重新打开后编辑。')
    value={k:v.strip() if isinstance(v,str) else v for k,v in data.model_dump(exclude={'base_version','confirmed'}).items()}
    value.update(id=product_id or uuid.uuid4().hex,version=(old['version']+1 if old else 1),updated=time.time(),confirmed=True)
    if len(material(value))>5000:raise ValueError('商品名称、专名和已确认卖点合计请控制在 5000 字内。')
    value['history']=copy.deepcopy(old.get('history',[]) if old else [])
    if old:value['history'].append({k:v for k,v in old.items() if k!='history'})
    if old:saved['products'][saved['products'].index(old)]=value
    else:saved['products'].append(value)
    write(root,saved);return copy.deepcopy(value)


def archive(root,product_id):
    saved=load(root);old=next((p for p in saved['products'] if p['id']==product_id),None)
    if old is None:raise ValueError('商品不存在。')
    old['archived']=True;write(root,saved)
