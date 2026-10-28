"""Install/check the Windows runtime without packaging personal state or large models."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from prepare_models import model_status
from browser_setup import prepare_browser
from extra_setup import prepare_extras

SKILL=Path(__file__).resolve().parents[1]
UPSTREAM='https://codeload.github.com/Acclerate/video-transcriber/zip/bfce75fb1d9cf3e8444d531a4f96ec49faa467cf'
UPSTREAM_SHA256='3ee582c0b0b906769b9e0736965b7d715ab359fd82d5bcaabf87a5d44e042d08'
FFMPEG_ARCHIVE='ffmpeg-9.0.2-essentials_build.zip'
FFMPEG_SHA256='60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'


def home():
    return Path(os.environ.get('VIDEO_COPY_STUDIO_HOME',str(Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'VideoCopyStudio'))).resolve()


def ffmpeg_path(value=''):
    candidates=[value,os.environ.get('FFMPEG_PATH',''),shutil.which('ffmpeg') or '']
    for value in candidates:
        if value and Path(value).is_file() and Path(value).with_name('ffprobe.exe').is_file():return str(Path(value).resolve())
    return ''


def write_launcher(root, python):
    # ASCII Python source plus JSON escapes work with Chinese user/Agent paths.
    launcher=root/'open-studio.pyw'
    launcher.write_text('import subprocess\nfrom pathlib import Path\n'
        +'command='+repr([str(python),str(SKILL/'scripts/studio_agent.py'),'--runtime-home',str(root),'start','--open'])+'\n'
        +'with (Path('+repr(str(root))+')/"launcher.log").open("ab") as log:\n'
        +'    result=subprocess.run(command,stdout=log,stderr=log,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))\n'
        +'if result.returncode:\n'
        +'    import ctypes\n'
        +'    ctypes.windll.user32.MessageBoxW(0,'+repr('启动失败，请查看 '+str(root/'launcher.log'))+', "文案工坊",16)\n',encoding='utf-8')
    pythonw=python.with_name('pythonw.exe')
    if not pythonw.exists():pythonw=python
    # A .cmd remains usable even if desktop shortcuts are disabled by company policy.
    command='@echo off\r\nchcp 65001 >nul\r\n"'+str(pythonw)+'" "'+str(launcher)+'"\r\n'
    (root/'打开文案工坊.cmd').write_bytes(command.encode('utf-8'))
    cli='@echo off\r\nchcp 65001 >nul\r\n'+subprocess.list2cmdline([str(python),str(SKILL/'scripts/studio_agent.py'),'--runtime-home',str(root)])+' %*\r\n'
    (root/'studio.cmd').write_bytes(cli.encode('utf-8'))
    return launcher,pythonw


def download(url,path,sha256=None):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'video-copy-studio-installer/1.0'}),timeout=90) as source,path.open('wb') as dest:
        shutil.copyfileobj(source,dest)
    if sha256 and hashlib.sha256(path.read_bytes()).hexdigest()!=sha256:raise RuntimeError('下载文件校验失败，未安装。')


def upstream(root):
    marker=root/'.studio-upstream-revision'
    if marker.exists():return
    if root.exists() and any(root.iterdir()):raise RuntimeError('转写目录非空且未被此安装器管理，请使用空目录或 --register-existing。')
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        archive=Path(temp)/'upstream.zip';download(UPSTREAM,archive,UPSTREAM_SHA256)
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                parts=Path(info.filename).parts[1:]
                if not parts or '..' in parts or info.is_dir():continue
                target=root.joinpath(*parts)
                if not target.resolve().is_relative_to(root.resolve()):raise RuntimeError('上游压缩包包含无效路径。')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read(info))
    # The pinned version uses an asyncio.Lock in an async method.
    path=root/'core/sensevoice_transcriber.py';text=path.read_text(encoding='utf-8')
    text=text.replace('        with self.model_lock:\n','        async with self.model_lock:\n',1)
    path.write_text(text,encoding='utf-8');marker.write_text(UPSTREAM_SHA256,encoding='ascii')


def patch_runtime(asr):
    # Keep this compatibility hook inside the app, never patch a system library.
    shutil.copyfile(SKILL/'scripts/asr_compat.py',asr/'studio_runtime_compat.py')
    source=asr/'core/sensevoice_transcriber.py'
    text=source.read_text(encoding='utf-8')
    hook='from studio_runtime_compat import fix_sentencepiece_paths\nfix_sentencepiece_paths()\n'
    if hook not in text:
        anchor='from loguru import logger\n'
        if anchor not in text:raise RuntimeError('转写源码版本不匹配，无法应用中文路径兼容修复。')
        source.write_text(text.replace(anchor,anchor+hook,1),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-home',type=Path,default=home());parser.add_argument('--ffmpeg',default='')
    parser.add_argument('--port',type=int,default=8777);parser.add_argument('--install',action='store_true')
    parser.add_argument('--download-ffmpeg',action='store_true');parser.add_argument('--register-existing',action='store_true')
    parser.add_argument('--asr-root',type=Path);parser.add_argument('--python',type=Path)
    parser.add_argument('--data-dir',type=Path,help='Existing studio data to preserve when registering a runtime; no files are copied.')
    parser.add_argument('--prepare-models',action='store_true',help='Also verify/download models for an explicitly registered existing runtime.')
    args=parser.parse_args();root=args.runtime_home.resolve();config=root/'runtime.json'
    previous=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    if not 1024<=args.port<=65535:raise ValueError('port 必须在 1024..65535。')
    if os.name!='nt':raise RuntimeError('当前完整本地运行时支持 Windows 10/11。其他系统可阅读 Skill，但不能运行本机加密配置与桌面服务。')
    if not (3,10)<=sys.version_info[:2]<=(3,12):raise RuntimeError('请使用 Python 3.10、3.11 或 3.12 执行安装。')
    if not args.install and not args.register_existing:
        saved=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        print(json.dumps({'ok':bool(saved),'runtime_config':str(config),'installed':bool(saved),
             'python':str(args.python or saved.get('python','')),'ffmpeg_found':bool(ffmpeg_path(args.ffmpeg)),
             'models_ready':model_status(root/'models-ready.json',saved.get('model_cache')),
             'next':'python scripts/bootstrap.py --install --download-ffmpeg','network_required_for_first_install':True},ensure_ascii=False));return
    root.mkdir(parents=True,exist_ok=True);ffmpeg=ffmpeg_path(args.ffmpeg or str(root/'ffmpeg/ffmpeg.exe'))
    model_cache=root/'models'
    if not ffmpeg and args.download_ffmpeg:
        folder=root/'ffmpeg';folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'ffmpeg.zip'
            urls=['https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/'+FFMPEG_ARCHIVE,
                  'https://www.gyan.dev/ffmpeg/builds/packages/'+FFMPEG_ARCHIVE]
            for url in urls:
                try:download(url,archive,FFMPEG_SHA256);break
                except (OSError,RuntimeError):
                    if url==urls[-1]:raise
            with zipfile.ZipFile(archive) as source:
                for name in ('ffmpeg.exe','ffprobe.exe'):
                    matches=[i for i in source.infolist() if i.filename.endswith('/bin/'+name)]
                    if len(matches)!=1:raise RuntimeError('FFmpeg 下载包格式不匹配。')
                    (folder/name).write_bytes(source.read(matches[0]))
        ffmpeg=ffmpeg_path(str(folder/'ffmpeg.exe'))
    if not ffmpeg:raise RuntimeError('未找到同目录的 ffmpeg.exe / ffprobe.exe，请指定 --ffmpeg 或 --download-ffmpeg。')
    asr=(args.asr_root or root/'runtime/video-transcriber').resolve()
    if args.register_existing:
        if not args.asr_root or not args.python:raise ValueError('--register-existing 需要 --asr-root 和 --python。')
        python=args.python.resolve()
        command=[str(python),'-c','from config.settings import settings; print(settings.MODEL_CACHE_DIR)']
        value=subprocess.check_output(command,cwd=asr,encoding='utf-8',env=dict(os.environ,PYTHONIOENCODING='utf-8')).strip().splitlines()[-1]
        model_cache=Path(value);model_cache=(asr/model_cache).resolve() if not model_cache.is_absolute() else model_cache.resolve()
    else:
        upstream(asr);python=asr/'.venv/Scripts/python.exe'
        if not python.exists():subprocess.run([sys.executable,'-m','venv',str(asr/'.venv')],check=True)
        model_cache.mkdir(exist_ok=True)
        (asr/'.env').write_text('ENABLE_GPU=false\nMODEL_CACHE_DIR='+model_cache.as_posix()+'\nLOG_LEVEL=INFO\n',encoding='utf-8')
        constraints=asr/'studio-constraints.txt';constraints.write_text('huggingface-hub<1\ntransformers<5\ntorch==2.6.0\ntorchaudio==2.6.0\nnumpy<2.3\n',encoding='ascii')
        log=root/'bootstrap.log'
        commands=[[str(python),'-m','pip','install','--upgrade','pip>=25.2,<27'],
                  [str(python),'-m','pip','install','torch==2.6.0','torchaudio==2.6.0','--index-url','https://pypi.org/simple'],
                  [str(python),'-c','import torch,torchaudio; assert torch.version.cuda is None, "Expected the Windows CPU build"'],
                  [str(python),'-m','pip','install','-r',str(asr/'requirements.txt'),'-c',str(constraints)]]
        with log.open('a',encoding='utf-8') as output:
            for command in commands:
                print('正在安装依赖，日志：'+str(log),file=sys.stderr,flush=True)
                result=subprocess.run(command,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode:raise RuntimeError('依赖安装失败，查看 bootstrap.log；修复网络后可重跑安装，现有数据保留。')
    browser_path=previous.get('browser_path')
    if args.install or args.prepare_models:
        prepare_extras(root,python)
        browser_path=prepare_browser(root,python,browser_path)
    if not python.is_file() or not (asr/'webmain.py').exists():raise RuntimeError('转写程序或 Python 路径无效。')
    if args.install or args.prepare_models:
        patch_runtime(asr)
        manifest=root/'models-ready.json'
        # Every install/repair loads the actual models, reusing downloaded weights.
        print('正在准备并验证本地模型（SenseVoice、标点、时间对齐、OCR）；详细日志：'+str(root/'models.log'),file=sys.stderr,flush=True)
        env=dict(os.environ,PYTHONIOENCODING='utf-8',MODELSCOPE_CACHE=str(model_cache),MODEL_CACHE_DIR=str(model_cache),ENABLE_GPU='false')
        env['PATH']=str(Path(ffmpeg).parent)+os.pathsep+env.get('PATH','')
        with (root/'models.log').open('a',encoding='utf-8') as output:
            result=subprocess.run([str(python),str(SKILL/'scripts/prepare_models.py'),'--asr-root',str(asr),
                '--cache',str(model_cache),'--manifest',str(manifest)],stdout=output,stderr=output,env=env,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not model_status(manifest,model_cache):raise RuntimeError('模型下载或加载自检失败，查看 models.log；安装未完成，可修复网络后重跑。')
    launcher,pythonw=write_launcher(root,python)
    data_dir=(args.data_dir or Path(previous.get('data_dir',str(root/'data')))).resolve()
    data={'python':str(python),'asr_root':str(asr),'ffmpeg':ffmpeg,'port':args.port,'data_dir':str(data_dir),
          'model_cache':str(model_cache),'launcher':str(launcher),'pythonw':str(pythonw)}
    if browser_path:data['browser_path']=browser_path
    temp=config.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(config)
    print(json.dumps({'ok':True,'runtime_config':str(config),'runtime_home':str(root),
        'models_ready':model_status(root/'models-ready.json',model_cache),'web_url':f'http://127.0.0.1:{args.port}/',
        'launcher':str(root/'打开文案工坊.cmd')},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    try:main()
    except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));sys.exit(1)
