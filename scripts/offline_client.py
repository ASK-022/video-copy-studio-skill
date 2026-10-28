"""Relocatable desktop client using its own Python, models and Chromium resources."""
import argparse
import hashlib
import http.cookiejar
import http.client
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
import urllib.error
import urllib.request
from urllib.parse import urlsplit

NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)


@contextmanager
def single_client(data):
    if os.name!='nt':
        yield True;return
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[wintypes.LPVOID,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.ReleaseMutex.argtypes=[wintypes.HANDLE];kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    name='Local\\VideoCopyStudioOffline-'+hashlib.sha256(str(Path(data).resolve()).casefold().encode()).hexdigest()[:24]
    handle=kernel.CreateMutexW(None,False,name)
    if not handle:raise OSError(ctypes.get_last_error(),'无法创建客户端实例锁。')
    acquired=kernel.WaitForSingleObject(handle,0) in (0,0x80)
    try:yield acquired
    finally:
        if acquired:kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def request(url,path='',data=None):
    parsed=urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('离线客户端只允许访问本机服务。')
    if not path.startswith('/api/'):raise ValueError('客户端控制路径无效。')
    connection=http.client.HTTPConnection(parsed.hostname,parsed.port or 80,timeout=5)
    try:
        connection.request('GET','/');response=connection.getresponse();response.read()
        cookie=(response.getheader('Set-Cookie') or '').split(';',1)[0]
        body=json.dumps(data).encode() if data is not None else None
        connection.request('POST' if data is not None else 'GET',path,body=body,
            headers={'Content-Type':'application/json','X-Studio-Request':'1','Cookie':cookie})
        response=connection.getresponse();raw=response.read()
        if response.status>=400:raise urllib.error.HTTPError(url+path,response.status,response.reason,response.headers,io.BytesIO(raw))
        return json.loads(raw)
    finally:connection.close()


def read_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return {} if default is None else default


def atomic_json(path,value):
    path=Path(path);temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)


def paths(root):
    root=Path(root).resolve();description=read_json(root/'offline-client.json')
    if description.get('format')!='video-copy-studio-offline/v1':raise ValueError('离线客户端资源不完整，请重新解压完整包。')
    result={'root':root,'skill':root/'App','python':root/'Runtime/python/python.exe','engine':root/'Engine',
        'models':root/'Models','browsers':root/'Browsers','ffmpeg':root/'FFmpeg/bin/ffmpeg.exe','version':description['version']}
    for path in (result['python'],result['ffmpeg'],result['skill']/'VERSION',result['engine']/'webmain.py'):
        if not path.is_file():raise ValueError('离线资源缺失：'+str(path))
    return result


def environment(locations,data,instance,port):
    env=dict(os.environ)
    env.pop('PYTHONHOME',None)
    env['PYTHONPATH']=env.get('VIDEO_COPY_STUDIO_TEST_PATH','')
    env.update(PYTHONNOUSERSITE='1',PYTHONIOENCODING='utf-8',PYTHONPYCACHEPREFIX=str(data/'pycache'),COPY_STUDIO_ASR_ROOT=str(locations['engine']),
        COPY_STUDIO_ASR_PYTHON=str(locations['python']),COPY_STUDIO_DATA=str(data/'data'),COPY_STUDIO_PORT=str(port),
        COPY_STUDIO_INSTANCE=instance,VIDEO_COPY_STUDIO_OFFLINE_MODELS=str(locations['models']),
        MODELSCOPE_CACHE=str(data/'cache'),MODEL_CACHE_DIR=str(locations['models']),ENABLE_GPU='false',
        PLAYWRIGHT_BROWSERS_PATH=str(locations['browsers']),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    env['PATH']=str(locations['ffmpeg'].parent)+os.pathsep+env.get('PATH','')
    return env


def close_service(state):
    try:
        health=request(state['url'],'/api/health')
        if health.get('instance')!=state.get('instance'):return
        request(state['url'],'/api/client/close',{'instance':state['instance']})
        for _ in range(100):
            try:request(state['url'],'/api/health')
            except OSError:return
            time.sleep(.1)
        raise ValueError('旧客户端尚未退出，请稍后再打开。')
    except urllib.error.HTTPError as exc:
        if exc.code==409:raise ValueError('仍有任务正在处理，完成后再切换客户端。') from exc
        raise ValueError('旧离线客户端无法安全退出，请关闭旧客户端后重试。') from exc
    except (OSError,KeyError):return


def start(root,data):
    locations=paths(root);data=Path(data).resolve();data.mkdir(parents=True,exist_ok=True)
    state_path=data/'offline-state.json';old=read_json(state_path)
    if old:
        try:
            health=request(old['url'],'/api/health')
            if health.get('instance')==old.get('instance'):
                if old.get('bundle')==str(locations['root']) and old.get('version')==locations['version']:return locations,old
                close_service(old)
        except (OSError,KeyError):pass
    with socket.socket() as listener:
        try:listener.bind(('127.0.0.1',8777))
        except OSError:listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
    instance=secrets.token_urlsafe(24);env=environment(locations,data,instance,port)
    receipt=read_json(locations['root']/'model-receipt.json')
    converted=[]
    for item in receipt.get('files',[]):
        path=locations['root']/item['path']
        if not path.resolve().is_relative_to(locations['root']) or not path.is_file() or path.stat().st_size!=item['bytes']:
            raise ValueError('离线模型资源缺失或不完整：'+item['path'])
        converted.append({'path':str(path),'bytes':item['bytes']})
    if not converted:raise ValueError('离线模型清单缺失。')
    atomic_json(data/'models-ready.json',dict(receipt,cache=str(locations['models']),files=converted))
    config={'python':str(locations['python']),'pythonw':str(locations['python'].with_name('pythonw.exe')),
        'asr_root':str(locations['engine']),'ffmpeg':str(locations['ffmpeg']),'port':port,'data_dir':str(data/'data'),
        'model_cache':str(locations['models']),'browser_path':str(locations['browsers'])}
    atomic_json(data/'runtime.json',config)
    with (data/'server.log').open('ab') as log:
        if getattr(sys,'frozen',False):
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            child=subprocess.Popen([str(locations['python']),'-m','client.app'],cwd=locations['skill']/'assets/studio',
        env=env,stdout=log,stderr=log,creationflags=NO_WINDOW)
        finally:
            if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(str(Path(sys._MEIPASS)))
    state={'url':f'http://127.0.0.1:{port}','instance':instance,'pid':child.pid,'bundle':str(locations['root']),'version':locations['version']}
    last_error='服务尚未就绪。'
    for _ in range(120):
        try:
            if request(state['url'],'/api/health').get('instance')==instance:
                atomic_json(state_path,state);return locations,state
        except urllib.error.HTTPError as exc:last_error=str(exc)+': '+exc.read().decode('utf-8',errors='replace')[:500]
        except OSError as exc:
            last_error=str(exc)
            import traceback
            (data/'startup-probe.log').write_text(traceback.format_exc(),encoding='utf-8')
        if child.poll() is not None:break
        time.sleep(.25)
    child.terminate()
    raise ValueError('离线客户端启动失败：'+last_error+'；请查看 '+str(data/'server.log'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path)
    parser.add_argument('--data-dir',type=Path,default=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'VideoCopyStudioOffline')
    parser.add_argument('--self-test',type=Path);parser.add_argument('--close',action='store_true');args=parser.parse_args()
    root=args.root or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])
    if args.close:close_service(read_json(args.data_dir/'offline-state.json'));return
    if args.self_test:
        locations,state=start(root,args.data_dir)
        args.self_test.write_text(json.dumps({'ok':True,**state},ensure_ascii=False),encoding='utf-8');return
    with single_client(args.data_dir) as acquired:
        if not acquired:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'离线客户端已经打开，请从任务栏切换到客户端窗口。','文案工坊',64);return
        locations,state=start(root,args.data_dir)
        chrome=next(iter(locations['browsers'].glob('chromium-*/chrome-win64/chrome.exe')),None)
        if not chrome:raise ValueError('离线 Chromium 窗口资源缺失。')
        if getattr(sys,'frozen',False):
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            browser=subprocess.Popen([str(chrome),'--app='+state['url'],'--user-data-dir='+str(args.data_dir/'browser-profile'),
                '--no-first-run','--disable-background-networking','--disable-component-update','--disable-sync','--metrics-recording-only'],creationflags=NO_WINDOW)
        finally:
            if getattr(sys,'frozen',False):ctypes.windll.kernel32.SetDllDirectoryW(str(Path(sys._MEIPASS)))
        browser.wait()
        try:close_service(state)
        except ValueError:pass


if __name__=='__main__':
    try:main()
    except Exception as exc:
        if '--self-test' in sys.argv:
            target=Path(sys.argv[sys.argv.index('--self-test')+1]);target.parent.mkdir(parents=True,exist_ok=True)
            import traceback
            target.write_text(json.dumps({'ok':False,'error':str(exc),'traceback':traceback.format_exc()},ensure_ascii=False),encoding='utf-8')
            if sys.stderr:print(str(exc),file=sys.stderr)
        else:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,str(exc),'文案工坊离线客户端',16)
        sys.exit(1)
