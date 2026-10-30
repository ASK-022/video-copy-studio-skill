"""Build and smoke-test the frozen Content Hub resource preparation helper."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile

base=Path(__file__).resolve().parents[2]
work=base/'.cache/contenthub-setup-build'
work.mkdir(parents=True,exist_ok=True)
version=(base/'skills/video-copy-studio/VERSION').read_text(encoding='utf-8').strip()
source=base/f'outputs/客户端更新-v{version}/video-copy-studio-v{version}.zip'
payload=work/'payload.zip'
# Overlay only reviewed setup code; all embedded third-party assets remain pinned.
progress_source=base/'AskFilm/scripts/contenthub_progress.py'
published=base/'.cache/publish/video-copy-studio/scripts'
overlays={f'video-copy-studio/scripts/{name}':published/name for name in ('bootstrap.py','download_sources.py','browser_setup.py')}
overlays['video-copy-studio/scripts/contenthub_progress.py']=progress_source
with zipfile.ZipFile(source) as original,zipfile.ZipFile(payload,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as target:
    seen=set()
    for entry in original.infolist():
        target.writestr(entry,overlays[entry.filename].read_bytes() if entry.filename in overlays else original.read(entry));seen.add(entry.filename)
    for name,path in overlays.items():
        if name not in seen:target.writestr(name,path.read_bytes())
manifest=work/'resource-payload.json'
manifest.write_text(json.dumps({'version':version,'sha256':hashlib.sha256(payload.read_bytes()).hexdigest()}),encoding='utf-8')
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
    '--name','ContentHub-Resources-Setup','--distpath',str(work),'--workpath',str(work/'work'),'--specpath',str(work),
    '--icon',str(base/'AskFilm/apps/desktop/build/icon.ico'),
    '--add-data',str(manifest)+os.pathsep+'.','--add-data',str(payload)+os.pathsep+'.',
    str(base/'AskFilm/scripts/contenthub-resources-setup.py')],check=True)
result=work/'helper-self-test.json'
result.unlink(missing_ok=True)
subprocess.run([str(work/'ContentHub-Resources-Setup.exe'),'--self-test',str(result)],check=True,timeout=30)
assert json.loads(result.read_text(encoding='utf-8'))['ok'],'Frozen helper failed its resource validation'
print('CONTENTHUB_RESOURCE_HELPER_VERIFIED')
