"""Prepare signed app updates; the desktop launcher hands off after it exits."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import threading
import uuid

from client.updates import signed_update,local_version
from client.update_trust import verify,download


class AppUpdates:
    def __init__(self):
        self.root=Path(os.environ['COPY_STUDIO_BUNDLE']).resolve() if os.environ.get('COPY_STUDIO_BUNDLE') else None
        self.data=Path(os.environ['COPY_STUDIO_CLIENT_DATA']).resolve() if os.environ.get('COPY_STUDIO_CLIENT_DATA') else None
        self.busy=False;self.writers=0;self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=1)
        self.current={'phase':'idle','message':''}

    @property
    def supported(self):return bool(self.root and self.data)

    def state(self):
        with self.lock:
            if self.busy:return dict(self.current,supported=self.supported)
        try:value=json.loads((self.data/'updates/status.json').read_text(encoding='utf-8')) if self.data else {}
        except (OSError,ValueError):value={}
        return dict(value,supported=self.supported)

    def set(self,**values):
        with self.lock:self.current=dict(values)

    def begin(self,requested,busy):
        with self.lock:
            if not self.supported:raise ValueError('此入口用于完整离线客户端；在线版请使用安装管理器更新。')
            if self.busy:raise ValueError('正在准备更新，请稍候。')
            if self.writers or busy():raise ValueError('还有任务或资料保存正在进行，请完成后再更新。')
            self.busy=True;self.set(phase='downloading',message='正在核验新版清单和程序包，资料与模型保留…')
            self.pool.submit(self.prepare,requested)

    def prepare(self,requested):
        try:
            result=signed_update(local_version())
            if not result['update_available'] or result['latest']!=requested:raise ValueError('版本信息已变化，请重新检查更新。')
            if not result['compatible']:raise ValueError('本次运行资源不兼容，请使用完整安装包。')
            payload=verify(result['envelope'])
            folder=self.data/'updates'/uuid.uuid4().hex;folder.mkdir(parents=True)
            package=folder/payload['package']['name']
            download(payload,package,lambda message:self.set(phase='downloading',message=message))
            helper=folder/'helper';(helper/'client').mkdir(parents=True)
            source=Path(__file__).resolve().parents[3]
            for name in ('app_update_worker.py','offline_client.py'):shutil.copy2(source/'scripts'/name,helper/name)
            for name in ('__init__.py','update_trust.py'):shutil.copy2(source/'assets/studio/client'/name,helper/'client'/name)
            plan={'root':str(self.root),'data':str(self.data),'package':str(package),'envelope':result['envelope']}
            plan_path=folder/'plan.json';plan_path.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
            self.set(phase='ready',message='下载校验完成，客户端即将重启；启动失败会自动恢复旧版。',plan=str(plan_path))
        except Exception as exc:
            self.set(phase='error',message=str(exc))
            if self.data:
                target=self.data/'updates';target.mkdir(parents=True,exist_ok=True)
                (target/'status.json').write_text(json.dumps(self.current,ensure_ascii=False),encoding='utf-8')
            with self.lock:self.busy=False
