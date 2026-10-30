"""Publishable pieces keep the resource revision independent of app releases."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tempfile,zipfile

base=Path(__file__).resolve().parents[2];version='1.1.1';revision='r1';chunk=90*1024**2
output=Path(tempfile.gettempdir())/f'contenthub-offline-distribution-v{version}';output.mkdir(parents=True,exist_ok=True)
work=base/'.cache/contenthub-offline-cloud-build';work.mkdir(parents=True,exist_ok=True)
source=base/'outputs/内容中台完整离线版-v1.1.0'
import tkinter
tkinter.Tcl().eval('info library') # Fail before packaging if the build environment hides Tcl/Tk.

def sha(path):
    with path.open('rb') as incoming:return hashlib.file_digest(incoming,'sha256').hexdigest()

resource=json.loads((base/'.cache/contenthub-offline-full-build/resources.json').read_text(encoding='utf-8'))
archive=source/'ContentHub-Offline-Resources-v1.1.0.zip'
assert archive.stat().st_size==resource['bytes'] and sha(archive)==resource['sha256']
assert resource['sha256']=='769ee42e52ad73c67f30d28483e34589ae4dbdb2c4873377d2635657b960c7d2','Changed resources require a new resource revision'
parts=[];files=[];whole=hashlib.sha256()
with archive.open('rb') as incoming:
    for index,data in enumerate(iter(lambda:incoming.read(chunk),b''),1):
        name=f'ContentHub-Resources-{revision}-{index:02}.zip';entry=f'resources-{revision}.part{index:03}'
        target=output/name;digest=hashlib.sha256(data).hexdigest();whole.update(data);valid=False
        existing=Path(tempfile.gettempdir())/'contenthub-offline-distribution-v1.1.0'/name
        if not target.exists() and existing.is_file():os.link(existing,target)
        if target.is_file():
            with zipfile.ZipFile(target) as zipped:
                valid=zipped.namelist()==[entry] and zipped.getinfo(entry).file_size==len(data) and hashlib.sha256(zipped.read(entry)).hexdigest()==digest
        if not valid:
            temporary=target.with_suffix('.zip.partial')
            info=zipfile.ZipInfo(entry,date_time=(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_STORED
            with zipfile.ZipFile(temporary,'w') as zipped:zipped.writestr(info,data)
            os.replace(temporary,target)
        parts.append({'name':name,'entry':entry,'bytes':len(data),'sha256':digest});files.append(target)
        print(f'RESOURCE_{revision.upper()} {index} {name} {len(data)}',flush=True)
assert whole.hexdigest()==resource['sha256'] and len(parts)==25
program_source=base/f'outputs/内容中台安装包-v{version}/ContentHub-Setup-v{version}-x64.exe'
expected=json.loads((base/'.cache/contenthub-111-publication.json').read_text(encoding='utf-8'))['assets'][program_source.name]
assert program_source.stat().st_size==expected['bytes'] and sha(program_source)==expected['sha256']
program={'name':program_source.name,'bytes':expected['bytes'],'sha256':expected['sha256'],'parts':[]}
with program_source.open('rb') as incoming:
    for index,data in enumerate(iter(lambda:incoming.read(chunk),b''),1):
        name=f'ContentHub-v{version}-Install-{index:02}.zip';entry=f'installer.part{index:03}';target=output/name
        info=zipfile.ZipInfo(entry,date_time=(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_STORED
        with zipfile.ZipFile(target,'w') as zipped:zipped.writestr(info,data)
        program['parts'].append({'name':name,'entry':entry,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()});files.append(target)
assert len(program['parts'])==6
resources={'name':f'ContentHub-Resources-{revision}.zip',**{key:resource[key] for key in ('bytes','sha256')},'parts':parts}
cloud={'format':'contenthub/offline-cloud/v1','version':version,'resource_revision':revision,'resource_contract':1,'program':program,'resources':resources}
(output/'contenthub-offline-cloud.json').write_text(json.dumps(cloud,ensure_ascii=False,indent=2),encoding='utf-8')
bundle={'format':'contenthub/offline-bundle/v1','version':version,'resource_contract':1,
    'installer':{key:program[key] for key in ('name','bytes','sha256')},
    'resources':{key:resources[key] for key in ('name','bytes','sha256')}|{key:resource[key] for key in ('unpacked_bytes','files')}}
(output/'contenthub-offline-bundle.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')
urls='https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/'
catalog={'format':'contenthub/resources/v1','revision':revision,'resource_contract':1,'minimum_desktop_version':'1.1.0',
    'archive':{key:resources[key] for key in ('name','bytes','sha256')},'unpacked_bytes':resource['unpacked_bytes'],'files':resource['files'],
    'models':['SenseVoice Small','Chinese punctuation','Forced alignment','OCR'],
    'parts':[{**part,'url':urls+part['name'],'zip_bytes':(output/part['name']).stat().st_size,'zip_sha256':sha(output/part['name'])} for part in parts]}
(output/f'contenthub-resources-{revision}.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
print('FREEZE_OFFLINE_DISTRIBUTION_INSTALLER',flush=True)
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx','--name',f'ContentHub-Offline-Install-v{version}',
    '--distpath',str(output),'--workpath',str(work/'pyinstaller'),'--specpath',str(work),'--icon',str(base/'AskFilm/apps/desktop/build/icon.ico')]
for data in (output/'contenthub-offline-cloud.json',output/'contenthub-offline-bundle.json',base/'AskFilm/scripts/contenthub_offline_probe.py'):
    command+=['--add-data',str(data)+os.pathsep+'.']
subprocess.run(command+[str(base/'AskFilm/scripts/contenthub_offline_cloud_setup.py')],check=True)
helper=output/f'ContentHub-Offline-Install-v{version}.exe';files.append(helper)
layout=work/'layout-test.json';layout.unlink(missing_ok=True)
subprocess.run([str(helper),'--self-test',str(layout)],check=True,timeout=45)
assert json.loads(layout.read_text(encoding='utf-8'))['ok']
vc=output/'VC_redist.x64.exe'
if not vc.exists():shutil.copyfile(source/vc.name,vc)
assert sha(vc)==sha(source/vc.name);files.append(vc)
guide=f'''内容中台完整离线版 v{version}：编导台＋剪辑台（Windows x64）

新电脑首次安装：
1. 下载 ContentHub-Offline-Install-v{version}.exe。
2. 下载 ContentHub-v{version}-Install-01.zip 至 -06.zip，共 6 个程序分包。
3. 下载 ContentHub-Resources-{revision}-01.zip 至 -25.zip，共 25 个独立资源分包。
4. 把上述安装器和全部 31 个 ZIP 放在同一文件夹，无需解压分包。
5. 双击 ContentHub-Offline-Install-v{version}.exe，选择模型资源位置（建议 D/E 盘，位于程序目录外）。安装器先校验和自动合并，再离线解压、校验四组模型、浏览器和 FFmpeg；界面显示文件、处理进度、速度及剩余时间。
6. 自检通过后自动进入标准程序安装向导，再选择程序安装位置。安装和本地音视频转写不需要联网或翻墙。

下载合计约 2.7 GB，资源解压约 4.26 GB，程序另需约 1 GB；请为分包、自动合并和安装合计预留至少 14 GB 空间。请关闭并行运行的安装器，避免多个安装器同时写入同一资源目录。
如果提示缺少微软运行库，请一并下载 VC_redist.x64.exe，在安装器内点击“微软运行库”或手动安装后重试；已校验资源会复用。
不要单独运行合并产生的程序安装组件；应始终从 Offline-Install 安装器进入，确保模型资源完成登记。

已有版本更新：在客户端设置中点击检查更新，下载并更新程序；失败回滚保留资料、Key 和已登记的模型目录。无需重新下载这 25 个资源分包。
程序版本与资源版本分别管理：本次程序为 {version}，本地模型及运行环境为 {revision}（资源契约 1）。以后只改程序时继续引用同一份 {revision} 资源；只有新增、更换模型或不兼容的运行资源才发布新的资源修订。已下载并通过校验的分包和合并文件可以继续复用。
旧的 ContentHub-Install-v1.1.0.exe 是仅程序分包安装器；新电脑完整离线安装请使用带 Offline 的安装器，并下载全部资源分包。

本包包含 SenseVoice Small、中文标点、时间对齐、OCR、Python/依赖、Playwright 浏览器、FFmpeg，以及完整桌面程序。不包含个人资料、项目或任何用户 API Key。
AI 文案、公开链接解析及检查更新仍需要联网，按功能填写自己的 API Key 或登录相应账号。客户端程序更新不会自动把模型全部重下。
'''
readme=output/'00-READ-ME-OFFLINE.txt';readme.write_text(guide,encoding='utf-8-sig');files.append(readme)
catalog_path=output/f'contenthub-resources-{revision}.json';files.append(catalog_path)
checksums=output/'SHA256SUMS-OFFLINE.txt';checksums.write_text(''.join(sha(path)+'  '+path.name+'\n' for path in files),encoding='utf-8');files.append(checksums)
record={'ok':True,'version':version,'resource_revision':revision,'directory':str(output),'helper':str(helper),
    'program_pieces':6,'resource_pieces':25,'resources_sha256':resource['sha256'],'program_sha256':program['sha256'],
    'files':[{'name':path.name,'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)} for path in files]}
(base/'.cache/contenthub-offline-publish-record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in record.items() if key!='files'},ensure_ascii=True),flush=True)
