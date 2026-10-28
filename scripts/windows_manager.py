"""Windows GUI installer/launcher. Frozen with Python and Tk; models stay external."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
import zipfile

SOURCE=Path(__file__).resolve().parents[1]
if not getattr(sys,'frozen',False):sys.path.insert(0,str(SOURCE/'assets/studio'))
from client.updates import check_update,local_version,version_tuple

RESOURCES=Path(getattr(sys,'_MEIPASS',SOURCE))
VERSION=local_version(RESOURCES)
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)


def runtime_home():
    return Path(os.environ.get('VIDEO_COPY_STUDIO_HOME',str(Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'VideoCopyStudio'))).resolve()


def installed_version(root):
    receipt=Path(root)/'installation.json'
    try:
        value=json.loads(receipt.read_text(encoding='utf-8-sig'))['version']
        version_tuple(value);return value
    except (OSError,ValueError,KeyError):pass
    # Older command-line installs have no installation receipt.
    roots=[Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills',
           Path(os.environ.get('CLAUDE_CONFIG_DIR',str(Path.home()/'.claude')))/'skills',Path.home()/'.openclaw/skills']
    if (Path(root)/'runtime.json').is_file():
        for candidate in roots:
            try:return local_version(candidate/'video-copy-studio')
            except (OSError,ValueError):pass
    return None


def verify_payload():
    package=RESOURCES/'payload.zip'
    expected=(RESOURCES/'payload.zip.sha256').read_text(encoding='ascii').split()[0]
    if hashlib.sha256(package.read_bytes()).hexdigest()!=expected:raise ValueError('内置安装包校验失败，请重新下载 EXE。')
    with zipfile.ZipFile(package) as source:
        if source.read('video-copy-studio/VERSION').decode().strip()!=VERSION:raise ValueError('内置安装包版本不匹配。')
    if not (RESOURCES/'install.ps1').is_file():raise ValueError('内置安装脚本缺失。')
    return package


def powershell():
    return str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')


def run_installer(root,tag,emit):
    version_tuple(tag.removeprefix('v'))
    package=verify_payload() if tag=='v'+VERSION else None
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='video-copy-studio-exe-') as folder:
        script=Path(folder)/'install.ps1'
        # PowerShell 5.1 needs a BOM when reading a script containing Chinese.
        script.write_text((RESOURCES/'install.ps1').read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
        command=[powershell(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),
                 '-RuntimeHome',str(root),'-ReleaseTag',tag]
        if package:command+=['-PackagePath',str(package)]
        with (root/'installer.log').open('a',encoding='utf-8') as log:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,encoding='utf-8',errors='replace',creationflags=NO_WINDOW)
            for line in process.stdout:
                log.write(line);log.flush();emit(line.rstrip())
            code=process.wait()
        if code:raise ValueError('安装未完成。请查看安装日志，修复后重新点击“安装/更新”。')
    receipt=json.loads((root/'installation.json').read_text(encoding='utf-8-sig'))
    if receipt.get('version')!=tag[1:]:raise ValueError('安装完成凭据不匹配，请检查 installer.log。')


def save_manager(root):
    if not getattr(sys,'frozen',False):return
    target=Path(root)/('VideoCopyStudio-Manager-v'+VERSION+'.exe')
    if Path(sys.executable).resolve()!=target.resolve():shutil.copy2(sys.executable,target)
    # Side-by-side manager versions avoid overwriting a running EXE.
    quote=lambda path:str(path).replace("'","''")
    script="$s=New-Object -ComObject WScript.Shell; $p=Join-Path ([Environment]::GetFolderPath('Desktop')) '文案工坊安装管理器.lnk'; $l=$s.CreateShortcut($p); $l.TargetPath='"+quote(target)+"'; $l.Arguments='--runtime-home \""+quote(root)+"\"'; $l.Save()"
    encoded=base64.b64encode(script.encode('utf-16le')).decode('ascii')
    subprocess.run([powershell(),'-NoProfile','-EncodedCommand',encoded],creationflags=NO_WINDOW,check=True)


class Manager:
    def __init__(self,root,home):
        self.root=root;self.events=queue.Queue();self.busy=False;self.latest=None
        root.title('文案工坊 · 安装与更新');root.geometry('760x660');root.minsize(680,590)
        root.configure(bg='#f4f6fa')
        style=ttk.Style();style.theme_use('clam')
        style.configure('TFrame',background='#f4f6fa');style.configure('TLabel',background='#f4f6fa',font=('Microsoft YaHei UI',10))
        style.configure('TButton',font=('Microsoft YaHei UI',10),padding=(13,9))
        style.configure('Title.TLabel',font=('Microsoft YaHei UI',23,'bold'),foreground='#172338')
        style.configure('Muted.TLabel',foreground='#596579');style.configure('Primary.TButton',background='#1763d4',foreground='white')
        frame=ttk.Frame(root,padding=26);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='文案工坊',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='安装一次，以后从桌面打开。更新前可先查看正式版说明。',style='Muted.TLabel').pack(anchor='w',pady=(6,20))
        self.version=tk.StringVar();ttk.Label(frame,textvariable=self.version).pack(anchor='w')
        location=ttk.Frame(frame);location.pack(fill='x',pady=(12,8))
        ttk.Label(location,text='运行时目录').pack(side='left',padx=(0,10))
        self.path=tk.StringVar(value=str(home));self.entry=ttk.Entry(location,textvariable=self.path);self.entry.pack(side='left',fill='x',expand=True)
        self.browse=ttk.Button(location,text='选择',command=self.choose);self.browse.pack(side='left',padx=(8,0))
        self.path.trace_add('write',lambda *_:self.refresh_version())
        self.status=tk.StringVar(value='可直接安装；首次安装需要联网下载浏览器、依赖和模型。')
        ttk.Label(frame,textvariable=self.status,wraplength=690,style='Muted.TLabel').pack(anchor='w',pady=(4,12))
        bar=ttk.Frame(frame);bar.pack(fill='x')
        self.install=ttk.Button(bar,text='安装 / 更新',style='Primary.TButton',command=self.begin_install);self.install.pack(side='left')
        self.open=ttk.Button(bar,text='打开文案工坊',command=self.open_studio);self.open.pack(side='left',padx=8)
        self.check=ttk.Button(bar,text='检查更新',command=self.check_updates);self.check.pack(side='left')
        ttk.Button(bar,text='查看日志',command=self.logs).pack(side='right')
        self.progress=ttk.Progressbar(frame,mode='indeterminate');self.progress.pack(fill='x',pady=(17,12))
        self.details=tk.Text(frame,height=15,wrap='word',font=('Microsoft YaHei UI',10),bg='white',fg='#263247',relief='flat',padx=14,pady=12,state='disabled')
        self.details.pack(fill='both',expand=True)
        ttk.Label(frame,text='Windows 10/11 x64  ·  管理器 v'+VERSION+'  ·  模型不包含在 EXE 中',style='Muted.TLabel').pack(anchor='w',pady=(12,0))
        self.append('此窗口用于安装、启动和更新。视频创作与脚本改写在本机网页中使用。\n升级会保留资料与 Key。请先保存工作、等待任务完成；旧服务不会被强制结束。')
        self.refresh_version();root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(120,self.poll);root.after(500,self.check_updates)

    def refresh_version(self):
        current=installed_version(Path(self.path.get()).expanduser())
        self.version.set('本机版本：'+('v'+current if current else '尚未完成安装')+'    ·    内置版本：v'+VERSION)

    def append(self,text):
        self.details.configure(state='normal');self.details.insert('end',text+'\n');self.details.see('end');self.details.configure(state='disabled')

    def choose(self):
        path=filedialog.askdirectory(title='选择运行时安装目录',initialdir=self.path.get())
        if path:self.path.set(path)

    def set_busy(self,busy):
        self.busy=busy
        for widget in (self.install,self.open,self.check,self.entry,self.browse):widget.configure(state='disabled' if busy else 'normal')
        if busy:self.progress.start(12)
        else:self.progress.stop()

    def start(self,work):
        self.set_busy(True)
        def worker():
            try:work()
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def check_updates(self):
        if self.busy:return
        current=installed_version(self.path.get()) or VERSION
        self.status.set('正在检查 GitHub 正式版…')
        self.start(lambda:self.events.put(('release',check_update(current))))

    def begin_install(self):
        if not self.path.get().strip():messagebox.showerror('安装目录','请选择运行时目录。');return
        root=Path(self.path.get()).expanduser().resolve()
        current=installed_version(root)
        tag=self.latest['tag'] if self.latest and version_tuple(self.latest['latest'])>=version_tuple(VERSION) else 'v'+VERSION
        if current and version_tuple(current)>version_tuple(tag[1:]):
            messagebox.showinfo('保留新版','本机版本更新。请先检查更新或下载最新版管理器，避免降级。');return
        if not messagebox.askokcancel('安装 / 更新',f'即将安装 {tag}。\n\n首次安装需要联网并预留数 GB 空间。已有资料与 Key 会保留。\n请先保存工作并等待正在处理的任务完成。\n\n继续安装？'):return
        self.status.set('正在安装 '+tag+'，请保持网络连接并等待自检完成…')
        def work():
            run_installer(root,tag,lambda line:self.events.put(('log',line)))
            warning=''
            try:save_manager(root)
            except Exception:warning='安装完成，但管理器快捷方式未创建；可继续使用下载的 EXE。'
            self.events.put(('installed',warning))
        self.start(work)

    def open_studio(self):
        root=Path(self.path.get()).expanduser().resolve()
        def work():
            try:config=json.loads((root/'runtime.json').read_text(encoding='utf-8-sig'))
            except (OSError,ValueError):raise ValueError('请先完成安装，再打开文案工坊。')
            with (root/'launcher.log').open('ab') as log:
                subprocess.Popen([config.get('pythonw',config['python']),config['launcher']],cwd=root,stdout=log,stderr=log,creationflags=NO_WINDOW)
            self.events.put(('opened','已请求启动；页面未打开时请查看 launcher.log。'))
        self.start(work)

    def logs(self):
        root=Path(self.path.get()).expanduser().resolve()
        if not root.exists():messagebox.showinfo('日志','尚未创建运行时目录。');return
        os.startfile(root)

    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='log':self.append(value);continue
            self.set_busy(False);self.refresh_version()
            if kind=='release':
                self.latest=value
                message=('发现新版本 v'+value['latest'] if value['update_available'] else '当前已是最新版本（正式版 v'+value['latest']+'）')
                self.status.set(message);self.append('\n'+message+'\n'+value['release_url']+'\n'+value['notes'])
            elif kind=='installed':
                self.status.set('安装与自检完成。');self.append(value or '安装与自检完成。已有旧服务请正常关闭后重新打开；不便关闭时可保存工作后重启电脑。')
            elif kind=='opened':self.status.set(value)
            elif kind=='error':self.status.set(value);self.append('提示：'+value)
        self.root.after(120,self.poll)

    def close(self):
        if self.busy:messagebox.showinfo('正在处理','请等待当前检查或安装结束后再关闭。');return
        self.root.destroy()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime-home',type=Path,default=runtime_home())
    parser.add_argument('--self-test',type=Path);args=parser.parse_args()
    if args.self_test:
        package=verify_payload();window=tk.Tk();window.withdraw();manager=Manager(window,args.runtime_home);window.update_idletasks()
        controls=[manager.install.cget('text'),manager.open.cget('text'),manager.check.cget('text')]
        window.destroy()
        args.self_test.write_text(json.dumps({'ok':True,'version':VERSION,'payload_sha256':hashlib.sha256(package.read_bytes()).hexdigest(),'tk_ready':True,'controls':controls}),encoding='utf-8');return
    root=tk.Tk();Manager(root,args.runtime_home);root.mainloop()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        if sys.stderr:print(str(exc),file=sys.stderr)
        if '--self-test' not in sys.argv:messagebox.showerror('文案工坊',str(exc))
        sys.exit(1)
