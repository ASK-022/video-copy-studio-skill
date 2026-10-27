"""Explicit append-only exports to a user-configured Feishu electronic spreadsheet."""
import hashlib
import json
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit, parse_qs

import httpx
from pydantic import BaseModel, Field

from client.security import seal, unseal
from client.draft_exports import DraftTextExport, table_payload


class FeishuRequestError(ValueError):
    def __init__(self,message,ambiguous=False):
        super().__init__(message);self.ambiguous=ambiguous


class FeishuSettings(BaseModel):
    app_id: str = Field(default='',max_length=100)
    secret: str = Field(default='',max_length=500)
    target_url: str = Field(default='',max_length=2000)
    sheet_id: str = Field(default='',max_length=100)
    clear: bool = False


def target_parts(url, sheet_id=''):
    parsed=urlsplit(url.strip())
    if (parsed.scheme!='https' or not (parsed.hostname or '').endswith('.feishu.cn')
            or parsed.username or parsed.password or parsed.port not in (None,443)):
        raise ValueError('请填写 https://你的空间.feishu.cn/sheets/… 电子表格链接。')
    match=re.fullmatch(r'/sheets/([A-Za-z0-9_-]+)/?',parsed.path)
    if not match:
        raise ValueError('本版直写支持飞书电子表格（/sheets/ 链接）；请在飞书打开电子表格并复制链接，暂不支持多维表格或知识库链接。')
    sheet_id=sheet_id.strip() or parse_qs(parsed.query).get('sheet',[''])[0]
    if sheet_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',sheet_id):
        raise ValueError('工作表 ID 格式不正确。')
    return match[1],sheet_id


class FeishuStore:
    def __init__(self, state, transport=None):
        self.path=Path(state)/'feishu.json';self.receipts=Path(state)/'feishu-syncs.json'
        self.lock=threading.RLock();self.transport=transport

    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}

    def write(self,path,data):
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

    def public(self):
        with self.lock:config=self.read()
        return {k:config.get(k,'') for k in ('app_id','target_url','sheet_id')}|{'has_secret':bool(config.get('encrypted_secret'))}

    def save(self,data):
        with self.lock:
            config=self.read()
            if data.clear:
                self.write(self.path,{});return self.public()
            app_id=data.app_id.strip();url=data.target_url.strip()
            if not re.fullmatch(r'cli_[A-Za-z0-9_-]+',app_id):raise ValueError('请填写飞书企业自建应用的 App ID（cli_ 开头）。')
            _,sheet_id=target_parts(url,data.sheet_id)
            if config.get('app_id')!=app_id and not data.secret.strip():
                raise ValueError('更换 App ID 时，请同时填写对应的 App Secret。')
            encrypted=seal(data.secret.strip()) if data.secret.strip() else config.get('encrypted_secret','')
            if not encrypted:raise ValueError('请填写 App Secret。')
            self.write(self.path,{'app_id':app_id,'target_url':url,'sheet_id':sheet_id,'encrypted_secret':encrypted})
            return self.public()

    def request(self,client,method,path,**kwargs):
        try:
            response=client.request(method,path,**kwargs)
            response.raise_for_status();body=response.json()
        except (httpx.HTTPError,ValueError) as exc:
            definite=isinstance(exc,httpx.HTTPStatusError) and 400<=exc.response.status_code<500
            raise FeishuRequestError('飞书请求未完成，请检查网络、应用权限与目标表格授权。',ambiguous=not definite) from exc
        if body.get('code')!=0:
            # Do not reflect remote diagnostic strings which may contain request credentials.
            code=body.get('code');code=code if isinstance(code,int) else '未知'
            raise FeishuRequestError(f'飞书返回错误码 {code}。请检查应用已发布、表格读写权限已生效，并把应用添加为目标表格协作者。')
        return body

    def connect(self,client,config):
        if not config.get('encrypted_secret'):raise ValueError('请先到「设置 → 服务商 → 飞书表格」配置应用与目标表格。')
        token=self.request(client,'POST','auth/v3/tenant_access_token/internal',json={
            'app_id':config['app_id'],'app_secret':unseal(config['encrypted_secret'])}).get('tenant_access_token')
        if not token:raise ValueError('飞书未返回访问凭证，请检查应用配置。')
        client.headers['Authorization']='Bearer '+token
        spreadsheet,sheet_id=target_parts(config['target_url'],config.get('sheet_id',''))
        data=self.request(client,'GET',f'sheets/v3/spreadsheets/{spreadsheet}/sheets/query').get('data',{})
        sheets=[s for s in data.get('sheets',[]) if s.get('resource_type','sheet')=='sheet' and not s.get('hidden')]
        selected=next((s for s in sheets if s['sheet_id']==sheet_id),None) if sheet_id else (sheets[0] if len(sheets)==1 else None)
        if sheet_id and not selected:raise ValueError('目标工作表不存在或已隐藏，请重新测试并选择工作表。')
        if selected and not re.fullmatch(r'[A-Za-z0-9_-]+',selected['sheet_id']):raise ValueError('飞书返回的工作表 ID 无效。')
        return spreadsheet,sheets,selected

    def client(self):
        return httpx.Client(base_url='https://open.feishu.cn/open-apis/',timeout=45,trust_env=False,follow_redirects=False,transport=self.transport)

    def test(self):
        with self.lock:
            with self.client() as client:
                _,sheets,selected=self.connect(client,self.read())
        return {'sheets':[{'id':s['sheet_id'],'title':s['title']} for s in sheets],
                'sheet_id':selected['sheet_id'] if selected else '',
                'message':'已读取目标表格；测试不写入文案。请选择并保存目标工作表。'}

    def sync(self,item,request:DraftTextExport):
        payload=table_payload(item,request);rows=payload['rows'];headers=payload['headers']
        last_column=chr(64+len(headers))
        if len(rows)>4999:raise ValueError('飞书单次最多写入 4999 条文案，请分次勾选导入。')
        with self.lock:
            config=self.read()
            with self.client() as client:
                spreadsheet,_,selected=self.connect(client,config)
                if not selected:raise ValueError('目标有多张工作表，请先在飞书配置中测试连接、选择工作表并保存。')
                sheet=selected['sheet_id'];row_count=selected.get('grid_properties',{}).get('row_count',1000)
                if row_count>50000:raise ValueError('目标工作表过大，请为文案新建一张工作表后配置。')
                values=self.request(client,'GET',f'sheets/v2/spreadsheets/{spreadsheet}/values/{sheet}!A1:{last_column}{max(1,row_count)}',
                                    params={'valueRenderOption':'ToString'}).get('data',{}).get('valueRange',{}).get('values',[]) or []
                while values and not any(v not in ('',None) for v in values[-1]):values.pop()
                if values and values[0]!=headers:
                    raise ValueError(f'目标 A1:{last_column}1 表头与所选模板不一致。请为这套模板选择空白工作表，或将首行设为：'+'、'.join(headers)+'。')
                identity=json.dumps({'app':config['app_id'],'target':[spreadsheet,sheet],'job':item['id'],
                                     'batch':request.batch_id,'headers':headers,'rows':rows},sort_keys=True,ensure_ascii=False)
                fingerprint=hashlib.sha256(identity.encode()).hexdigest()
                receipts=json.loads(self.receipts.read_text(encoding='utf-8')) if self.receipts.exists() else {}
                previous=receipts.get(fingerprint)
                if previous:
                    if previous.get('status')=='done':return previous['result']|{'duplicate':True}
                    raise ValueError('同一批文案上次写入的结果尚未确认，为避免重复写入，请先到飞书核对；可先使用本地 Excel 导出。')
                upload=rows if values else [headers,*rows]
                start=len(values)+1
                receipts[fingerprint]={'status':'pending'};self.write(self.receipts,receipts)
                # Exactly one write; ambiguous failures stay pending and are never automatically retried.
                try:
                    reply=self.request(client,'POST',f'sheets/v2/spreadsheets/{spreadsheet}/values_append',
                        params={'insertDataOption':'INSERT_ROWS'},json={'valueRange':{
                            'range':f'{sheet}!A{start}:{last_column}{start+len(upload)-1}','values':upload}})
                except FeishuRequestError as exc:
                    if not exc.ambiguous:
                        receipts.pop(fingerprint,None);self.write(self.receipts,receipts)
                    raise
                result={'count':len(rows),'script_count':len(request.items),'template':request.template,'sheet_title':selected['title'],'url':config['target_url'],
                        'range':reply.get('data',{}).get('updates',{}).get('updatedRange',''),'duplicate':False}
                receipts[fingerprint]={'status':'done','result':result};self.write(self.receipts,receipts)
                return result
