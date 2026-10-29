"""App-only transactions; never writes Models, Runtime, Engine, Browsers or user data.

Executed from a private copy outside App by the existing Python runtime. Recovery
uses the journal and same-volume rename, including an interrupted process.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

from offline_client import atomic_json,read_json,close_service,start

NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
TERMINAL=('committed','rolled_back','aborted')


def durable_json(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf-8') as output:
        json.dump(value,output,ensure_ascii=False,indent=2);output.flush();os.fsync(output.fileno())
    os.replace(temporary,path)


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def replace(source,target):
    # The one-file bootloader may still be cleaning up after its app released the mutex.
    deadline=time.monotonic()+20
    while True:
        try:os.replace(source,target);return
        except PermissionError:
            if time.monotonic()>=deadline:raise
            time.sleep(.25)


@contextmanager
def transaction_lock(root):
    folder=Path(root)/'.updates';folder.mkdir(exist_ok=True)
    with (folder/'lock').open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise ValueError('另一个升级器正在工作，请稍后再打开客户端。') from exc
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)


def status(data,**values):
    folder=Path(data)/'updates';folder.mkdir(parents=True,exist_ok=True)
    atomic_json(folder/'status.json',dict(values,at=time.time()))


def safe_extract(package,target,version):
    names=set();total=0
    with zipfile.ZipFile(package) as archive:
        for item in archive.infolist():
            name=item.filename;parts=PurePosixPath(name).parts
            key=name.casefold().rstrip('/')
            if (not parts or chr(92) in name or ':' in name or name.startswith('/') or any(p in ('.','..') or p.endswith((' ','.')) for p in parts)
                or key in names or (item.external_attr>>16)&0o170000==0o120000):raise ValueError('更新包包含不安全的路径。')
            if parts[0] not in ('App','VideoCopyStudio.exe','offline-client.json'):raise ValueError('更新包试图修改运行资源。')
            if parts[0]!='App' and len(parts)!=1:raise ValueError('更新路径无效。')
            if any(p.casefold() in ('.studio','.env','providers.json','runtime.json','jobs','models','__pycache__') for p in parts[1:]):raise ValueError('更新包含个人资料或运行资源。')
            total+=item.file_size
            if total>150*1024*1024:raise ValueError('更新解压大小超出限制。')
            names.add(key)
        for item in archive.infolist():
            path=target.joinpath(*PurePosixPath(item.filename).parts)
            if not path.resolve().is_relative_to(target.resolve()):raise ValueError('更新路径越界。')
            if item.is_dir():path.mkdir(parents=True,exist_ok=True);continue
            path.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as source,path.open('wb') as dest:shutil.copyfileobj(source,dest)
    if not (target/'App/VERSION').is_file() or (target/'App/VERSION').read_text().strip()!=version:raise ValueError('更新包内部版本不匹配。')
    info=read_json(target/'offline-client.json')
    if info.get('version')!=version or info.get('resource_contract')!=1:raise ValueError('运行资源契约不匹配。')
    for name in ('App/assets/studio/client/app.py','App/scripts/offline_client.py','VideoCopyStudio.exe'):
        if not (target/name).is_file():raise ValueError('更新包不完整。')


def rollback(root,transaction):
    backup=transaction/'backup'
    # Existence of the renamed original is the durable evidence for each action.
    if (backup/'App').exists():
        if (root/'App').exists():
            failed=transaction/('failed-App-'+uuid.uuid4().hex)
            replace(root/'App',failed)
        replace(backup/'App',root/'App')
    for name in ('VideoCopyStudio.exe','offline-client.json'):
        if (backup/name).exists():
            if (root/name).is_file() and sha256(root/name)==sha256(backup/name):continue
            temporary=root/(name+'.restore')
            shutil.copy2(backup/name,temporary);replace(temporary,root/name)


def recover(root,data):
    root=Path(root).resolve()
    with transaction_lock(root):
        for transaction in sorted((root/'.updates').glob('txn-*')):
            journal=read_json(transaction/'journal.json')
            if journal and journal.get('phase') not in TERMINAL:
                state=read_json(Path(data)/'offline-state.json')
                if state.get('bundle')==str(root):close_service(state)
                rollback(root,transaction)
                durable_json(transaction/'journal.json',dict(journal,phase='rolled_back'))
                status(data,phase='rolled_back',message='上次更新意外中断，已恢复旧版程序。资料、Key 和模型保持原位置。')


def validate_root(root,data):
    root=Path(root).resolve();data=Path(data).resolve()
    if root.is_symlink() or data.is_relative_to(root/'App'):raise ValueError('资料目录不能位于待替换的 App 目录内。')
    for name in ('App','Runtime','Models','Browsers','Engine','.updates'):
        path=root/name
        if path.is_symlink() or (path.exists() and not path.resolve().is_relative_to(root)):raise ValueError('程序目录包含外部链接，不能自动更新。')
    if read_json(root/'offline-client.json').get('format')!='video-copy-studio-offline/v1':raise ValueError('请选择完整离线客户端目录。')
    if (root/'App/.studio').exists():raise ValueError('检测到 App 内的旧资料，请先迁移到独立资料目录。')
    return root,data


def apply(root,data,package,envelope,probe=None,relaunch=True,after_step=lambda *_:None):
    # Import from this helper's copied client package, never the changing App.
    from client.update_trust import verify,version
    root,data=validate_root(root,data);payload=verify(envelope)
    current=(root/'App/VERSION').read_text().strip()
    if version(payload['version'])<=version(current):raise ValueError('当前版本相同或更新，禁止降级覆盖。')
    if version(current)<version(payload['min_version']):raise ValueError('旧版运行资源不兼容，请使用完整安装包。')
    package=Path(package)
    if package.stat().st_size!=payload['package']['bytes'] or sha256(package)!=payload['package']['sha256']:raise ValueError('更新包 SHA256 校验失败。')
    with transaction_lock(root):
        transaction=root/'.updates'/('txn-'+uuid.uuid4().hex);transaction.mkdir();new=transaction/'new';new.mkdir()
        journal={'phase':'preparing','from':current,'to':payload['version']}
        def phase(value):
            journal['phase']=value;durable_json(transaction/'journal.json',journal);after_step(value)
        phase('preparing')
        try:
            if shutil.disk_usage(root).free<500*1024*1024:raise ValueError('升级至少需要 500MB 可用空间。')
            safe_extract(package,new,payload['version'])
            backup=transaction/'backup';backup.mkdir()
            for name in ('VideoCopyStudio.exe','offline-client.json'):shutil.copy2(root/name,backup/name)
            phase('prepared')
            close_service(read_json(data/'offline-state.json'))
            # Windows must release the launcher and its singleton mutex before here.
            from offline_client import single_client
            with single_client(data) as acquired:
                if not acquired:raise ValueError('请先关闭当前离线客户端窗口，再运行升级器。')
                phase('swapping')
                replace(root/'App',backup/'App');after_step('old_app_saved')
                replace(new/'App',root/'App');after_step('new_app_installed')
                for name in ('VideoCopyStudio.exe','offline-client.json'):replace(new/name,root/name)
                phase('testing')
                status(data,phase='testing',message='正在验证新版启动，失败将自动恢复旧版…')
                if probe:probe(root,data)
                else:
                    # The old launcher module in this separate process starts and probes the new backend.
                    locations,state=start(root,data)
                    from offline_client import request
                    health=request(state['url'],'/api/health')
                    if health.get('version')!=payload['version'] or not health.get('update_ready'):raise ValueError('新版启动健康检查未通过。')
                phase('committed')
                status(data,phase='committed',version=payload['version'],message='已更新到 v'+payload['version']+'，已复用原模型和运行环境，资料与 Key 保留。')
        except BaseException as exc:
            if journal['phase'] in ('swapping','testing'):
                try:close_service(read_json(data/'offline-state.json'))
                finally:rollback(root,transaction)
                phase('rolled_back')
                status(data,phase='rolled_back',message='新版未通过启动验证，已恢复 v'+current+'。资料、Key 和模型保持原位置。',error=str(exc)[:800])
            else:
                phase('aborted');status(data,phase='aborted',message='升级未完成，原程序保持可用。',error=str(exc)[:800])
            if relaunch:launch(root,data)
            raise
    if relaunch:launch(root,data)


def launch(root,data):
    env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1')
    if getattr(sys,'frozen',False):
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:subprocess.Popen([str(root/'VideoCopyStudio.exe'),'--data-dir',str(data)],cwd=root,env=env,creationflags=NO_WINDOW)
    finally:
        if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(str(Path(sys._MEIPASS)))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path,required=True);args=parser.parse_args()
    plan=read_json(args.plan)
    time.sleep(1)  # parent launcher exits and releases Windows executable/mutex
    for _ in range(40):
        from offline_client import single_client
        with single_client(plan['data']) as acquired:
            if acquired:break
        time.sleep(.25)
    apply(Path(plan['root']),Path(plan['data']),Path(plan['package']),plan['envelope'])


if __name__=='__main__':
    try:main()
    except Exception as exc:
        if sys.stderr:print(str(exc),file=sys.stderr)
        sys.exit(1)
