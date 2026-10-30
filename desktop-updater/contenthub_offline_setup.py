"""Install complete desktop resources from the adjacent offline package, never download."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import stat
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
import zipfile
import zlib
from contenthub_progress import Meter,file_sha,parse_event,run_logged
from contenthub_setup_ui import ProgressPanel

FILES=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
ALLOWED={'Runtime','Engine','FFmpeg','Browsers','Models','offline-client.json','model-receipt.json'}


def description(directory):
    path=FILES/'contenthub-offline-bundle.json' if getattr(sys,'frozen',False) else Path(directory)/'contenthub-offline-bundle.json'
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('format')!='contenthub/offline-bundle/v1':raise ValueError('离线包清单格式无效')
    for key in ('installer','resources'):
        item=value[key]
        if Path(item['name']).name!=item['name'] or any(c in item['name'] for c in ('/',chr(92),':')):raise ValueError('离线包文件名无效')
        if len(item.get('sha256',''))!=64 or item.get('bytes',0)<=0:raise ValueError('离线包校验清单无效')
    return value


def native(path):
    value=str(Path(path).absolute())
    if os.name=='nt' and not value.startswith('\\\\?\\'):
        return Path('\\\\?\\UNC\\'+value[2:] if value.startswith('\\\\') else '\\\\?\\'+value)
    return Path(value)


def safe(root,name):
    parts=name.split('/')
    if not parts or parts[0] not in ALLOWED or any(part in ('','..','.') for part in parts) or chr(92) in name or ':' in name:raise ValueError('离线包包含无效资源路径')
    target=(root/Path(*parts)).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('资源目标路径越界或指向外部目录')
    return native(target)


def valid_resource(root):
    root=Path(root)
    try:
        if (root/'offline-client.json').is_file():
            info=json.loads((root/'offline-client.json').read_text(encoding='utf-8-sig'))
            receipt=json.loads((root/'model-receipt.json').read_text(encoding='utf-8-sig'))
            files=receipt.get('files',[])
            return info.get('format')=='video-copy-studio-offline/v1' and bool(files) and all((root/item['path']).resolve().is_relative_to(root.resolve()) and (root/item['path']).is_file() and (root/item['path']).stat().st_size==item['bytes'] for item in files) and all((root/name).is_file() for name in ('Runtime/python/python.exe','Engine/webmain.py','FFmpeg/bin/ffmpeg.exe','FFmpeg/bin/ffprobe.exe'))
        return False
    except (OSError,ValueError,KeyError,TypeError):return False


def verify_file(path,item,emit):
    if not path.is_file() or path.stat().st_size!=item['bytes']:raise ValueError('离线文件缺失或不完整：'+item['name'])
    meter=Meter(emit,item['bytes'],file=item['name']);value=hashlib.sha256();done=0
    with path.open('rb') as source:
        for block in iter(lambda:source.read(4*1024**2),b''):
            value.update(block);done+=len(block);meter.update(done)
    meter.update(done,True)
    if value.hexdigest()!=item['sha256']:raise ValueError('离线包 SHA256 校验失败：'+item['name'])


def extract_resources(archive,root,emit):
    root=Path(root).resolve()
    for parent in [root,*root.parents]:
        if (parent/'contenthub-install.json').is_file():raise ValueError('模型资源须位于程序安装目录之外，以便更新和卸载时保留')
    if root.exists() and any(root.iterdir()) and not any((root/name).exists() for name in ('.contenthub-offline-install.json','.contenthub-resources.json','offline-client.json')):
        raise ValueError('所选目录已有其他文件，请选择新的 ContentHubOfflineResources 文件夹')
    root.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        entries=[entry for entry in source.infolist() if not entry.is_dir()];seen=set();total=0
        for entry in entries:
            safe(root,entry.filename);fold=entry.filename.casefold()
            if fold in seen or stat.S_IFMT(entry.external_attr>>16)==stat.S_IFLNK:raise ValueError('离线包包含重复路径或符号链接')
            seen.add(fold);total+=entry.file_size
        if total>20*1024**3 or len(entries)>100000:raise ValueError('离线包大小超出限制')
        pending=sum(entry.file_size for entry in entries if not safe(root,entry.filename).is_file() or safe(root,entry.filename).stat().st_size!=entry.file_size)
        needed=pending+max((entry.file_size for entry in entries),default=0)+128*1024**2
        if shutil.disk_usage(root).free<needed:raise ValueError('资源盘剩余空间不足，请至少预留 '+str(round(needed/1024**3,1))+' GB')
        (root/'.contenthub-offline-install.json').write_text(json.dumps({'format':'contenthub/offline-resource-install/v1'}),encoding='utf-8')
        meter=Meter(emit,total);done=0;reused=0
        for entry in entries:
            target=safe(root,entry.filename);meter.context={'file':Path(entry.filename).name}
            if target.is_file() and target.stat().st_size==entry.file_size:
                crc=0
                with target.open('rb') as cached:
                    for block in iter(lambda:cached.read(4*1024**2),b''):crc=zlib.crc32(block,crc)
                if crc==entry.CRC:
                    done+=entry.file_size;reused+=1;meter.update(done);continue
            target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_name(target.name+'.contenthub-part')
            with source.open(entry) as incoming,temporary.open('wb') as output:
                for block in iter(lambda:incoming.read(1024**2),b''):
                    output.write(block);done+=len(block);meter.update(done)
            os.replace(temporary,target)
        meter.update(done,True)
    return {'files':len(entries),'bytes':total,'reused_files':reused}


def register(profile,root):
    profile=Path(profile).resolve();root=Path(root).resolve()
    if root==profile or profile.is_relative_to(root):raise ValueError('请将资源目录与个人资料目录分开保存')
    profile.mkdir(parents=True,exist_ok=True);path=profile/'director-runtime.json'
    if path.exists():
        previous=json.loads(path.read_text(encoding='utf-8-sig'))
        if Path(previous.get('root','')).resolve()==root:return
        shutil.copyfile(path,profile/('director-runtime-before-offline-'+time.strftime('%Y%m%d-%H%M%S')+'.json'))
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps({'format':'contenthub/director-runtime/v1','root':str(root)},ensure_ascii=False),encoding='utf-8');os.replace(temporary,path)


def install(directory,root,profile,emit,probe=True,register_profile=True):
    directory=Path(directory).resolve();root=Path(root).resolve();info=description(directory)
    installer=directory/info['installer']['name'];archive=directory/info['resources']['name']
    emit('phase',index=1,steps=4,name='校验完整程序安装器')
    emit('source',source='本机离线包（安装不联网）',file=installer.name,attempt=1,attempts=1)
    verify_file(installer,info['installer'],emit)
    emit('phase',index=2,steps=4,name='校验完整模型与运行资源')
    emit('source',source='本机离线包（安装不联网）',file=archive.name,attempt=1,attempts=1)
    verify_file(archive,info['resources'],emit)
    emit('phase',index=3,steps=4,name='解压资源，复用已完成文件')
    emit('source',source='本机硬盘 · 解压／校验速度',file=archive.name,attempt=1,attempts=1)
    extracted=extract_resources(archive,root,emit)
    if not valid_resource(root):raise ValueError('离线资源目录不完整，重试将继续复用已完成文件')
    emit('phase',index=4,steps=4,name='断网校验模型与浏览器')
    emit('activity',message='正在加载四组本机模型并验证浏览器；这是本机自检，不在下载。')
    if probe:
        if os.name=='nt' and not (Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/msvcp140.dll').is_file():
            raise ValueError('本机缺少微软运行库。请点击“微软运行库”完成安装，再重试；已解压资源保留。')
        result=root/'offline-models-verified.json';result.unlink(missing_ok=True)
        env=dict(os.environ,CONTENT_HUB_PROGRESS='1',PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
        env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None)
        if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            completed=run_logged([str(root/'Runtime/python/python.exe'),str(FILES/'contenthub_offline_probe.py'),'--root',str(root),'--result',str(result)],root/'offline-setup.log',env=env,timeout=1200,emit=emit)
        finally:
            if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(str(FILES))
        check=json.loads(result.read_text(encoding='utf-8')) if result.exists() else {}
        if completed.returncode or not check.get('ok') or check.get('external_attempts')!=0:raise ValueError('本机离线自检未完成，请查看资源目录 offline-setup.log。已完成的资源保留，可重试。')
    if register_profile:register(profile,root)
    emit('activity',message='完整离线资源已就绪，即将进入程序安装向导。')
    return {'ok':True,'version':info['version'],'root':str(root),'installer':str(installer),'offline':True,**extracted}


def main(installer=None,package_note=None):
    operation=installer or install
    parser=argparse.ArgumentParser();parser.add_argument('--package-dir',type=Path);parser.add_argument('--resource-dir',type=Path)
    parser.add_argument('--profile',type=Path,default=Path(os.environ.get('ASKFILM_USER_DATA',str(Path(os.environ.get('APPDATA',Path.home()))/'内容中台'))))
    parser.add_argument('--headless',action='store_true');parser.add_argument('--no-register',action='store_true');parser.add_argument('--result',type=Path);parser.add_argument('--self-test',type=Path);args=parser.parse_args()
    directory=args.package_dir or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path.cwd())
    root=args.resource_dir or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'ContentHubOfflineResources'
    if args.headless:
        console=Path(args.result).with_suffix('.log') if args.result else Path(root).parent/'contenthub-offline-console.log'
        console.parent.mkdir(parents=True,exist_ok=True);sys.stdout=console.open('a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout
        def emit(kind,**fields):print(json.dumps({'kind':kind,**fields},ensure_ascii=False),flush=True)
        try:result=operation(directory,root,args.profile,emit,register_profile=not args.no_register)
        except Exception as error:
            import traceback
            traceback.print_exc();result={'ok':False,'error':str(error)}
        if args.result:args.result.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if result['ok'] else 1
    info=description(directory);window=tk.Tk();window.title('内容中台 · 完整离线安装')
    window.geometry('820x680');window.minsize(760,620)
    frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='完整离线安装',font=('Microsoft YaHei UI',21,'bold')).pack(anchor='w')
    ttk.Label(frame,text=package_note or '编导台＋剪辑台，模型、Python、浏览器和 FFmpeg 已全部随包提供。安装和本地转写不需要联网。',wraplength=760).pack(anchor='w',pady=(8,10))
    ttk.Label(frame,text='资源保存位置（后续更新继续复用；下一步可另选程序安装位置）：').pack(anchor='w')
    path=tk.StringVar(value=str(root));row=ttk.Frame(frame);row.pack(fill='x',pady=(5,0))
    entry=ttk.Entry(row,textvariable=path);entry.pack(side='left',fill='x',expand=True)
    browse=ttk.Button(row,text='选择位置',command=lambda:path.set(filedialog.askdirectory() or path.get()));browse.pack(side='right',padx=(8,0))
    panel=ProgressPanel(frame,offline=True);actions=ttk.Frame(frame);actions.pack(side='bottom',fill='x',pady=(6,0))
    details=tk.Text(frame,height=5,wrap='word',font=('Microsoft YaHei UI',9));details.pack(fill='both',expand=True,pady=(5,0))
    events=queue.Queue();busy=False
    def work():
        try:events.put(('done',operation(directory,path.get(),args.profile,lambda kind,**fields:events.put(('event',{'kind':kind,'at':time.time(),**fields})))))
        except Exception as error:events.put(('error',str(error)))
    def begin():
        nonlocal busy
        if busy:return
        busy=True;panel.reset();panel.set_busy(True);button.configure(state='disabled');entry.configure(state='disabled');browse.configure(state='disabled')
        details.delete('1.0','end');threading.Thread(target=work,daemon=False).start()
    button=ttk.Button(actions,text='校验并安装完整离线版',command=begin);button.pack(side='right')
    runtime=directory/'VC_redist.x64.exe'
    if runtime.is_file():ttk.Button(actions,text='微软运行库',command=lambda:os.startfile(runtime)).pack(side='left')
    def poll():
        nonlocal busy
        while not events.empty():
            kind,value=events.get()
            if kind=='event':
                panel.apply(value)
                if value['kind']!='progress':
                    details.insert('end',(value.get('message') or value.get('name') or value.get('source') or value['kind'])+'\n');details.see('end')
                continue
            busy=False;panel.set_busy(False);button.configure(state='normal');entry.configure(state='normal');browse.configure(state='normal')
            if kind=='done':
                if args.result:args.result.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
                button.configure(text='打开程序安装向导',command=lambda p=value['installer']:subprocess.Popen([p],cwd=directory))
                subprocess.Popen([value['installer']],cwd=directory)
            else:
                panel.apply({'kind':'activity','message':value});details.insert('end',value+'\n');messagebox.showerror('安装尚未完成',value);button.configure(text='重试并继续安装')
        panel.refresh();window.after(200,poll)
    def close():
        if busy:messagebox.showinfo('正在安装','请等待当前本机校验或解压结束，已完成文件会保留。');return
        window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    if args.self_test:
        panel.set_busy(True);panel.apply({'kind':'phase','index':3,'steps':4,'name':'解压完整离线资源'})
        panel.apply({'kind':'source','source':'本机离线包（无需联网）','attempt':1,'attempts':1,'file':'model.pt'})
        panel.apply({'kind':'progress','received':512*1024**2,'total':2*1024**3,'speed':32*1024**2,'eta':48})
        window.update();window.update_idletasks()
        visible=actions.winfo_y()+actions.winfo_height()<=frame.winfo_height() and details.winfo_height()>=40
        args.self_test.write_text(json.dumps({'ok':visible,'controls_visible':visible,'display':panel.refresh(),'version':info['version']},ensure_ascii=False,indent=2),encoding='utf-8')
        window.destroy();return 0 if visible else 1
    poll();window.mainloop();return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:
        if sys.stderr:print(str(error),file=sys.stderr)
        if '--headless' not in sys.argv:messagebox.showerror('内容中台离线安装',str(error))
        sys.exit(1)
