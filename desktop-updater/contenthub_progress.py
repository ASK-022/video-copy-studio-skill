"""Progress records shared by online resource preparation and offline installation."""
from collections import deque
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PREFIX='@@CONTENTHUB_PROGRESS '


def emit_event(kind, **fields):
    if os.environ.get('CONTENT_HUB_PROGRESS')=='1':
        print(PREFIX+json.dumps({'kind':kind,'at':time.time(),**fields},ensure_ascii=False),file=sys.stderr,flush=True)


def parse_event(line):
    if not line.startswith(PREFIX):return None
    try:
        event=json.loads(line[len(PREFIX):])
        return event if isinstance(event,dict) and isinstance(event.get('kind'),str) else None
    except (ValueError,TypeError):return None


def byte_text(value):
    if value is None:return '大小未知'
    size=max(0,float(value))
    for unit in ('B','KB','MB','GB','TB'):
        if size<1024 or unit=='TB':return f'{size:.1f} {unit}' if unit!='B' else f'{size:.0f} B'
        size/=1024


def time_text(seconds):
    if seconds is None:return '计算中'
    seconds=max(0,int(seconds))
    if seconds>=3600:return f'{seconds//3600} 小时 {(seconds%3600)//60} 分'
    if seconds>=60:return f'{seconds//60} 分 {seconds%60} 秒'
    return f'{seconds} 秒'


class Meter:
    def __init__(self,emit,total=None,received=0,clock=time.monotonic,**context):
        self.emit=emit;self.total=total;self.received=received;self.clock=clock;self.context=context
        self.samples=deque([(clock(),received)]);self.last=0

    def update(self,received,force=False):
        now=self.clock();self.received=received;self.samples.append((now,received))
        while len(self.samples)>2 and self.samples[1][0]<now-5:self.samples.popleft()
        elapsed=now-self.samples[0][0]
        speed=(received-self.samples[0][1])/elapsed if elapsed>=.15 else None
        eta=(self.total-received)/speed if self.total and speed and speed>0 else None
        if force or now-self.last>=.3:
            self.emit('progress',received=received,total=self.total,speed=speed,eta=eta,**self.context);self.last=now
        return speed


def error_text(error):
    if isinstance(error,urllib.error.HTTPError):return '服务器返回 HTTP '+str(error.code)
    text=str(error)
    if 'CERTIFICATE_VERIFY_FAILED' in text:return 'HTTPS 证书校验未通过'
    if 'SSL' in text or 'EOF' in text:return 'HTTPS 连接中断（TLS EOF）'
    if isinstance(error,TimeoutError) or 'timed out' in text.lower():return '连接超时或线路持续过慢'
    if '校验' in text:return '文件校验未通过，重新下载'
    return type(error).__name__+'：'+text[:160]


def file_sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(4*1024**2),b''):value.update(block)
    return value.hexdigest()


def download_file(sources,path,sha256=None,emit=emit_event,timeout=20,slow_after=45,min_speed=16*1024):
    """Retain verified-file partials across mirror switches; never disable TLS checks."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and sha256 and file_sha(path)==sha256:
        emit('cached',file=path.name,source='本机已校验缓存',received=path.stat().st_size,total=path.stat().st_size);return path
    part=path.with_name(path.name+'.part');meta=part.with_name(part.name+'.json')
    signature={'sha256':sha256,'name':path.name}
    try:valid=sha256 and json.loads(meta.read_text(encoding='utf-8'))==signature
    except (OSError,ValueError):valid=False
    if not valid:part.unlink(missing_ok=True)
    meta.write_text(json.dumps(signature),encoding='utf-8')
    reason='';previous=''
    for index,source in enumerate(sources,1):
        label,url=source if isinstance(source,(tuple,list)) else (urllib.parse.urlsplit(source).hostname,source)
        offset=part.stat().st_size if part.is_file() else 0
        emit('source',file=path.name,source=label,host=urllib.parse.urlsplit(url).hostname,attempt=index,attempts=len(sources),reason=reason,previous=previous,resumed=offset)
        headers={'User-Agent':'ContentHub-Resources/1.1','Accept-Encoding':'identity'}
        if offset:headers['Range']=f'bytes={offset}-'
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=timeout) as response:
                status=getattr(response,'status',200);length=int(response.headers.get('Content-Length') or 0)
                if offset and status==206:
                    match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)',response.headers.get('Content-Range',''))
                    if not match or int(match[1])!=offset:raise RuntimeError('断点响应位置无效')
                    total=int(match[3]) if match[3]!='*' else None
                else:
                    if offset:emit('activity',message='当前线路不支持断点续传，从头下载并重新校验。')
                    offset=0;total=length or None
                meter=Meter(emit,total,offset,file=path.name);received=offset;started=time.monotonic()
                meter.update(received,True)
                with part.open('ab' if offset else 'wb') as output:
                    read=getattr(response,'read1',response.read)
                    while block:=read(64*1024):
                        output.write(block);received+=len(block);speed=meter.update(received)
                        if time.monotonic()-started>slow_after and speed is not None and speed<min_speed:
                            raise TimeoutError('线路持续过慢；保留下载片段并切换备用源')
                if total is not None and received!=total:raise OSError('连接提前结束，保留已下载片段')
                if sha256 and file_sha(part)!=sha256:
                    part.unlink(missing_ok=True);raise RuntimeError('下载文件校验失败')
                meter.total=received;meter.update(received,True)
            os.replace(part,path);meta.unlink(missing_ok=True)
            emit('transfer-done',file=path.name,total=received);return path
        except (OSError,ValueError,RuntimeError,http.client.HTTPException) as error:
            reason=error_text(error);previous=label
            emit('source-failed',file=path.name,source=label,reason=reason,will_retry=index<len(sources))
    raise RuntimeError(f'{path.name} 下载未完成：{reason}。已下载片段保留，重试可继续。')


def amount(text):
    match=re.fullmatch(r'([\d.]+)\s*([kmgt]?)(?:i?b)?',text.strip(),re.I)
    if not match:return None
    return float(match[1])*1024**('kmgt'.find(match[2].lower())+1 if match[2] else 0)


def line_progress(line):
    text=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',line).strip()
    raw=re.search(r'Progress\s+(\d+)\s+of\s+(\d+)',text)
    if raw:return {'kind':'progress','received':int(raw[1]),'total':int(raw[2]) or None}
    totals=re.search(r'(\d+(?:\.\d+)?\s*[kKmMgGtT]?(?:i?[bB])?)\s*/\s*(\d+(?:\.\d+)?\s*[kKmMgGtT]?(?:i?[bB])?)',text)
    if totals and re.search(r'[kKmMgGtTbB]',totals[1]+totals[2]):
        received,total=amount(totals[1]),amount(totals[2])
        if received is not None and total and received<=total:
            speed=re.search(r'(\d+(?:\.\d+)?\s*[kKmMgGtT](?:i?[bB])?)/s',text)
            label=re.search(r'Downloading\s*\[([^\]]+)\]',text)
            return {'kind':'progress','received':received,'total':total,**({'speed':amount(speed[1])} if speed else {}),**({'file':label[1]} if label else {})}
    browser=re.search(r'(\d+)%\s+of\s+(\d+(?:\.\d+)?)\s*(MiB|MB|GiB|GB)',text)
    if browser:
        total=amount(browser[2]+browser[3]);return {'kind':'progress','received':total*int(browser[1])/100,'total':total,'estimated':True}
    download=re.search(r'Downloading\s+(\S+)',text)
    if download:
        name=urllib.parse.urlsplit(download[1]).path.rsplit('/',1)[-1]
        return {'kind':'file','file':name[:180]}
    if text.startswith('[models '):return {'kind':'activity','message':text,'file':text.split('] ',1)[-1]}
    if text.startswith(('Installing collected packages','Successfully installed','检查 Playwright','补装')):
        return {'kind':'activity','message':text[:220]}
    return None


def run_logged(command,log,env=None,timeout=1200,emit=emit_event):
    """Tee pip, browser and model output live, including carriage-return progress."""
    target=Path(log);target.parent.mkdir(parents=True,exist_ok=True)
    environment=dict(os.environ if env is None else env,PYTHONUNBUFFERED='1',PYTHONIOENCODING='utf-8')
    child=subprocess.Popen(command,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    timed_out=threading.Event()
    def stop():
        if child.poll() is None:
            timed_out.set()
            if os.name=='nt':subprocess.run(['taskkill.exe','/PID',str(child.pid),'/T','/F'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            else:child.kill()
    timer=threading.Timer(timeout,stop);timer.daemon=True;timer.start()
    try:
        with target.open('a',encoding='utf-8') as output:
            for line in child.stdout:
                output.write(line);output.flush()
                forwarded=parse_event(line) or line_progress(line)
                if forwarded:
                    kind=forwarded.pop('kind');forwarded.pop('at',None);emit(kind,**forwarded)
                elif os.environ.get('CONTENT_HUB_PROGRESS')=='1':print(line.rstrip(),file=sys.stderr,flush=True)
        code=child.wait()
        if timed_out.is_set():raise subprocess.TimeoutExpired(command,timeout)
        return subprocess.CompletedProcess(command,code)
    finally:timer.cancel();child.stdout.close()


class ProgressState:
    def __init__(self):
        self.phase='等待开始';self.index=0;self.steps=6;self.file='—';self.source='尚未联网';self.attempt=''
        self.received=0;self.total=None;self.speed=None;self.eta=None;self.switch='尚未切换线路';self.message='';self.active=False;self.updated=time.monotonic();self.meter=None;self.estimated=False

    def apply(self,event):
        kind=event.get('kind');now=time.monotonic()
        if kind=='phase':
            self.phase=event.get('name',self.phase);self.index=event.get('index',self.index);self.steps=event.get('steps',self.steps)
            self.file='—';self.active=False;self.speed=self.eta=self.total=None;self.received=0;self.message=event.get('message','');self.meter=None;self.source='本机安装／校验';self.attempt=''
        if kind=='source':
            self.source=event.get('source','未知线路');self.attempt=f"（{event.get('attempt',1)}/{event.get('attempts',1)}）"
            if event.get('previous'):
                stamp=time.strftime('%H:%M:%S',time.localtime(event.get('at',time.time())))
                self.switch=f"{stamp}  {event['previous']} → {self.source}；{event.get('reason','当前线路未完成')}"
            self.message='正在连接当前下载源…';self.active=True;self.speed=None;self.meter=None;self.updated=now
        if kind in ('file','source'):
            self.file=event.get('file',self.file);self.received=event.get('resumed',0);self.total=None;self.speed=self.eta=None;self.meter=None;self.active=True
        if kind=='progress':
            received=max(0,event.get('received',0));total=event.get('total');self.total=total if total and total>=received else None
            if self.meter is None or received<self.received:
                self.meter=Meter(lambda *_args,**_kwargs:None,self.total,received)
            self.meter.total=self.total;calculated=self.meter.update(received)
            self.received=received;self.speed=event.get('speed') or calculated;self.estimated=event.get('estimated',False)
            self.eta=event.get('eta') or ((self.total-received)/self.speed if self.total and self.speed else None)
            self.file=event.get('file',self.file);self.active=True;self.updated=now;self.message='正在传输，已完成部分会保留。'
        if kind=='activity':
            self.message=event.get('message','正在安装或自检…');self.file=event.get('file',self.file);self.active=False;self.speed=self.eta=None
        if kind=='source-failed':self.message=f"{event.get('source','当前源')}：{event.get('reason','连接中断')}";self.speed=self.eta=None
        if kind in ('cached','transfer-done'):
            self.file=event.get('file',self.file);self.received=event.get('total',self.received);self.total=event.get('total',self.total)
            self.active=False;self.speed=self.eta=None;self.message='已校验并复用本机资源' if kind=='cached' else '文件传输完成，继续安装或校验'
            if kind=='cached':self.source=event.get('source','本机资源');self.attempt=''

    def display(self):
        percent=f'{self.received/self.total*100:.1f}%' if self.total else '总大小未知'
        stalled=self.active and time.monotonic()-self.updated>5
        speed=('约 ' if self.estimated else '')+byte_text(self.speed)+'/s' if self.speed and not stalled else ('等待数据…' if self.active else '当前未在传输')
        return {'phase':f'阶段 {self.index}/{self.steps} · {self.phase}','file':self.file,'source':self.source+' '+self.attempt,
            'bytes':byte_text(self.received)+' / '+byte_text(self.total)+'  ·  '+percent,'speed':speed,
            'eta':'预计剩余：'+(time_text(self.eta) if self.active and not stalled else '计算中' if self.active else '—'),
            'switch':self.switch,'message':self.message,'percent':self.received/self.total*100 if self.total else None}
