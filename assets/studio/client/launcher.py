"""Open the local client in its own Chrome application window."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time
import webbrowser

import httpx

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get('COPY_STUDIO_PORT','8777'))
URL = f'http://127.0.0.1:{PORT}'
DATA = ROOT/'.studio'


def alive():
    try:
        with httpx.Client(trust_env=False,timeout=2) as client:
            root=client.get(URL)
            if root.status_code!=200 or '文案工坊' not in root.text:
                return False
            return client.get(URL+'/api/health').json().get('ok') is True
    except Exception:
        return False


def launch():
    DATA.mkdir(exist_ok=True)
    if not alive():
        with (DATA/'server.log').open('ab') as output:
            subprocess.Popen([sys.executable,'-m','client.app'],cwd=ROOT,stdout=output,stderr=output,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(40):
            if alive():
                break
            time.sleep(.4)
        else:
            raise RuntimeError('客户端服务启动失败。请检查 '+str(PORT)+' 端口是否被占用；日志位于 .studio/server.log。')
    chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
    edge=Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
    browser=chrome if chrome.is_file() else edge
    if browser.is_file():
        profile=Path(os.environ.get('LOCALAPPDATA',str(DATA)))/'VideoCopyStudio/browser'
        subprocess.Popen([str(browser),'--app='+URL,'--user-data-dir='+str(profile),
                          '--no-first-run','--no-default-browser-check','--window-size=1320,920'])
    else:
        webbrowser.open(URL)


if __name__=='__main__':
    try:
        launch()
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(None,str(exc),'文案工坊启动失败',0x10)
