"""Prepare private transcription resources; no Agent folders, projects or keys are copied."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog,ttk,messagebox
import zipfile
from contenthub_progress import PREFIX,Meter,file_sha,parse_event
from contenthub_setup_ui import ProgressPanel

FILES=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
PYTHON_SHA='0eb85c2dfccccf1b17352de4c397f69194035b7d37149eacc16f1147d93de3b8'


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def payload():
    info=json.loads((FILES/'resource-payload.json').read_text(encoding='utf-8'))
    archive=FILES/'payload.zip'
    if not archive.is_file():raise ValueError('安装器缺少内置资源文件，请重新获取最新版安装器。')
    if digest(archive)!=info['sha256']:raise ValueError('内置准备程序校验失败，请重新获取安装器。')
    return archive,info


def extract(archive,target,prefix=''):
    target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            path=(target/entry.filename).resolve()
            if not path.is_relative_to(target.resolve()) or chr(92) in entry.filename or ':' in entry.filename or (prefix and not entry.filename.startswith(prefix)):
                raise ValueError('内置资源路径无效。')
        source.extractall(target)

def validate_resource_location(directory,excluded=None):
    roots=[Path(excluded)] if excluded else []
    if os.environ.get('CONTENT_HUB_INSTALL_ROOT'):roots.append(Path(os.environ['CONTENT_HUB_INSTALL_ROOT']))
    if getattr(sys,'frozen',False):
        roots.extend(parent for parent in Path(sys.executable).parents if (parent/'contenthub-install.json').is_file())
    if any(Path(directory).resolve().is_relative_to(root.resolve()) for root in roots):
        raise ValueError('请选择整个程序安装目录之外的位置存放模型，以便更新或重新安装时继续复用。')


def prepare(directory,emit,program_root=None):
    actual=Path(directory).resolve();actual.mkdir(parents=True,exist_ok=True);alias=None
    if os.name=='nt':
        mask=ctypes.windll.kernel32.GetLogicalDrives()
        for letter in 'RSTUVWXYZHIJKLMNOPQ':
            if not mask&(1<<(ord(letter)-65)):
                candidate=letter+':'
                attempt=subprocess.run(['subst.exe',candidate,str(actual)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=NO_WINDOW)
                if attempt.returncode==0:alias=candidate;break
        if alias is None:raise ValueError('没有可用盘符建立资源安装短路径，请释放一个盘符后重试。')
    try:return prepare_at(Path(alias+'/') if alias else actual,actual,emit,alias,program_root)
    finally:
        if alias:subprocess.run(['subst.exe',alias,'/D'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=NO_WINDOW)

def bundled_ffmpeg(root,emit,program_root=None):
    candidates=[]
    if program_root:candidates.extend([Path(program_root)/'resources',Path(program_root)])
    if getattr(sys,'frozen',False):candidates.append(Path(sys.executable).parent.parent)
    installed=os.environ.get('CONTENT_HUB_INSTALL_ROOT')
    if installed:
        try:
            version=json.loads((Path(installed)/'current.json').read_text(encoding='utf-8'))['version']
            if __import__('re').fullmatch(r'\d+\.\d+\.\d+',version):candidates.append(Path(installed)/'versions'/version/'resources')
        except (OSError,ValueError,KeyError):pass
    def record(kind,**fields):emit(PREFIX+json.dumps({'kind':kind,'at':time.time(),**fields},ensure_ascii=False))
    for resources in candidates:
        try:
            version_root=resources.parent;meta=json.loads((version_root/'contenthub-version.json').read_text(encoding='utf-8'))
            if meta.get('format')!='contenthub/version/v1':continue
            for folder in (resources/'runtime/ffmpeg',resources/'runtime/ffmpeg/bin'):
                paths=[folder/name for name in ('ffmpeg.exe','ffprobe.exe')]
                if not all(path.is_file() for path in paths):continue
                entries=[meta['files'].get(path.relative_to(version_root).as_posix(),{}) for path in paths]
                if not all(path.stat().st_size==entry.get('bytes') and file_sha(path)==entry.get('sha256') for path,entry in zip(paths,entries)):continue
                target=root/'ffmpeg';target.mkdir(parents=True,exist_ok=True);total=sum(p.stat().st_size for p in paths)
                record('source',source='程序安装包内置 FFmpeg（不下载）',file='ffmpeg.exe / ffprobe.exe',attempt=1,attempts=1)
                meter=Meter(record,total);done=0
                for path,entry in zip(paths,entries):
                    destination=target/path.name;meter.context={'file':path.name}
                    if destination.is_file() and file_sha(destination)==entry['sha256']:done+=path.stat().st_size;meter.update(done);continue
                    temporary=destination.with_suffix('.contenthub-part')
                    with path.open('rb') as incoming,temporary.open('wb') as output:
                        for block in iter(lambda:incoming.read(1024**2),b''):output.write(block);done+=len(block);meter.update(done)
                    if file_sha(temporary)!=entry['sha256']:raise ValueError('内置 FFmpeg 复制校验失败')
                    os.replace(temporary,destination)
                meter.update(done,True);record('cached',source='程序安装包内置 FFmpeg（不下载）',file='ffmpeg.exe / ffprobe.exe',total=total)
                return target/'ffmpeg.exe'
        except (OSError,ValueError,KeyError):continue
    return None


def prepare_at(root,actual,emit,alias,program_root=None):
    archive,info=payload()
    if os.name=='nt' and not (Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/msvcp140.dll').is_file():
        raise ValueError('请先点击“微软运行库”，按微软窗口完成安装后，再准备本地转写资源。')
    marker=root/'.contenthub-resources.json'
    if root.exists() and any(root.iterdir()) and not marker.exists():
        raise ValueError('该目录已有其他文件。请选择一个新的 ContentHubResources 文件夹；已有文案工坊资源请在客户端选择“选择已有资源”。')
    root.mkdir(parents=True,exist_ok=True)
    marker.write_text(json.dumps({'format':'contenthub/resources/v1'}),encoding='utf-8')
    source=root/'.installer'/info['version'];source.mkdir(parents=True,exist_ok=True)
    emit(PREFIX+json.dumps({'kind':'phase','index':1,'steps':6,'name':'校验内置安装工具'},ensure_ascii=False))
    emit('正在校验并准备安装工具…');extract(archive,source,'video-copy-studio/')
    skill=source/'video-copy-studio';python_root=root/'python-3.12.10'
    bootstrap=skill/'scripts/bootstrap.py';text=bootstrap.read_text(encoding='utf-8')
    text=text.replace('root=args.runtime_home.resolve();','root=args.runtime_home.absolute();').replace("asr=(args.asr_root or root/'runtime/video-transcriber').resolve()","asr=(args.asr_root or root/'runtime/video-transcriber').absolute()")
    bootstrap.write_text(text,encoding='utf-8')
    # Keep the interpreter's short drive alias through the browser install too.
    browser_setup=skill/'scripts/browser_setup.py'
    browser_setup.write_text(browser_setup.read_text(encoding='utf-8').replace('.resolve()','.absolute()'),encoding='utf-8')
    python=python_root/'tools/python.exe';nuget=skill/'assets/bootstrap/python-3.12.10.nupkg'
    if digest(nuget)!=PYTHON_SHA:raise ValueError('基础 Python 校验失败。')
    if not python.is_file():emit('正在准备独立 Python…');extract(nuget,python_root)
    emit('正在准备转写依赖和模型。首次需要联网；已有下载会继续复用。')
    ffmpeg=bundled_ffmpeg(root,emit,program_root)
    command=[str(python),str(bootstrap),'--runtime-home',str(root),'--install','--download-ffmpeg']
    if ffmpeg:command.extend(['--ffmpeg',str(ffmpeg)])
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',CONTENT_HUB_PROGRESS='1',PYTHONNOUSERSITE='1',PYTHONPYCACHEPREFIX=str(root/'python-cache'))
    env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None)
    if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        with (root/'resource-setup.log').open('a',encoding='utf-8') as log:
            child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=NO_WINDOW)
            failure=''
            for line in child.stdout:
                log.write(line);log.flush();emit(line.strip())
                if line.lstrip().startswith('{'):
                    try:
                        status=json.loads(line)
                        if status.get('ok') is False:failure=str(status.get('error',''))
                    except (ValueError,TypeError):pass
            if child.wait():raise ValueError((failure or '资源下载或模型自检未完成')+'；已完成资源已保留，可在同一目录重试。详情：resource-setup.log')
    finally:
        if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(str(FILES))
    config=json.loads((root/'runtime.json').read_text(encoding='utf-8'))
    receipt=json.loads((root/'models-ready.json').read_text(encoding='utf-8'))
    if not all(receipt.get('loaded',{}).get(key) for key in ('sensevoice','punctuation','alignment','ocr')):raise ValueError('模型自检未通过。')
    if alias:
        def canonical_paths(value):
            if isinstance(value,str):return value.replace(alias+'\\',str(actual)+'\\').replace(alias+'/',actual.as_posix()+'/')
            if isinstance(value,list):return [canonical_paths(v) for v in value]
            if isinstance(value,dict):return {k:canonical_paths(v) for k,v in value.items()}
            return value
        config=canonical_paths(config);receipt=canonical_paths(receipt)
        (actual/'runtime.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        (actual/'models-ready.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        cfg=actual/'runtime/video-transcriber/.venv/pyvenv.cfg'
        if cfg.is_file():cfg.write_text(canonical_paths(cfg.read_text(encoding='utf-8')),encoding='utf-8')
    return {'ok':True,'root':str(actual),'python':config['python']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,default=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'ContentHubResources')
    parser.add_argument('--auto-start',action='store_true');parser.add_argument('--self-test',type=Path)
    parser.add_argument('--headless',action='store_true',help='Run the same preparation pipeline with a machine-readable result')
    parser.add_argument('--result',type=Path);parser.add_argument('--exclude-root',type=Path);args=parser.parse_args()
    if args.headless:
        args.directory.parent.mkdir(parents=True,exist_ok=True)
        # A windowed PyInstaller executable has no usable console handles.
        sys.stdout=(args.directory.parent/'resource-console.log').open('a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout
        if args.result:args.result.unlink(missing_ok=True)
        try:
            validate_resource_location(args.directory,args.exclude_root)
            result=prepare(args.directory,lambda text:print(text,flush=True),args.exclude_root)
        except Exception as exc:
            import traceback
            traceback.print_exc();result={'ok':False,'error':str(exc)}
        if args.result:
            args.result.parent.mkdir(parents=True,exist_ok=True);args.result.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        sys.exit(0 if result['ok'] else 1)
    try:archive,info=payload()
    except Exception as exc:
        if args.self_test:
            args.self_test.parent.mkdir(parents=True,exist_ok=True)
            args.self_test.write_text(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),encoding='utf-8')
        else:messagebox.showerror('资源准备未能启动',str(exc))
        sys.exit(1)
    window=tk.Tk();window.title('内容中台 · 编导资源准备');window.geometry('820x680');window.minsize(760,620)
    frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='准备本地转写资源',font=('Microsoft YaHei UI',20,'bold')).pack(anchor='w')
    ttk.Label(frame,text='首次需要下载数 GB。可选择 D/E 盘；不需要填写 Key。已有资源可关闭此窗口，回客户端选择复用。',wraplength=660).pack(anchor='w',pady=12)
    path=tk.StringVar(value=str(args.directory));row=ttk.Frame(frame);row.pack(fill='x')
    entry=ttk.Entry(row,textvariable=path);entry.pack(side='left',fill='x',expand=True)
    browse=ttk.Button(row,text='选择位置',command=lambda:path.set(filedialog.askdirectory() or path.get()));browse.pack(side='right')
    panel=ProgressPanel(frame)
    actions=ttk.Frame(frame);actions.pack(side='bottom',fill='x',pady=(4,0))
    details=tk.Text(frame,height=8,wrap='word',font=('Microsoft YaHei UI',9));details.pack(fill='both',expand=True,pady=12)
    events=queue.Queue();busy=False;complete=False
    def work():
        try:
            validate_resource_location(path.get(),args.exclude_root)
            events.put(('done',prepare(path.get(),lambda text:events.put(('log',text)),args.exclude_root)))
        except Exception as exc:events.put(('error',str(exc)))
    def begin():
        nonlocal busy
        if busy:return
        busy=True;panel.reset();panel.set_busy(True);details.delete('1.0','end');button.configure(state='disabled');entry.configure(state='disabled');browse.configure(state='disabled')
        threading.Thread(target=work,daemon=False).start()
    button=ttk.Button(actions,text='开始准备资源',command=begin);button.pack(side='right')
    redistributable=Path(sys.executable).parent/'VC_redist.x64.exe'
    if redistributable.is_file():ttk.Button(actions,text='微软运行库',command=lambda:os.startfile(redistributable)).pack(side='left')
    def close():
        if busy:messagebox.showinfo('正在准备','请等待当前准备结束。正在下载的模型会保留，失败后可重试。');return
        window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    def poll():
        nonlocal busy,complete
        while not events.empty():
            kind,value=events.get()
            if kind=='log':
                event=parse_event(value)
                if event:
                    panel.apply(event)
                    if event['kind']=='progress':continue
                    value=event.get('message') or event.get('name') or event.get('source') or event['kind']
                    if event.get('reason'):value+='：'+event['reason']
                details.insert('end',value[:2000]+'\n');details.see('end')
                if int(details.index('end-1c').split('.')[0])>700:details.delete('1.0','200.0')
                continue
            busy=False;panel.set_busy(False);button.configure(state='normal');entry.configure(state='normal');browse.configure(state='normal')
            if kind=='done':
                if args.result:
                    args.result.parent.mkdir(parents=True,exist_ok=True);args.result.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
                complete=True;panel.apply({'kind':'activity','message':'资源自检通过，正在返回客户端…'});window.after(1200,window.destroy)
            else:panel.apply({'kind':'activity','message':value});button.configure(text='重试并继续准备');messagebox.showerror('尚未完成',value)
        panel.refresh()
        window.after(150,poll)
    if args.self_test:
        panel.set_busy(True);panel.apply({'kind':'phase','index':2,'steps':6,'name':'准备 FFmpeg'})
        panel.apply({'kind':'source','source':'Gyan 主源','file':'ffmpeg.zip','attempt':1,'attempts':2})
        panel.apply({'kind':'source','source':'GitHub 备用源','file':'ffmpeg.zip','attempt':2,'attempts':2,'previous':'Gyan 主源','reason':'HTTPS 连接中断（TLS EOF）'})
        panel.apply({'kind':'progress','received':50*1024**2,'total':100*1024**2,'speed':2*1024**2,'eta':25})
        # Tk must calculate the mapped layout before a hidden-window geometry check.
        window.deiconify();window.update();window.update_idletasks()
        layout={'window_height':window.winfo_height(),'frame_height':frame.winfo_height(),'actions_bottom':actions.winfo_y()+actions.winfo_height(),'log_height':details.winfo_height()}
        visible=layout['actions_bottom']<=layout['frame_height'] and layout['log_height']>=50
        window.withdraw()
        args.self_test.parent.mkdir(parents=True,exist_ok=True)
        args.self_test.write_text(json.dumps({'ok':visible,'tk_ready':True,'controls_visible':visible,'layout':layout,'version':info['version'],'payload_bytes':archive.stat().st_size,'display':panel.refresh()},ensure_ascii=False),encoding='utf-8');window.destroy()
        if not visible:sys.exit(1)
        return
    poll()
    if args.auto_start:window.after(200,begin)
    window.mainloop()
    if not complete:sys.exit(1)


if __name__=='__main__':main()
