"""Build a Windows x64 GUI bootstrapper with the verified versioned Skill ZIP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist');args=parser.parse_args()
    if os.name!='nt':raise ValueError('EXE 必须在 Windows x64 Python 上构建。')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/build_release.py'),'--output',str(out)],check=True)
    version=(ROOT/'VERSION').read_text().strip();package=out/f'video-copy-studio-v{version}.zip'
    work=ROOT/'dist/exe-build';payload=work/'payload';payload.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(package,payload/'payload.zip');shutil.copyfile(package.with_suffix('.zip.sha256'),payload/'payload.zip.sha256')
    shutil.copyfile(ROOT/'VERSION',payload/'VERSION');shutil.copyfile(ROOT/'install.ps1',payload/'install.ps1')
    name='VideoCopyStudio-Setup-v'+version
    version_file=work/'version-info.txt'
    numeric=tuple(map(int,version.split('.')))+(0,)
    version_file.write_text('VSVersionInfo(ffi=FixedFileInfo(filevers='+repr(numeric)+', prodvers='+repr(numeric)+', mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), kids=[StringFileInfo([StringTable("040904b0", [StringStruct("FileDescription", "Video Copy Studio Setup and Update"), StringStruct("ProductName", "Video Copy Studio"), StringStruct("FileVersion", "'+version+'"), StringStruct("ProductVersion", "'+version+'")])]), VarFileInfo([VarStruct("Translation", [1033,1200])])])',encoding='utf-8')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
        '--name',name,'--distpath',str(out),'--workpath',str(work/'work'),'--specpath',str(work),
        '--paths',str(ROOT/'assets/studio'),'--version-file',str(version_file)]
    for filename in ('VERSION','install.ps1','payload.zip','payload.zip.sha256'):
        command+=['--add-data',str(payload/filename)+os.pathsep+'.']
    command+=[str(ROOT/'scripts/windows_manager.py')]
    subprocess.run(command,check=True)
    exe=out/(name+'.exe');digest=hashlib.sha256(exe.read_bytes()).hexdigest()
    exe.with_suffix('.exe.sha256').write_text(digest+'  '+exe.name+'\n',encoding='ascii')
    print(json.dumps({'exe':str(exe),'bytes':exe.stat().st_size,'sha256':digest},ensure_ascii=False))


if __name__=='__main__':main()
