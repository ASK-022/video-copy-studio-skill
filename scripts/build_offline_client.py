"""Build a clean, relocatable Windows client and verified standalone resource ZIPs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from bootstrap import upstream,patch_runtime,UPSTREAM_SHA256
from prepare_models import model_status

ROOT=Path(__file__).resolve().parents[1]
VERSION=(ROOT/'VERSION').read_text().strip()
SKIP={'.git','.venv','__pycache__','dist','.studio','.links','releases'}


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(4*1024*1024),b''):result.update(chunk)
    return result.hexdigest()


def copy_tree(source,target):
    def ignore(folder,names):return [name for name in names if name in SKIP or name.endswith(('.pyc','.log')) or name in ('runtime.json','installation.json','.env')]
    shutil.copytree(source,target,ignore=ignore)


def freeze(entry,name,output,work):
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
        '--name',name,'--distpath',str(output),'--workpath',str(work/name),'--specpath',str(work),
        '--paths',str(ROOT/'assets/studio'),'--add-data',str(ROOT/'VERSION')+os.pathsep+'.',str(ROOT/'scripts'/entry)],check=True)


def stage(source,work):
    destination=work/('VideoCopyStudio-Offline-v'+VERSION)
    if destination.exists():raise ValueError('离线构建目录已存在，请选择新的 --work 目录。')
    config=json.loads((source/'runtime.json').read_text(encoding='utf-8'))
    if not model_status(source/'models-ready.json',config['model_cache']):raise ValueError('来源运行时尚未通过模型自检。')
    destination.mkdir(parents=True)
    print('Copying clean Python and installed dependencies...',flush=True)
    copy_tree(source/'python-3.12.10/tools',destination/'Runtime/python')
    site=destination/'Runtime/python/Lib/site-packages'
    assert site.resolve().is_relative_to(destination.resolve())
    shutil.rmtree(site)
    copy_tree(Path(config['python']).parents[1]/'Lib/site-packages',site)
    for pth in site.glob('*.pth'):
        if ':\\' in pth.read_text(encoding='utf-8',errors='replace'):raise ValueError('运行依赖包含不可搬移的绝对导入路径：'+pth.name)
    print('Copying public app, engine and browser resources...',flush=True)
    copy_tree(ROOT,destination/'App')
    bootstrap_assets=destination/'App/assets/bootstrap'
    assert bootstrap_assets.resolve().is_relative_to(destination.resolve())
    shutil.rmtree(bootstrap_assets)
    upstream(destination/'Engine');patch_runtime(destination/'Engine')
    copy_tree(Path(config['browser_path']),destination/'Browsers')
    # Preserve the unmodified FFmpeg distribution's licenses and documentation.
    archive=source.parents[0]/'ffmpeg-installer-check.zip'
    if not archive.is_file():raise ValueError('请在来源运行时的同级目录提供原版 ffmpeg-installer-check.zip。')
    if digest(archive)!='60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba':raise ValueError('FFmpeg 来源校验失败。')
    with zipfile.ZipFile(archive) as original:
        for item in original.infolist():
            if item.is_dir():continue
            parts=Path(item.filename).parts[1:]
            target=destination/'FFmpeg'/Path(*parts)
            if not target.resolve().is_relative_to((destination/'FFmpeg').resolve()):raise ValueError('无效 FFmpeg 路径。')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read(item))
    print('Copying local model files without SDK account caches...',flush=True)
    models={'sensevoice':'iic--SenseVoiceSmall','punctuation':'damo--punc_ct-transformer_zh-cn-common-vocab272727-pytorch',
            'alignment':'iic--speech_timestamp_prediction-v1-16k-offline'}
    for name,repository in models.items():
        target=destination/'Models'/name;target.mkdir(parents=True)
        for path in (Path(config['model_cache'])/'models'/repository/'snapshots/master').iterdir():
            if path.is_file() and not path.name.startswith('.'):
                if path.is_symlink():raise ValueError('模型文件不能依赖外部符号链接。')
                shutil.copy2(path,target/path.name)
    files=[p for p in (destination/'Models').rglob('*') if p.is_file()]
    files+=list((site/'rapidocr_onnxruntime').rglob('*.onnx'))
    proof={'contract':1,'loaded':dict.fromkeys(('sensevoice','punctuation','alignment','ocr'),True),
           'files':[{'path':p.relative_to(destination).as_posix(),'bytes':p.stat().st_size} for p in files]}
    (destination/'model-receipt.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'offline-client.json').write_text(json.dumps({'format':'video-copy-studio-offline/v1','version':VERSION,'platform':'windows-x64'}),encoding='utf-8')
    (destination/'使用说明.txt').write_text('双击 VideoCopyStudio.exe 打开客户端。安装和本地转写无需联网；AI 改写、公开链接解析和检查更新仍需联网。\n个人资料保存在 %LOCALAPPDATA%\\VideoCopyStudioOffline，与程序目录分开；更新离线版时可继续使用这些资料。\n原始第三方许可证保存在 App、Runtime/python、FFmpeg 和 Models 下。\n',encoding='utf-8-sig')
    freeze('offline_client.py','VideoCopyStudio',destination,work)
    print(json.dumps({'staged':str(destination)},ensure_ascii=False),flush=True)


def package(work,output):
    destination=work/('VideoCopyStudio-Offline-v'+VERSION)
    if not (destination/'VideoCopyStudio.exe').is_file():raise ValueError('请先 stage 并验证离线客户端。')
    proof_path=work/'offline-verified.json'
    if not proof_path.is_file():raise ValueError('请先完成禁止外网连接的离线验收，并提供 offline-verified.json。')
    proof=json.loads(proof_path.read_text(encoding='utf-8'))
    if not proof.get('verified') or proof.get('external_attempts')!=0 or proof.get('client_sha256')!=digest(destination/'VideoCopyStudio.exe'):
        raise ValueError('离线验收记录与当前客户端不匹配。')
    output.mkdir(parents=True,exist_ok=True)
    groups=[];group=[];size=0
    for path in sorted(destination.rglob('*')):
        if not path.is_file():continue
        if any(part in SKIP for part in path.relative_to(destination).parts):continue
        if path.is_symlink():raise ValueError('离线包不能含外部符号链接。')
        length=path.stat().st_size
        if length>1300*1024*1024:raise ValueError('单文件过大，无法安全分包。')
        if size+length>1300*1024*1024 and group:groups.append(group);group=[];size=0
        group.append(path);size+=length
    if group:groups.append(group)
    def compress(item):
        index,group=item;path=output/f'VideoCopyStudio-Offline-v{VERSION}-part{index:02d}.zip'
        print('Compressing '+path.name,flush=True)
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
            for source in group:archive.write(source,source.relative_to(work).as_posix())
        if path.stat().st_size>=2*1024**3:raise ValueError('分包超过 GitHub 单附件限制。')
        return {'name':path.name,'bytes':path.stat().st_size,'sha256':digest(path)}
    with ThreadPoolExecutor(max_workers=3) as pool:parts=list(pool.map(compress,enumerate(groups,1)))
    description={'format':'video-copy-studio-offline-downloads/v1','version':VERSION,'client_dir':destination.name,
        'unpacked_bytes':sum(p.stat().st_size for group in groups for p in group),'parts':parts}
    manifest=output/f'offline-downloads-v{VERSION}.json'
    manifest.write_text(json.dumps(description,ensure_ascii=False,indent=2),encoding='utf-8')
    freeze('offline_setup.py','VideoCopyStudio-Offline-Setup-v'+VERSION,output,work)
    setup=output/f'VideoCopyStudio-Offline-Setup-v{VERSION}.exe'
    (output/'SHA256SUMS.txt').write_text(''.join(item['sha256']+'  '+item['name']+'\n' for item in parts)+digest(setup)+'  '+setup.name+'\n'+digest(manifest)+'  '+manifest.name+'\n',encoding='ascii')
    (output/'README-OFFLINE.txt').write_text('请下载本目录全部 ZIP 分包、offline-downloads 清单和 Offline-Setup.exe，放在同一文件夹。\n双击 Offline-Setup.exe，选择安装位置，校验和解压完成后点击“打开离线客户端”。安装过程无需联网、不需要另装 Python 或解压软件。\n进入客户端后可断网导入本地视频并转写。AI 改写与链接解析仍需联网并由使用者配置自己的服务。\n国内采用蓝奏云时，用 build_lanzou_package.py 生成小分包与专用安装器；原始大分包可用于 U 盘或共享盘分发。两种分包勿混用，分享链接以实际上传后生成的地址为准。\n',encoding='utf-8-sig')
    print(json.dumps(description,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['stage','package']);parser.add_argument('--source',type=Path)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.work=args.work.resolve();args.output=args.output.resolve();args.work.mkdir(parents=True,exist_ok=True)
    (stage(args.source.resolve(),args.work) if args.phase=='stage' else package(args.work,args.output))
