"""Prepare and check Chromium with the registered runtime's Python interpreter."""
import json
import os
from pathlib import Path
import subprocess
import sys
from download_sources import pip_install,BROWSER_HOSTS

PROBE = '''from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    executable = Path(p.chromium.executable_path)
    if not executable.is_file():
        raise FileNotFoundError("Playwright Chromium is missing")
    browser = p.chromium.launch(headless=True)
    browser.close()
'''


def browser_env(path):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if path is not None:
        env['PLAYWRIGHT_BROWSERS_PATH'] = str(path)
    return env


def browser_status(python, path):
    if not python or not Path(python).is_file():
        return False
    try:
        result = subprocess.run([str(python), '-c', PROBE], env=browser_env(path),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def prepare_browser(root, python, path=None):
    root = Path(root).resolve()
    python = Path(python).resolve()
    if not python.is_file():
        raise ValueError('运行时 Python 不存在，无法安装浏览器。')
    root.mkdir(parents=True, exist_ok=True)
    path = Path(path or root/'browsers').resolve()
    log = root/'bootstrap.log'
    retry = '修复网络后重跑安装，或执行运行时目录下的 studio.cmd repair-browser。'
    with log.open('a', encoding='utf-8') as output:
        def run(arguments, label):
            print(label+'；日志：'+str(log), file=sys.stderr, flush=True)
            output.write('\n'+label+'\n'); output.flush()
            return subprocess.run([str(python), *arguments], env=browser_env(path),
                stdout=output, stderr=output, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

        # An old registered runtime may have ASR installed but no Playwright package.
        if run(['-c', 'import playwright.sync_api'], '检查 Playwright 依赖').returncode:
            pip_install(python,['playwright>=1.50,<2'],log)
        if browser_status(python,path):return str(path)
        hosts=list(BROWSER_HOSTS)
        custom=os.environ.get('PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST') or os.environ.get('PLAYWRIGHT_DOWNLOAD_HOST')
        if custom:hosts.insert(0,('用户指定浏览器源',custom))
        for label,host in hosts:
            env=browser_env(path)
            env.pop('PLAYWRIGHT_DOWNLOAD_HOST',None);env.pop('PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST',None)
            env['PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT']='20000'
            if host:env.update(PLAYWRIGHT_DOWNLOAD_HOST=host,PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST=host)
            print('准备浏览器：'+label,file=sys.stderr,flush=True)
            output.write('\n准备浏览器：'+label+'\n');output.flush()
            try:
                result=subprocess.run([str(python),'-m','playwright','install','chromium'],env=env,
                    stdout=output,stderr=output,timeout=1800,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode==0 and browser_status(python,path):return str(path)
            except (OSError,subprocess.TimeoutExpired) as exc:
                output.write(type(exc).__name__+'\n')
            output.write('当前浏览器源未就绪，尝试下一下载源。\n');output.flush()
        raise RuntimeError('浏览器下载或启动自检失败，安装未完成。查看 '+str(log)+'；'+retry)
    return str(path)


def repair_browser(root, config):
    path = prepare_browser(root, config['python'], config.get('browser_path'))
    updated = dict(config, browser_path=path)
    target = Path(root)/'runtime.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)
    return {'browser_ready': True, 'browser_path': path,
            'next': '浏览器修复完成；关闭正在运行的文案工坊服务，再用桌面快捷方式重新打开。'}
