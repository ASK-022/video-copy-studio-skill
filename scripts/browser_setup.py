"""Prepare and check Chromium with the registered runtime's Python interpreter."""
import json
import os
from pathlib import Path
import subprocess
import sys

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
            if run(['-m', 'pip', 'install', 'playwright>=1.50,<2'], '补装 Playwright 依赖').returncode:
                raise RuntimeError('Playwright 依赖安装失败，安装未完成。查看 '+str(log)+'；'+retry)
        if run(['-m', 'playwright', 'install', 'chromium'], '下载独立 Chromium 浏览器').returncode:
            raise RuntimeError('Chromium 下载失败，安装未完成。查看 '+str(log)+'；'+retry)
        try:
            result = subprocess.run([str(python), '-c', PROBE], env=browser_env(path),
                stdout=output, stderr=output, timeout=45,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('Chromium 启动自检超时，安装未完成。查看 '+str(log)+'；'+retry) from exc
        if result.returncode:
            raise RuntimeError('Chromium 启动自检失败，安装未完成。查看 '+str(log)+'；'+retry)
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
