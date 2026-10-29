from pathlib import Path
import hashlib,json,os,subprocess,sys,zipfile
base=Path(__file__).resolve().parents[2];version='1.1.0';release=base/f'outputs/内容中台安装包-v{version}';installer=release/f'ContentHub-Setup-v{version}-x64.exe'
out=release/'蓝奏云分包';out.mkdir(exist_ok=True);parts=[];whole=hashlib.sha256()
with installer.open('rb') as source:
 index=1
 while block:=source.read(90*1024**2):
  name=f'ContentHub-v{version}-Install-{index:02d}.zip';entry=f'installer.part{index:03d}'
  with zipfile.ZipFile(out/name,'w',compression=zipfile.ZIP_STORED) as archive:archive.writestr(entry,block)
  parts.append({'name':name,'entry':entry,'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest()});whole.update(block);index+=1
manifest={'version':version,'installer':installer.name,'bytes':installer.stat().st_size,'sha256':whole.hexdigest(),'parts':parts}
work=base/'.cache/contenthub-cloud-setup-build';work.mkdir(exist_ok=True);path=work/'setup-parts.json';path.write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx','--name',f'ContentHub-Install-v{version}',
 '--distpath',str(out),'--workpath',str(work/'work'),'--specpath',str(work),'--icon',str(base/'AskFilm/apps/desktop/build/icon.ico'),'--add-data',str(path)+os.pathsep+'.',str(base/'AskFilm/scripts/contenthub_download_setup.py')],check=True)
(out/'下载与安装.txt').write_text(f'内容中台完整桌面版 v{version}\n\n下载本文件夹全部 {len(parts)} 个 ZIP 分包与 ContentHub-Install-v{version}.exe 到同一文件夹，然后双击安装助手。无需解压或手动拼接；助手逐包校验并重组标准安装器，自动打开可选择安装目录的安装向导。需约 1.2 GB 临时空间用于分包与安装器，程序和首次转写资源还需额外磁盘空间。\n\n本包包含编导台与剪辑台，支持检查更新、更新并重启和失败回滚；资料与 Key 在独立用户目录保存，原有模型直接复用。没有模型时，首次使用按客户端提示下载本地转写资源。\n\n软件含 AI 辅助开发代码。完整安装步骤与版本说明见 GitHub contenthub-v1.1.0 发布页。\n',encoding='utf-8')
print('CLOUD_INSTALLER_PARTS_READY '+str(len(parts)))
