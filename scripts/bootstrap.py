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

SKILL=Path(__file__).resolve().parents[1]
UPSTREAM='https://codeload.github.com/Acclerate/video-transcriber/zip/bfce75fb1d9cf3e8444d531a4f96ec49faa467cf'
UPSTREAM_SHA256='3ee582c0b0b906769b9e0736965b7d715ab359fd82d5bcaabf87a5d44e042d08'


def home():
    return Path(os.environ.get('VIDEO_COPY_STUDIO_HOME',str(Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'VideoCopyStudio'))).resolve()


def ffmpeg_path(value=''):
    candidates=[value,os.environ.get('FFMPEG_PATH',''),shutil.which('ffmpeg') or '']
    for value in candidates:
        if value and Path(value).is_file() and Path(value).with_name('ffprobe.exe').is_file():return str(Path(value).resolve())
    return ''


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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-home',type=Path,default=home());parser.add_argument('--ffmpeg',default='')
    parser.add_argument('--port',type=int,default=8777);parser.add_argument('--install',action='store_true')
    parser.add_argument('--download-ffmpeg',action='store_true');parser.add_argument('--register-existing',action='store_true')
    parser.add_argument('--asr-root',type=Path);parser.add_argument('--python',type=Path)
    args=parser.parse_args();root=args.runtime_home.resolve();config=root/'runtime.json'
    if not 1024<=args.port<=65535:raise ValueError('port 必须在 1024..65535。')
    if os.name!='nt':raise RuntimeError('当前完整本地运行时支持 Windows 10/11。其他系统可阅读 Skill，但不能运行本机加密配置与桌面服务。')
    if not (3,10)<=sys.version_info[:2]<=(3,12):raise RuntimeError('请使用 Python 3.10、3.11 或 3.12 执行安装。')
    if not args.install and not args.register_existing:
        saved=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        print(json.dumps({'ok':bool(saved),'runtime_config':str(config),'installed':bool(saved),
             'python':str(args.python or saved.get('python','')),'ffmpeg_found':bool(ffmpeg_path(args.ffmpeg)),
             'next':'python scripts/bootstrap.py --install --download-ffmpeg','network_required_for_first_install':True},ensure_ascii=False));return
    root.mkdir(parents=True,exist_ok=True);ffmpeg=ffmpeg_path(args.ffmpeg)
    if not ffmpeg and args.download_ffmpeg:
        folder=root/'ffmpeg';folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'ffmpeg.zip';download('https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',archive)
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
    else:
        upstream(asr);python=asr/'.venv/Scripts/python.exe'
        if not python.exists():subprocess.run([sys.executable,'-m','venv',str(asr/'.venv')],check=True)
        model_cache=root/'models';model_cache.mkdir(exist_ok=True)
        (asr/'.env').write_text('ENABLE_GPU=false\nMODEL_CACHE_DIR='+model_cache.as_posix()+'\nLOG_LEVEL=INFO\n',encoding='utf-8')
        constraints=asr/'studio-constraints.txt';constraints.write_text('huggingface-hub<1\ntransformers<5\n',encoding='ascii')
        log=root/'bootstrap.log'
        commands=[[str(python),'-m','pip','install','-r',str(asr/'requirements.txt'),'-c',str(constraints)],
                  [str(python),'-m','pip','install','-r',str(SKILL/'assets/requirements-extra.txt'),'-c',str(constraints)]]
        with log.open('a',encoding='utf-8') as output:
            for command in commands:
                print('正在安装依赖，日志：'+str(log),file=sys.stderr,flush=True)
                result=subprocess.run(command,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode:raise RuntimeError('依赖安装失败，查看 bootstrap.log；修复网络后可重跑安装，现有数据保留。')
    if not python.is_file() or not (asr/'webmain.py').exists():raise RuntimeError('转写程序或 Python 路径无效。')
    data={'python':str(python),'asr_root':str(asr),'ffmpeg':ffmpeg,'port':args.port,'data_dir':str(root/'data')}
    temp=config.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(config)
    print(json.dumps({'ok':True,'runtime_config':str(config),'runtime_home':str(root),'model_download':'首次转写时按需下载，未打包模型权重'},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    try:main()
    except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));sys.exit(1)
