"""Public one-shot GitHub artifact assembler. Never executes the Windows installer or publishes a release."""
from pathlib import Path, PurePosixPath
from concurrent.futures import ThreadPoolExecutor
import os, json, hashlib, urllib.request, time, re, subprocess, threading

REPO = 'ASK-022/video-copy-studio-skill'
VERSION = '1.3.0'

def need(ok, why):
    if not ok: raise RuntimeError(why)
def sha(path):
    with Path(path).open('rb') as s: return hashlib.file_digest(s, 'sha256').hexdigest()
def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=900)
    need(p.returncode == 0, (p.stderr or p.stdout)[-1500:].replace(os.environ.get('GH_TOKEN', 'no-token'), '[hidden]'))
    return p.stdout
def api(path): return json.loads(run(['gh', 'api', 'repos/' + REPO + path]))
def safe_name(value): return bool(re.fullmatch(r'[A-Za-z0-9_.-]+', value)) and value not in ('.', '..')
def safe_path(value):
    p = PurePosixPath(value)
    return not p.is_absolute() and '..' not in p.parts and value.startswith(('releases/contenthub/', 'installer-cache/'))

def assemble(parts, destination, expected_bytes, expected_sha):
    made = 0; digest = hashlib.sha256()
    with Path(destination).open('wb') as target:
        for part in parts:
            with Path(part).open('rb') as source:
                while block := source.read(1024 * 1024): target.write(block); digest.update(block); made += len(block)
    need(made == expected_bytes and digest.hexdigest() == expected_sha, 'Assembled installer differs from the verified candidate')

def main():
    need(os.environ.get('GITHUB_REPOSITORY') == REPO, 'Wrong repository')
    commit = os.environ['GITHUB_SHA']; need(re.fullmatch('[0-9a-f]{40}', commit), 'Invalid immutable commit')
    prefix = 'releases/contenthub/staging/1.3.0/'
    base = 'https://raw.githubusercontent.com/' + REPO + '/' + commit + '/'
    plan_raw = urllib.request.urlopen(base + prefix + 'plan.json', timeout=60).read()
    need(hashlib.sha256(plan_raw).hexdigest() == os.environ['CONTENTHUB_PLAN_SHA'], 'Public plan changed')
    plan = json.loads(plan_raw)
    need(plan['version'] == VERSION and plan['repository'] == REPO, 'Wrong publication target')
    need(len(plan['assets']) <= 250 and len(plan['installer_parts']) <= 150, 'Unexpected artifact count')
    release_id = int(plan['release_id'])
    def owned():
        release = api('/releases/' + str(release_id))
        need(release['draft'] and release['tag_name'] == plan['upload_tag'] and plan['source_sha256'] in release['body']
             and plan['installer']['sha256'] in release['body'], 'Owned draft changed; never publish or clobber')
        return release
    owned()
    work = Path('release-inputs').resolve(); work.mkdir(exist_ok=False)
    files = {}
    rows = [a for a in plan['assets'] if a['name'] != plan['installer']['name']] + plan['installer_parts']
    def download(row):
        need(safe_name(row['name']) and safe_path(row['git_path']), 'Unsafe public artifact path')
        need(0 < row['bytes'] <= 7 * 1024 * 1024, 'Unexpected part size')
        to = work / row['name']
        for attempt in range(5):
            try:
                count = 0; digest = hashlib.sha256()
                with urllib.request.urlopen(base + row['git_path'], timeout=120) as response, to.open('wb') as target:
                    while block := response.read(1024 * 1024):
                        count += len(block); need(count <= row['bytes'], 'Oversized public artifact'); digest.update(block); target.write(block)
                need(count == row['bytes'] and digest.hexdigest() == row['sha256'], 'Public artifact checksum mismatch')
                return row['name'], to
            except Exception:
                if attempt == 4: raise
                time.sleep(2 ** attempt)
    with ThreadPoolExecutor(max_workers=8) as pool: files.update(pool.map(download, rows))
    installer = plan['installer']; destination = work / installer['name']
    need(safe_name(installer['name']) and 0 < installer['bytes'] < 2 * 1024 ** 3, 'Unexpected installer')
    assemble([files[p['name']] for p in plan['installer_parts']], destination, installer['bytes'], installer['sha256'])
    files[installer['name']] = destination
    last_start = 0; lock = threading.Lock()
    def upload(asset):
        nonlocal last_start
        file = files[asset['name']]
        need(file.stat().st_size == asset['bytes'] and sha(file) == asset['sha256'], 'Upload bytes changed')
        release = owned(); existing = next((a for a in release['assets'] if a['name'] == asset['name']), None)
        if not existing:
            with lock:
                time.sleep(max(0, 1.1 - (time.monotonic() - last_start))); last_start = time.monotonic()
            try: run(['gh', 'release', 'upload', plan['upload_tag'], '--repo', REPO, str(file)])
            except Exception:
                release = owned(); existing = next((a for a in release['assets'] if a['name'] == asset['name']), None)
                if not existing: raise
        release = owned(); existing = next(a for a in release['assets'] if a['name'] == asset['name'])
        need(existing['size'] == asset['bytes'] and existing.get('digest') == 'sha256:' + asset['sha256'], 'Native upload checksum mismatch')
        print('NATIVE_ASSET_ACK ' + asset['name'], flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool: list(pool.map(upload, plan['assets']))
    release = owned(); actual = {a['name']: a for a in release['assets']}
    need(set(actual) == {a['name'] for a in plan['assets']}, 'Unexpected draft asset set')
    for a in plan['assets']: need(actual[a['name']]['size'] == a['bytes'] and actual[a['name']].get('digest') == 'sha256:' + a['sha256'], 'Final artifact mismatch')
    print(json.dumps({'ok': True, 'version': VERSION, 'source_sha256': plan['source_sha256'], 'installer_sha256': installer['sha256'], 'native_assets': len(actual), 'published': False}), flush=True)

if __name__ == '__main__': main()
