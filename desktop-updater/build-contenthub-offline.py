"""Create one complete offline desktop ZIP from explicitly curated, tested resources."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess,sys,time,zipfile

base=Path(__file__).resolve().parents[2];version='1.1.1'
source=base/'.cache/offline-build-113/VideoCopyStudio-Offline-v1.1.3'
output=base/f'outputs/内容中台完整离线版-v{version}';output.mkdir(parents=True,exist_ok=True)
work=base/'.cache/contenthub-offline-full-build';work.mkdir(parents=True,exist_ok=True)
proof=json.loads((base/'.cache/contenthub-offline-source-probe.json').read_text(encoding='utf-8'))
assert proof['ok'] and proof['external_attempts']==0 and all(proof['loaded'].values()) and proof['browser_ready'] and proof['ffmpeg_ready']
assert json.loads((source/'offline-client.json').read_text(encoding='utf-8'))['format']=='video-copy-studio-offline/v1'
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
installer=base/f'outputs/内容中台安装包-v{version}/ContentHub-Setup-v{version}-x64.exe'
assert sha(installer)=='eac603507a7f9a1da505d33fad5ee4428efade4bdd9d60298791c53f883695df'
target=output/'程序安装组件（请勿单独运行）.exe'
if not target.exists():os.link(installer,target)
redistributable=base/'.cache/offline-system-components/VC_redist.x64.exe'
if not (output/redistributable.name).exists():os.link(redistributable,output/redistributable.name)
files=[];excluded={'.git','.cache','__pycache__'}
for folder in ('Runtime','Engine','FFmpeg','Browsers','Models'):
    for parent,directories,names in os.walk(source/folder,followlinks=False):
        directories[:]=sorted(name for name in directories if name not in excluded)
        for name in sorted(names):
            path=Path(parent)/name
            if name.endswith(('.pyc','.log','.part')) or name=='.env':continue
            assert not path.is_symlink(),'Resources must not link to external paths'
            files.append(path)
files.extend([source/'offline-client.json',source/'model-receipt.json'])
assert all(path.is_file() for path in files)
total=sum(path.stat().st_size for path in files)
archive=output/'ContentHub-Resources-r1.zip'
resource_record=work/'resources.json'
cached=json.loads(resource_record.read_text(encoding='utf-8')) if resource_record.exists() else {}
fingerprint=hashlib.sha256(json.dumps([(p.relative_to(source).as_posix(),p.stat().st_size,p.stat().st_mtime_ns) for p in files],ensure_ascii=True).encode()).hexdigest()
assert cached.get('fingerprint')==fingerprint and cached.get('sha256')=='769ee42e52ad73c67f30d28483e34589ae4dbdb2c4873377d2635657b960c7d2','Changed resources require a new resource revision'
previous_resource=base/'outputs/内容中台完整离线版-v1.1.0/ContentHub-Offline-Resources-v1.1.0.zip'
if not archive.exists() and previous_resource.is_file() and sha(previous_resource)==cached['sha256']:os.link(previous_resource,archive)
if not (archive.exists() and cached.get('fingerprint')==fingerprint and cached.get('sha256')==sha(archive)):
    temporary=archive.with_suffix('.zip.partial');completed=0;last=time.monotonic()
    print(f'COMPRESS_OFFLINE_RESOURCES {len(files)} files {total} bytes',flush=True)
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as zipped:
        for index,path in enumerate(files,1):
            with path.open('rb') as incoming,zipped.open(path.relative_to(source).as_posix(),'w',force_zip64=True) as outgoing:
                for block in iter(lambda:incoming.read(4*1024**2),b''):
                    outgoing.write(block);completed+=len(block)
                    if time.monotonic()-last>=15:
                        print(f'COMPRESS {completed}/{total} bytes; {index}/{len(files)} files',flush=True);last=time.monotonic()
    os.replace(temporary,archive)
    cached={'sha256':sha(archive),'bytes':archive.stat().st_size,'unpacked_bytes':total,'files':len(files),'fingerprint':fingerprint}
    resource_record.write_text(json.dumps(cached,indent=2),encoding='utf-8')
manifest={'format':'contenthub/offline-bundle/v1','version':version,'resource_contract':1,
    'installer':{'name':target.name,'bytes':installer.stat().st_size,'sha256':sha(installer)},
    'resources':{'name':archive.name,'bytes':archive.stat().st_size,'sha256':cached['sha256'],'unpacked_bytes':total,'files':len(files)}}
manifest_path=output/'contenthub-offline-bundle.json';manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('FREEZE_COMPLETE_OFFLINE_INSTALLER',flush=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
    '--name',f'ContentHub-Offline-Setup-v{version}','--distpath',str(output),'--workpath',str(work/'pyinstaller'),'--specpath',str(work),
    '--icon',str(base/'AskFilm/apps/desktop/build/icon.ico'),
    '--add-data',str(manifest_path)+os.pathsep+'.','--add-data',str(base/'AskFilm/scripts/contenthub_offline_probe.py')+os.pathsep+'.',
    str(base/'AskFilm/scripts/contenthub_offline_setup.py')],check=True)
helper=output/f'ContentHub-Offline-Setup-v{version}.exe';layout=work/'layout-test.json';layout.unlink(missing_ok=True)
subprocess.run([str(helper),'--package-dir',str(output),'--self-test',str(layout)],check=True,timeout=45)
assert json.loads(layout.read_text(encoding='utf-8'))['ok']
launcher=output/'开始安装内容中台.exe'
if launcher.exists():launcher.unlink()
os.link(helper,launcher)
guide=f'''内容中台完整离线版 v{version}（编导台＋剪辑台，Windows x64）

1. 将整个 ZIP 解压到一个文件夹，保留所有文件在一起。
2. 双击“开始安装内容中台.exe”，选择模型资源位置（推荐 D/E 盘，位于程序目录之外）。程序安装组件由该向导自动调用，请勿单独运行。
3. 安装器从本包校验并解压全部资源，显示文件、已处理大小、进度、速度及预计剩余时间；随后执行四组模型、浏览器和 FFmpeg 的本机离线自检。
4. 自检通过后自动打开标准程序安装向导，可另选程序安装位置。首次启动无需再下载模型、Python、浏览器或 FFmpeg。
5. 资源约 {total/1024**3:.2f} GB，程序另需约 1 GB；请为原始压缩包、解压与安装合计预留至少 12 GB 空间。

本包包含 SenseVoice Small、中文标点、时间对齐、OCR、Python 与依赖、Playwright 浏览器、FFmpeg 和完整桌面程序。
安装及本地音视频转写无需联网。AI 文案、公开链接解析和检查更新需要联网，按功能填写自己的 API Key 或登录相应账号。
模型资源位置由安装器登记到用户资料目录；用户资料、Key 和项目单独保存。后续程序更新继续复用已安装模型。
本包不含个人资料、历史项目或任何用户的 API 密钥。

如果提示缺少微软运行库，请点击安装器的“微软运行库”，或双击包内 VC_redist.x64.exe 完成微软运行库安装后重试。
重试时保留已经完成并通过校验的资源文件；不要只单独复制某一个 EXE。
'''
(output/'使用说明.txt').write_text(guide,encoding='utf-8-sig')
members=[target,archive,launcher,output/redistributable.name,manifest_path,output/'使用说明.txt']
(output/'SHA256SUMS.txt').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in members),encoding='utf-8')
members.append(output/'SHA256SUMS.txt')
desktop=Path('C:/Users/Administrator/Desktop');outer=desktop/f'内容中台完整离线版-v{version}.zip'
if outer.exists():
    previous_path=work/'package-result.json';previous=json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else {}
    owned='--refresh' in sys.argv and previous.get('path')==str(outer) and previous.get('sha256')==sha(outer)
    if not owned:outer=desktop/f'内容中台完整离线版-v{version}-{datetime.datetime.now():%Y%m%d-%H%M%S}.zip'
temporary=outer.with_suffix('.zip.partial');prefix=f'内容中台完整离线版-v{version}/'
print('PACKAGE_SINGLE_DESKTOP_ZIP',flush=True)
with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_STORED,allowZip64=True) as zipped:
    for path in members:zipped.write(path,prefix+path.name)
with zipfile.ZipFile(temporary) as zipped:
    assert zipped.testzip() is None and len(zipped.namelist())==len(members)
os.replace(temporary,outer)
record={'ok':True,'path':str(outer),'bytes':outer.stat().st_size,'sha256':sha(outer),'version':version,'package_dir':str(output),
    'resources_bytes':total,'resources_archive_bytes':archive.stat().st_size,'files':len(files),'installer':str(launcher),'source_probe':proof,'layout':json.loads(layout.read_text(encoding='utf-8'))}
(work/'package-result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k not in ('source_probe','layout')},ensure_ascii=True),flush=True)
