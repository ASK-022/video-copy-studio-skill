"""Install the complete client from adjacent, independently verified resource ZIPs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import zipfile

SOURCE=Path(__file__).resolve().parents[1]
VERSION=(Path(getattr(sys,'_MEIPASS',SOURCE))/'VERSION').read_text(encoding='utf-8').strip()


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(4*1024*1024),b''):result.update(chunk)
    return result.hexdigest()


def manifest(directory):
    directory=Path(directory).resolve()
    value=json.loads((directory/f'offline-downloads-v{VERSION}.json').read_text(encoding='utf-8'))
    if value.get('format')!='video-copy-studio-offline-downloads/v1' or value.get('version')!=VERSION:raise ValueError('分包版本或清单不匹配。')
    if value.get('client_dir')!='VideoCopyStudio-Offline-v'+VERSION:raise ValueError('客户端目录无效。')
    parts=value.get('parts',[])
    if not parts:raise ValueError('离线资源分包清单为空。')
    for part in parts:
        if not re.fullmatch(r'VideoCopyStudio-Offline-v'+re.escape(VERSION)+r'-part[0-9]+\.zip',part.get('name','')):raise ValueError('分包文件名无效。')
        if not re.fullmatch(r'[a-f0-9]{64}',part.get('sha256','')):raise ValueError('分包校验值无效。')
    return value


def install(directory,parent,emit=lambda _:None):
    directory=Path(directory).resolve();parent=Path(parent).resolve();description=manifest(directory)
    destination=parent/description['client_dir']
    if destination.exists():raise ValueError('目标客户端目录已存在，请选择另一位置；个人资料保留在本机独立数据目录。')
    for part in description['parts']:
        source=directory/part['name'];emit('正在校验 '+part['name'])
        if not source.is_file() or source.stat().st_size!=part['bytes'] or digest(source)!=part['sha256']:
            raise ValueError('分包缺失或校验失败，请重新下载：'+part['name'])
    # Check every member before creating the output tree, including duplicates.
    names=set()
    for part in description['parts']:
        with zipfile.ZipFile(directory/part['name']) as archive:
            for entry in archive.infolist():
                name=entry.filename
                if name in names or '\\' in name or not name.startswith(description['client_dir']+'/'):
                    raise ValueError('资源包包含重复或无效路径。')
                target=(parent/name).resolve()
                if not target.is_relative_to(destination.resolve()) or stat.S_IFMT(entry.external_attr>>16)==stat.S_IFLNK:
                    raise ValueError('资源包路径越界或包含符号链接。')
                names.add(name)
    parent.mkdir(parents=True,exist_ok=True)
    for part in description['parts']:
        emit('正在解压 '+part['name'])
        extract_root=str(parent)
        if os.name=='nt' and not extract_root.startswith('\\\\?\\'):
            extract_root=('\\\\?\\UNC\\'+extract_root[2:]) if extract_root.startswith('\\\\') else ('\\\\?\\'+extract_root)
        with zipfile.ZipFile(directory/part['name']) as archive:archive.extractall(extract_root)
    if not (destination/'VideoCopyStudio.exe').is_file():raise ValueError('客户端程序缺失。')
    emit('离线客户端已准备好：'+str(destination))
    return destination


class Setup:
    def __init__(self,window,directory,installer=None,resource_note=None):
        self.window=window;self.directory=directory;self.installer=installer or install;self.events=queue.Queue();self.busy=False
        window.title('文案工坊 · 完整离线客户端');window.geometry('720x410');window.minsize(650,390)
        box=ttk.Frame(window,padding=26);box.pack(fill='both',expand=True)
        ttk.Label(box,text='完整离线客户端',font=('Microsoft YaHei UI',21,'bold')).pack(anchor='w')
        ttk.Label(box,text='安装及本地转写无需联网。AI 改写、链接解析和检查更新仍需联网。',wraplength=650).pack(anchor='w',pady=(9,20))
        ttk.Label(box,text=resource_note or '请将全部分包和清单放在本程序旁边，然后选择安装位置。',wraplength=650).pack(anchor='w')
        row=ttk.Frame(box);row.pack(fill='x',pady=14)
        self.parent=tk.StringVar(value=str(Path.home()/'Documents/VideoCopyStudioOffline'))
        ttk.Entry(row,textvariable=self.parent).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='选择位置',command=self.choose).pack(side='right',padx=(8,0))
        self.note=tk.StringVar(value='本版 v'+VERSION+' · 资源准备完成后，双击 VideoCopyStudio.exe 打开客户端。')
        ttk.Label(box,textvariable=self.note,wraplength=650).pack(anchor='w',pady=12)
        self.progress=ttk.Progressbar(box,mode='indeterminate');self.progress.pack(fill='x',pady=(5,20))
        self.button=ttk.Button(box,text='校验并安装离线客户端',command=self.begin);self.button.pack(anchor='w')
        window.protocol('WM_DELETE_WINDOW',self.close);window.after(150,self.poll)

    def choose(self):
        value=filedialog.askdirectory(title='选择离线客户端安装位置')
        if value:self.parent.set(value)

    def begin(self):
        if self.busy:return
        parent=self.parent.get()
        self.busy=True;self.button.configure(state='disabled');self.progress.start(12)
        def worker():
            try:self.events.put(('done',str(self.installer(self.directory,parent,lambda message:self.events.put(('note',message))))))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind,message=self.events.get();self.note.set(message)
            if kind!='note':
                self.busy=False;self.progress.stop();self.button.configure(state='normal')
                if kind=='done':
                    self.button.configure(text='打开离线客户端',command=lambda p=message:os.startfile(Path(p)/'VideoCopyStudio.exe'))
        self.window.after(150,self.poll)

    def close(self):
        if self.busy:messagebox.showinfo('正在安装','请等待当前校验与解压完成后再关闭。');return
        self.window.destroy()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package-dir',type=Path);parser.add_argument('--extract-to',type=Path);parser.add_argument('--self-test',type=Path);args=parser.parse_args()
    directory=args.package_dir or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path.cwd())
    if args.extract_to:
        path=install(directory,args.extract_to)
        if args.self_test:args.self_test.write_text(json.dumps({'ok':True,'client':str(path)}),encoding='utf-8')
        return
    if args.self_test:
        description=manifest(directory);window=tk.Tk();window.withdraw();Setup(window,directory);window.update_idletasks();window.destroy()
        args.self_test.write_text(json.dumps({'ok':True,'parts':len(description['parts']),'version':VERSION}),encoding='utf-8');return
    root=tk.Tk();Setup(root,directory);root.mainloop()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        if sys.stderr:print(str(exc),file=sys.stderr)
        if '--self-test' not in sys.argv:messagebox.showerror('离线客户端',str(exc))
        sys.exit(1)
