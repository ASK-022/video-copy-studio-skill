"""Small offline app upgrade EXE for v1.1.3; embeds no models or account files."""
import argparse
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog,messagebox,ttk

if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'assets/studio'))
from app_update_worker import apply,recover
from offline_client import read_json
from client.update_trust import verify

RESOURCES=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))


def resources():
    envelope=read_json(RESOURCES/'update.json');payload=verify(envelope)
    return envelope,payload,RESOURCES/payload['package']['name']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply-to',type=Path);parser.add_argument('--data-dir',type=Path,
        default=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'VideoCopyStudioOffline')
    parser.add_argument('--no-launch',action='store_true');parser.add_argument('--self-test',type=Path);args=parser.parse_args()
    envelope,payload,package=resources()
    if args.apply_to:
        recover(args.apply_to,args.data_dir)
        apply(args.apply_to,args.data_dir,package,envelope,relaunch=not args.no_launch)
        if args.self_test:args.self_test.write_text(json.dumps({'ok':True,'version':payload['version']}),encoding='utf-8')
        return
    window=tk.Tk();window.title('文案工坊 · 程序升级 v'+payload['version']);window.geometry('650x300')
    frame=ttk.Frame(window,padding=22);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='升级程序，复用已有模型',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text='请先关闭离线客户端窗口。选择含 VideoCopyStudio.exe 的文件夹。\n资料和 Key 保存在原位置；启动验证失败会自动恢复旧版。').pack(anchor='w',pady=12)
    root=tk.StringVar();row=ttk.Frame(frame);row.pack(fill='x');ttk.Entry(row,textvariable=root).pack(side='left',fill='x',expand=True)
    ttk.Button(row,text='选择客户端目录',command=lambda:root.set(filedialog.askdirectory() or root.get())).pack(side='right')
    info=tk.StringVar(value='无需重新下载模型。自定义资料目录请使用命令行 --data-dir 参数。');ttk.Label(frame,textvariable=info,wraplength=600).pack(anchor='w',pady=16)
    events=queue.Queue()
    def work():
        try:
            recover(Path(root.get()),args.data_dir)
            apply(Path(root.get()),args.data_dir,package,envelope,relaunch=True)
            events.put((True,'升级完成，已打开客户端。'))
        except Exception as exc:events.put((False,str(exc)))
    def run():
        if not root.get():return
        button.config(state='disabled');info.set('正在校验、备份并升级；随后验证启动…');threading.Thread(target=work,daemon=False).start()
    button=ttk.Button(frame,text='升级并打开',command=run);button.pack(anchor='e')
    def poll():
        try:
            ok,text=events.get_nowait();button.config(state='normal');info.set(text)
            if ok:messagebox.showinfo('完成',text)
            else:messagebox.showerror('升级未完成',text)
        except queue.Empty:pass
        window.after(300,poll)
    if args.self_test:
        args.self_test.write_text(json.dumps({'ok':True,'version':payload['version'],'tk_ready':True,'package_bytes':package.stat().st_size}),encoding='utf-8');window.destroy();return
    poll();window.mainloop()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        if sys.stderr:print(str(exc),file=sys.stderr)
        sys.exit(1)
