"""Independent AI provider profiles; the selected profile also updates the legacy config."""
import copy
import json
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import urlparse

from client.ai import AIClient
from client.security import seal, unseal


class ProviderStore:
    def __init__(self,root):
        self.root=Path(root)
        self.path=self.root/'providers.json'
        self.lock=threading.RLock()

    def _write(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(path)

    def _load(self):
        if self.path.exists():return json.loads(self.path.read_text(encoding='utf-8'))
        legacy=self.root/'ai.json'
        config=json.loads(legacy.read_text(encoding='utf-8')) if legacy.exists() else {
            'base_url':'https://api.deepseek.com','model':'deepseek-flash','encrypted_key':''}
        profile={'id':'default-ai','name':'DeepSeek' if urlparse(config['base_url']).hostname=='api.deepseek.com' else '原有 AI 服务',
                 'base_url':config['base_url'],'model':config['model'],
                 'encrypted_key':config.get('encrypted_key',''),'json_mode':config.get('json_mode',True),
                 'created':time.time(),'deleted_at':None}
        data={'version':1,'active_ai_id':profile['id'],'providers':[profile]}
        self._commit(data)
        return data

    def _find(self,data,provider_id):
        for profile in data['providers']:
            if profile['id']==provider_id and not profile.get('deleted_at'):return profile
        raise ValueError('服务商不存在或已移除。')

    def _commit(self,data):
        self._write(self.path,data)
        active=self._find(data,data['active_ai_id'])
        # Preserve compatibility with the existing local scripts and encrypted config.
        self._write(self.root/'ai.json',{k:active[k] for k in ('base_url','model','encrypted_key')}|{'json_mode':active.get('json_mode',True)})

    @staticmethod
    def _public(profile,active):
        return {**{k:profile[k] for k in ('id','name','base_url','model')},
                'json_mode':profile.get('json_mode',True),'has_key':bool(profile.get('encrypted_key')),'active':profile['id']==active}

    def listing(self):
        with self.lock:
            data=self._load()
            return {'active_ai_id':data['active_ai_id'],
                    'providers':[self._public(p,data['active_ai_id']) for p in data['providers'] if not p.get('deleted_at')]}

    def active(self):
        with self.lock:
            data=self._load()
            return copy.deepcopy(self._find(data,data['active_ai_id']))

    def save(self,provider_id,*,name,base_url,model,key='',clear_key=False,json_mode=None):
        name=name.strip();model=model.strip();base_url=base_url.strip().rstrip('/')
        parsed=urlparse(base_url)
        if not name or not model:raise ValueError('请填写服务商名称和模型名称。')
        if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('请输入有效的接口基础地址。')
        if parsed.scheme=='http' and parsed.hostname not in ('127.0.0.1','localhost'):
            raise ValueError('远程 AI 接口请使用 HTTPS。')
        with self.lock:
            data=self._load()
            if provider_id:
                profile=self._find(data,provider_id)
                if profile['base_url'].rstrip('/')!=base_url and profile.get('encrypted_key') and not key.strip() and not clear_key:
                    raise ValueError('更换接口地址时，请重新填写对应服务商的 Key。')
            else:
                profile={'id':uuid.uuid4().hex,'created':time.time(),'encrypted_key':'','deleted_at':None}
                data['providers'].append(profile)
            encrypted='' if clear_key else seal(key.strip()) if key.strip() else profile.get('encrypted_key','')
            profile.update(name=name,base_url=base_url,model=model,encrypted_key=encrypted)
            if json_mode is not None:profile['json_mode']=json_mode
            self._commit(data)
            return self._public(profile,data['active_ai_id'])

    def select(self,provider_id):
        with self.lock:
            data=self._load();profile=self._find(data,provider_id)
            if not profile.get('encrypted_key'):raise ValueError('请先为这个服务商填写 API Key。')
            data['active_ai_id']=provider_id
            self._commit(data)
            return self._public(profile,provider_id)

    def remove(self,provider_id):
        with self.lock:
            data=self._load();profile=self._find(data,provider_id)
            if data['active_ai_id']==provider_id:raise ValueError('该服务商正在使用，请先切换到其他服务商再移除。')
            profile['deleted_at']=time.time()
            self._commit(data)

    def client(self,provider_id=None):
        with self.lock:
            data=self._load();profile=copy.deepcopy(self._find(data,provider_id or data['active_ai_id']))
        if not profile.get('encrypted_key'):raise ValueError('请先在「设置 → 服务商」为选用的服务商填写 API Key。')
        client=AIClient(profile['base_url'],profile['model'],unseal(profile['encrypted_key']),json_mode=profile.get('json_mode',True))
        client.provider_id=profile['id'];client.provider_name=profile['name']
        return client
