"""Versioned desktop launcher and transactional updater. Personal data is never moved."""
import argparse,base64,ctypes,hashlib,hmac,json,os,re,secrets,shutil,subprocess,sys,time,zipfile
from pathlib import Path

FILES=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
REPOSITORY='ASK-022/video-copy-studio-skill'
class WindowsJob:
    """A failed or killed update worker must not leave its new backend running."""
    def __init__(self):
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_=[('ProcessTime',ctypes.c_longlong),('JobTime',ctypes.c_longlong),('LimitFlags',w.DWORD),('Min',ctypes.c_size_t),('Max',ctypes.c_size_t),('Active',w.DWORD),('Affinity',ctypes.c_size_t),('Priority',w.DWORD),('Scheduling',w.DWORD)]
        class IO(ctypes.Structure):_fields_=[(name,ctypes.c_ulonglong) for name in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]
        class Extended(ctypes.Structure):_fields_=[('Basic',Basic),('IO',IO),('ProcessMemory',ctypes.c_size_t),('JobMemory',ctypes.c_size_t),('PeakProcess',ctypes.c_size_t),('PeakJob',ctypes.c_size_t)]
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True);self.info=Extended()
        self.kernel.CreateJobObjectW.restype=ctypes.c_void_p
        self.kernel.SetInformationJobObject.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        self.kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        self.handle=self.kernel.CreateJobObjectW(None,None)
        self.info.Basic.LimitFlags=0x2000
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(self.info),ctypes.sizeof(self.info)):raise OSError(ctypes.get_last_error(),'无法创建更新进程保护')
    def assign(self,child):
        if not self.kernel.AssignProcessToJobObject(self.handle,ctypes.c_void_p(int(child._handle))):raise OSError(ctypes.get_last_error(),'无法保护更新进程')
    def close(self,keep=False):
        if not self.handle:return
        if keep:
            self.info.Basic.LimitFlags=0
            if not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(self.info),ctypes.sizeof(self.info)):raise OSError(ctypes.get_last_error(),'无法确认新版本进程')
        self.kernel.CloseHandle(self.handle);self.handle=None
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+secrets.token_hex(5)+'.tmp')
    with temporary.open('wb') as stream:stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()
def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}',value):raise ValueError('版本号无效')
    return tuple(map(int,value.split('.')))
def safe(root,name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or any(p in ('','..','.') for p in name.split('/')):raise ValueError('更新包含无效路径')
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()) or path==root.resolve():raise ValueError('更新路径越界')
    return Path('\\\\?\\'+str(path)) if os.name=='nt' and not str(path).startswith('\\\\?\\') else path
def verify(envelope):
    payload=envelope['payload'];signature=base64.b64decode(envelope['signature'],validate=True)
    key=read(FILES/'contenthub-update-public.json');modulus=int.from_bytes(base64.b64decode(key['modulus']),'big');size=(modulus.bit_length()+7)//8
    if len(signature)!=size or int.from_bytes(signature,'big')>=modulus:raise ValueError('更新签名无效')
    actual=pow(int.from_bytes(signature,'big'),key['exponent'],modulus).to_bytes(size,'big')
    digest=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(canonical(payload)).digest()
    if not hmac.compare_digest(actual,b'\0\1'+b'\xff'*(size-len(digest)-3)+b'\0'+digest):raise ValueError('更新签名无效')
    if payload['format']!='contenthub-desktop-update/v1' or payload['repository']!=REPOSITORY or payload['resource_contract']!=1:raise ValueError('更新产品或资源版本不匹配')
    version(payload['version']);version(payload['min_version'])
    if not 1<=len(payload['packages'])<=20:raise ValueError('更新包清单无效')
    for item in payload['packages']:
        if item['base_version']!='*':version(item['base_version'])
        if not re.fullmatch(r'ContentHub-[A-Za-z0-9._-]+\.zip',item['name']) or not re.fullmatch('[0-9a-f]{64}',item['sha256']) or type(item['bytes']) is not int or not 0<item['bytes']<2*1024**3:raise ValueError('更新包描述无效')
    return payload
def metadata(directory,expected=None):
    meta=read(directory/'contenthub-version.json');version(meta['version'])
    if expected and meta['version']!=expected:raise ValueError('程序版本与更新清单不一致')
    if meta['resource_contract']!=1 or not 1<=len(meta['files'])<=50000:raise ValueError('程序资源清单无效')
    seen=set();total=0
    for name,entry in meta['files'].items():
        safe(directory,name);fold=name.casefold()
        if fold in seen or not re.fullmatch('[0-9a-f]{64}',entry['sha256']) or type(entry['bytes']) is not int or entry['bytes']<0:raise ValueError('程序文件清单无效')
        seen.add(fold);total+=entry['bytes']
    if total>8*1024**3 or 'ContentHub.exe' not in meta['files']:raise ValueError('程序体积或入口无效')
    return meta
def profile():return Path(os.environ.get('ASKFILM_USER_DATA',str(Path(os.environ['APPDATA'])/'内容中台'))).resolve()
def check_root(root):
    marker=read(root/'contenthub-install.json')
    if marker.get('format')!='contenthub/install/v1' or marker.get('product')!='contenthub-desktop':raise ValueError('不是完整桌面版安装目录')
    return marker
def current(root):
    value=read(root/'current.json');version(value['version']);metadata(root/'versions'/value['version'],value['version']);return value
def is_alive(pid,expected=None):
    if os.name!='nt':
        try:os.kill(pid,0);return True
        except OSError:return False
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)]
    handle=kernel.OpenProcess(0x1000,False,int(pid))
    if not handle:return False
    code=ctypes.c_ulong();ok=kernel.GetExitCodeProcess(handle,ctypes.byref(code));matches=True
    if expected:
        buffer=ctypes.create_unicode_buffer(32768);length=ctypes.c_ulong(len(buffer))
        matches=bool(kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(length))) and os.path.normcase(os.path.realpath(buffer.value))==os.path.normcase(os.path.realpath(expected))
    kernel.CloseHandle(handle);return bool(ok and code.value==259 and matches)
def launch(root,wanted,ack=None,nonce=None,arguments=()):
    directory=root/'versions'/wanted;metadata(directory,wanted)
    env=dict(os.environ,CONTENT_HUB_INSTALL_ROOT=str(root))
    env.pop('ELECTRON_RUN_AS_NODE',None)
    for key in ('CONTENT_HUB_UPDATE_ACK','CONTENT_HUB_UPDATE_NONCE'):env.pop(key,None)
    if ack:env.update(CONTENT_HUB_UPDATE_ACK=str(ack),CONTENT_HUB_UPDATE_NONCE=nonce)
    if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        logs=profile()/'logs';logs.mkdir(parents=True,exist_ok=True)
        with (logs/'desktop-launch.log').open('ab') as output:
            child=subprocess.Popen([str(directory/'ContentHub.exe'),*arguments],cwd=directory,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=output,creationflags=NO_WINDOW)
        write(logs.parent/'desktop-process.json',{'pid':child.pid,'version':wanted,'root':str(root),'started':time.time()});return child
    finally:
        if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(str(FILES))
def result(root,data,status,**extra):
    value={'status':status,'at':time.time(),**extra};write(data/'desktop-update-result.json',value)
    write(root/'update-transaction.json',{'state':'finished',**value})
def backup_metadata(data,token):
    backup=data/'updates'/'backups'/token;backup.mkdir(parents=True)
    files=[]
    # Media and models keep their original locations. Mutable document/config
    # metadata and encrypted keys receive independent byte copies before boot.
    for path in data.rglob('*'):
        relative=path.relative_to(data)
        if relative.parts[0] in ('updates','logs','Cache','Code Cache','GPUCache','Network','ShaderCache','DawnGraphiteCache','DawnWebGPUCache','GrShaderCache'):continue
        if not path.is_file() or path.is_symlink():continue
        if path.suffix.lower() not in ('.json','.key','.enc','.sealed','.toml','.ini','.txt','.md','.html') and path.name not in ('key','byok-keys'):continue
        if path.stat().st_size>20*1024**2:raise ValueError('资料元数据过大，请使用完整安装包')
        destination=safe(backup,relative.as_posix());destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination);files.append(relative.as_posix())
    write(backup/'backup-files.json',files);return token
def restore_metadata(data,token):
    if not re.fullmatch('[0-9a-f]{48}',token):raise ValueError('回滚备份标识无效')
    backup=data/'updates'/'backups'/token
    for name in read(backup/'backup-files.json'):
        source=safe(backup,name);destination=safe(data,name);destination.parent.mkdir(parents=True,exist_ok=True)
        pending=destination.with_name(destination.name+'.rollback.tmp');shutil.copyfile(source,pending);os.replace(pending,destination)
def recover(root,data):
    try:transaction=read(root/'update-transaction.json')
    except FileNotFoundError:return
    if transaction.get('state') not in ('preparing','launching'):return
    if is_alive(transaction.get('worker_pid',0),transaction.get('worker_exe')):raise ValueError('更新正在进行，请稍候再打开')
    old=transaction['previous'];version(old)
    try:
        ack=read(data/'updates'/transaction['ack'])
        ready=ack.get('nonce')==transaction['nonce'] and ack.get('version')==transaction['target'] and is_alive(ack.get('pid',0))
    except (OSError,ValueError,KeyError):ready=False
    if ready:
        write(root/'current.json',{'version':transaction['target'],'previous':old});result(root,data,'updated',version=transaction['target'])
    else:
        if transaction.get('backup'):restore_metadata(data,transaction['backup'])
        write(root/'current.json',{'version':old});result(root,data,'rolled-back',version=old,error='interrupted')
def unpack(root,data,job):
    payload=verify(job['envelope']);old=current(root)['version']
    if version(payload['version'])<=version(old) or version(old)<version(payload['min_version']):raise ValueError('更新版本顺序无效')
    package=next(p for p in payload['packages'] if p['name']==job['package'])
    if package['base_version'] not in ('*',old):raise ValueError('增量包与当前版本不匹配')
    archive=Path(job['archive']).resolve()
    if not archive.is_relative_to((data/'updates').resolve()) or archive.stat().st_size!=package['bytes'] or sha(archive)!=package['sha256']:raise ValueError('更新包校验失败')
    target=payload['version'];stage=root/'versions'/('.staging-'+secrets.token_hex(8));stage.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as source:
            entries=source.infolist();seen=set();total=0
            for entry in entries:
                name=entry.filename
                if entry.is_dir():continue
                safe(stage,name);fold=name.casefold();total+=entry.file_size
                if fold in seen or ((entry.external_attr>>16)&0o170000)==0o120000:raise ValueError('更新包包含重复路径或链接')
                seen.add(fold)
            if total>8*1024**3 or len(entries)>50000:raise ValueError('更新包超出限制')
            meta=json.loads(source.read('contenthub-version.json'))
            if meta['version']!=target:raise ValueError('更新版本标记无效')
            if package['base_version']!='*':
                previous=root/'versions'/old;before=metadata(previous,old)
                for name in meta['files']:
                    if name in before['files'] and name.casefold() not in seen:
                        src=safe(previous,name);dest=safe(stage,name);dest.parent.mkdir(parents=True,exist_ok=True)
                        if src.is_symlink() or not src.is_file():raise ValueError('旧程序文件不完整，请使用完整安装包')
                        try:os.link(src,dest)
                        except OSError:shutil.copyfile(src,dest)
            for entry in entries:
                if entry.is_dir():continue
                name=entry.filename
                if name!='contenthub-version.json' and name not in meta['files']:raise ValueError('更新包包含清单之外的文件')
                dest=safe(stage,name);dest.parent.mkdir(parents=True,exist_ok=True);dest.unlink(missing_ok=True)
                with source.open(entry) as inp,dest.open('xb') as out:shutil.copyfileobj(inp,out)
        meta=metadata(stage,target)
        for name,entry in meta['files'].items():
            path=safe(stage,name)
            if not path.is_file() or path.stat().st_size!=entry['bytes'] or sha(path)!=entry['sha256']:raise ValueError('新程序文件校验失败')
        destination=root/'versions'/target
        if destination.exists():
            metadata(destination,target)
            os.replace(destination,root/'versions'/('.failed-'+target+'-'+secrets.token_hex(8)))
        os.replace(stage,destination);return old,target
    finally:
        if stage.exists():
            assert stage.resolve().is_relative_to((root/'versions').resolve()) and stage.name.startswith('.staging-')
            shutil.rmtree(stage)
def apply(job_path):
    job=read(job_path);root=Path(job['root']).resolve();data=Path(job['data']).resolve();check_root(root)
    if data.is_relative_to(root):raise ValueError('资料目录必须位于程序目录之外')
    if not Path(job_path).resolve().is_relative_to((data/'updates').resolve()):raise ValueError('更新请求路径无效')
    lock=(root/'update.lock').open('a+b')
    import msvcrt
    lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    try:
        recover(root,data)
        deadline=time.monotonic()+60
        while is_alive(job['parent_pid'],job.get('parent_exe')):
            if time.monotonic()>deadline:raise ValueError('客户端尚未退出，未切换程序')
            time.sleep(.2)
        old=current(root)['version'];target=old;switched=False;child=None;protection=None;backup=None
        try:
            if job.get('operation')=='rollback':
                target=current(root).get('previous');version(target);metadata(root/'versions'/target,target)
            else:old,target=unpack(root,data,job)
            nonce=secrets.token_hex(24);ack='boot-'+nonce+'.json'
            backup=backup_metadata(data,nonce)
            transaction={'state':'launching','previous':old,'target':target,'nonce':nonce,'ack':ack,'backup':backup,'worker_pid':os.getpid(),'worker_exe':sys.executable}
            write(root/'update-transaction.json',transaction)
            write(root/'current.json',{'version':target,'previous':old});switched=True
            protection=WindowsJob()
            child=launch(root,target,data/'updates'/ack,nonce)
            protection.assign(child)
            write(root/'update-transaction.json',{**transaction,'child_pid':child.pid})
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if child.poll() is not None:raise ValueError('新版程序提前退出')
                try:
                    ready=read(data/'updates'/ack)
                    if ready.get('nonce')==nonce and ready.get('version')==target and ready.get('pid')==child.pid and ready.get('director') and ready.get('editor'):
                        protection.close(keep=True);protection=None
                        result(root,data,'rolled-back' if job.get('operation')=='rollback' else 'updated',version=target,previous=old);return
                except (OSError,ValueError):pass
                time.sleep(.3)
            raise ValueError('新版双工作台启动超时')
        except Exception as exc:
            import traceback
            (data/'logs').mkdir(parents=True,exist_ok=True)
            with (data/'logs/desktop-updater.log').open('a',encoding='utf-8') as log:traceback.print_exc(file=log)
            if protection:protection.close();protection=None
            if switched:
                if child and child.poll() is None:
                    # Terminate only the process tree started by this transaction.
                    subprocess.run(['taskkill.exe','/PID',str(child.pid),'/T','/F'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=NO_WINDOW)
                if backup:restore_metadata(data,backup)
                write(root/'current.json',{'version':old});result(root,data,'rolled-back',version=old,error='startup-failed')
            else:result(root,data,'failed',version=old,error='validation-failed',detail=str(exc)[:500])
            launch(root,old)
    finally:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()
def remove_program(directory):
    """Called by the copied NSIS uninstaller helper; never remove a profile or models."""
    root=Path(directory).resolve();check_root(root);versions=root/'versions';data=profile()
    if versions.is_symlink() or (os.name=='nt' and versions.is_junction()):raise ValueError('版本目录包含外部链接，未删除')
    if versions.is_dir():
        for item in versions.iterdir():
            path=item.resolve()
            if not path.is_relative_to(versions.resolve()) or item.is_symlink() or (os.name=='nt' and item.is_junction()):raise ValueError('安装目录包含外部链接，未删除')
            if not item.is_dir():continue
            owned=False
            if (item/'contenthub-version.json').is_file():
                owned=read(item/'contenthub-version.json').get('format')=='contenthub/version/v1'
            if re.fullmatch(r'\.staging-[0-9a-f]{16}',item.name):owned=True
            if not owned:continue
            if data==path or data.is_relative_to(path):raise ValueError('请先将资料目录移出内部版本目录')
            shutil.rmtree(Path('\\\\?\\'+str(path)) if os.name=='nt' else path)
        try:versions.rmdir()
        except OSError:pass
    for name in ('ContentHub.exe','current.json','update-transaction.json','update.lock','uninstallerIcon.ico','Uninstall ContentHub.exe','contenthub-install.json'):
        try:(root/name).unlink(missing_ok=True)
        except PermissionError:
            if name!='Uninstall ContentHub.exe':raise
    try:root.rmdir()
    except OSError:pass
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',type=Path);parser.add_argument('--self-test',type=Path);parser.add_argument('--remove-program',type=Path);args,remaining=parser.parse_known_args()
    if args.self_test:
        key=read(FILES/'contenthub-update-public.json');assert len(base64.b64decode(key['modulus']))==384
        write(args.self_test,{'ok':True,'signature':'RSA-3072-SHA256','layout':1});return
    if args.apply:apply(args.apply);return
    if args.remove_program:remove_program(args.remove_program);return
    root=Path(sys.executable).resolve().parent;check_root(root);data=profile();recover(root,data);launch(root,current(root)['version'],arguments=remaining)
if __name__=='__main__':
    try:main()
    except Exception as exc:
        try:
            data=profile();write(data/'desktop-update-error.json',{'at':time.time(),'error':str(exc)})
            ctypes.windll.user32.MessageBoxW(0,str(exc),'内容中台',16)
        except Exception:pass
        sys.exit(1)
