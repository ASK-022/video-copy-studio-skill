"""Verify cloud ZIP pieces, reconstruct the standard installer, and open its wizard."""
from pathlib import Path
import argparse,ctypes,hashlib,json,os,queue,secrets,subprocess,sys,threading,tkinter as tk,zipfile
from tkinter import ttk,filedialog,messagebox
FILES=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
def digest(path):
 value=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
 return value.hexdigest()
def assemble(folder,manifest,emit=lambda *_:None):
 target=folder/manifest['installer']
 if target.is_file() and target.stat().st_size==manifest['bytes'] and digest(target)==manifest['sha256']:return target
 pending=folder/(manifest['installer']+'.'+secrets.token_hex(6)+'.partial');total=hashlib.sha256();received=0
 try:
  with pending.open('xb') as output:
   for index,part in enumerate(manifest['parts'],1):
    path=folder/part['name']
    if not path.is_file():raise ValueError(f'缺少第 {index}/{len(manifest["parts"])} 个分包：{part["name"]}。请把全部分包与本安装助手放在同一文件夹。')
    current=hashlib.sha256();size=0
    with zipfile.ZipFile(path) as archive:
     entries=archive.infolist()
     if len(entries)!=1 or entries[0].filename!=part['entry'] or entries[0].file_size!=part['bytes']:raise ValueError('分包格式或大小不符：'+part['name'])
     with archive.open(entries[0]) as source:
      while block:=source.read(1024*1024):
       size+=len(block);received+=len(block)
       if size>part['bytes']:raise ValueError('分包内容超出限制')
       current.update(block);total.update(block);output.write(block);emit(round(received/manifest['bytes']*100))
    if size!=part['bytes'] or current.hexdigest()!=part['sha256']:raise ValueError('分包校验未通过，请重新下载：'+part['name'])
  if received!=manifest['bytes'] or total.hexdigest()!=manifest['sha256']:raise ValueError('安装器总校验失败，未运行。')
  if target.exists():os.replace(target,target.with_name(target.name+'.invalid-'+secrets.token_hex(4)))
  os.replace(pending,target);return target
 finally:pending.unlink(missing_ok=True)
def open_setup(path):
 if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(None)
 subprocess.Popen([str(path)],cwd=path.parent,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--verify-only',type=Path);parser.add_argument('--result',type=Path);parser.add_argument('--self-test',type=Path);args=parser.parse_args()
 manifest=json.loads((FILES/'setup-parts.json').read_text(encoding='utf-8'))
 if args.verify_only:
  try:path=assemble(args.verify_only,manifest);result={'ok':True,'sha256':digest(path),'bytes':path.stat().st_size,'parts':len(manifest['parts'])}
  except Exception as exc:result={'ok':False,'error':str(exc)}
  if args.result:args.result.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
  sys.exit(0 if result['ok'] else 1)
 window=tk.Tk();window.title('内容中台 · 安装助手');window.geometry('650x430');window.minsize(650,430)
 frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
 ttk.Label(frame,text='校验分包，打开安装向导',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w')
 ttk.Label(frame,text=f'请先下载全部 {len(manifest["parts"])} 个 ZIP 分包到同一文件夹，无需手动解压。标准安装向导中可以选择程序安装位置。',wraplength=590).pack(anchor='w',pady=14)
 directory=tk.StringVar(value=str(Path(sys.executable).parent));row=ttk.Frame(frame);row.pack(fill='x')
 entry=ttk.Entry(row,textvariable=directory);entry.pack(side='left',fill='x',expand=True)
 browse=ttk.Button(row,text='选择分包目录',command=lambda:directory.set(filedialog.askdirectory() or directory.get()));browse.pack(side='right')
 progress=ttk.Progressbar(frame,maximum=100);progress.pack(fill='x',pady=16)
 note=tk.StringVar(value='只准备安装程序，不读取现有资料、Key 或模型。');ttk.Label(frame,textvariable=note,wraplength=590).pack(anchor='w')
 events=queue.Queue();busy=False
 def begin():
  nonlocal busy
  if busy:return
  busy=True;button.configure(state='disabled');browse.configure(state='disabled');entry.configure(state='disabled');note.set('正在校验与重组安装器…')
  def work():
   try:events.put(('done',assemble(Path(directory.get()),manifest,lambda value:events.put(('progress',value)))))
   except Exception as exc:events.put(('error',str(exc)))
  threading.Thread(target=work,daemon=True).start()
 button=ttk.Button(frame,text='校验并打开安装器',command=begin);button.pack(anchor='e',pady=18)
 def poll():
  nonlocal busy
  while not events.empty():
   kind,value=events.get()
   if kind=='progress':progress['value']=value;continue
   busy=False;button.configure(state='normal');browse.configure(state='normal');entry.configure(state='normal')
   if kind=='done':open_setup(value);note.set('校验通过，已打开安装向导。可在向导中选择安装位置。')
   else:note.set(value);messagebox.showerror('尚未完成',value)
  window.after(100,poll)
 window.protocol('WM_DELETE_WINDOW',lambda:messagebox.showinfo('正在校验','请等待校验完成。') if busy else window.destroy())
 if args.self_test:
  window.deiconify();window.update();window.update_idletasks();ok=button.winfo_y()+button.winfo_height()<=frame.winfo_height()
  args.self_test.write_text(json.dumps({'ok':ok,'controls_visible':ok,'parts':len(manifest['parts'])}),encoding='utf-8');window.destroy();sys.exit(0 if ok else 1)
 poll();window.mainloop()
if __name__=='__main__':main()
