"""Build the stable launcher/update worker; the publisher private key is never bundled."""
from pathlib import Path
import json,os,subprocess,sys
base=Path(__file__).resolve().parents[2];work=base/'.cache/contenthub-launcher-build';work.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
    '--name','ContentHub','--distpath',str(work),'--workpath',str(work/'work'),'--specpath',str(work),
    '--icon',str(base/'AskFilm/apps/desktop/build/icon.ico'),
    '--add-data',str(base/'AskFilm/apps/desktop/src/contenthub-update-public.json')+os.pathsep+'.',str(base/'AskFilm/scripts/contenthub_update.py')],check=True)
result=work/'self-test.json';result.unlink(missing_ok=True)
subprocess.run([str(work/'ContentHub.exe'),'--self-test',str(result)],check=True,timeout=30)
assert json.loads(result.read_text())['ok'];print('CONTENTHUB_LAUNCHER_VERIFIED')
