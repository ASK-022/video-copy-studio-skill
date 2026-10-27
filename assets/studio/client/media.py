"""Local link import. Uses public media only, with an isolated browser fallback."""
import asyncio
import importlib.util
import ipaddress
import os
from pathlib import Path
import re
import socket
import sys
from urllib.parse import urlparse

import httpx

MAX_BYTES = 500 * 1024 * 1024
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'


def extract_url(text):
    match = re.search(r'https?://[^\s<>"\u3000]+', text)
    if not match:
        raise ValueError('请粘贴 http 或 https 视频链接，也可以直接粘贴完整分享文案。')
    return match.group(0).rstrip('。，、；！）》】」』,.!?;')


def safe_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('只支持不含账号密码的 http/https 公网链接。')
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme=='https' else 80))
    except OSError as exc:
        raise ValueError('链接域名无法解析，请检查网络。') from exc
    # The local gateway uses 198.18/15 synthetic DNS for public names.
    # Permit that mapping for domain names, never a user-supplied literal address.
    try:
        ipaddress.ip_address(parsed.hostname)
        literal = True
    except ValueError:
        literal = False
    fake_dns = ipaddress.ip_network('198.18.0.0/15')
    if any(not ipaddress.ip_address(x[4][0]).is_global and not (
        not literal and ipaddress.ip_address(x[4][0]) in fake_dns) for x in addresses):
        raise ValueError('视频链接必须是公网地址。')
    return url


def stream_download(url, target, referer='', progress=lambda s:None):
    headers = {'User-Agent':UA}
    if referer:
        headers['Referer'] = referer
    with httpx.Client(timeout=45, trust_env=False) as client:
        for _ in range(8):
            safe_url(url)
            with client.stream('GET', url, headers=headers) as response:
                if response.is_redirect:
                    url = str(response.url.join(response.headers['location']))
                    continue
                response.raise_for_status()
                content_type = response.headers.get('content-type','')
                if 'text/html' in content_type or 'json' in content_type:
                    raise ValueError('链接返回的是网页，未取得可下载的视频。')
                if int(response.headers.get('content-length','0')) > MAX_BYTES:
                    raise ValueError('视频超过 500 MB，请下载较短版本后导入。')
                size = 0
                with target.open('wb') as output:
                    for chunk in response.iter_bytes(1024*256):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError('视频超过 500 MB。')
                        output.write(chunk)
                if size < 100:
                    raise ValueError('下载内容为空或无效。')
                return target
    raise ValueError('链接重定向次数过多。')


def public_douyin(url, target, progress):
    """Use a new ephemeral Chromium session; never read personal browser cookies."""
    from playwright.sync_api import sync_playwright
    progress('正在通过公开播放页读取视频（不读取个人浏览器登录状态）…')
    candidates = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True,
                                    args=['--mute-audio','--autoplay-policy=no-user-gesture-required'])
        try:
            context = browser.new_context(user_agent=UA, locale='zh-CN')
            page = context.new_page()
            def capture(request):
                link = request.url
                if ('douyinvod.com' in urlparse(link).hostname if urlparse(link).hostname else False) and (
                    'mime_type=audio' in link or 'mime_type=video' in link or '.mp4' in link or '.m4a' in link):
                    if link not in candidates:
                        candidates.append(link)
            page.on('request', capture)
            page.goto(url, wait_until='domcontentloaded', timeout=35000)
            # Short links land on the mobile page. Desktop public playback exposes A/V URLs.
            match = re.search(r'/(?:video|share/video)/(\d+)', page.url)
            if not candidates and match:
                page.goto('https://www.douyin.com/video/'+match.group(1), wait_until='domcontentloaded', timeout=35000)
            if page.locator('video').count():
                page.locator('video').first.evaluate('(video) => { video.muted = false; video.play().catch(() => {}); }')
            for _ in range(20):
                page.wait_for_timeout(1000)
                # Douyin often requests video first, with the original audio arriving later.
                if any('mime_type=audio' in link for link in candidates):
                    break
            if not candidates:
                raise ValueError('抖音公开页未返回音视频地址，可能需要验证或视频已不可访问。请下载视频后本地导入。')
            # Audio alone is sufficient for local transcription and avoids unnecessarily large downloads.
            candidates.sort(key=lambda x: 0 if 'mime_type=audio' in x else 1)
            for candidate in candidates[:4]:
                try:
                    downloaded=stream_download(candidate, target, 'https://www.douyin.com/', progress)
                    import subprocess, json
                    probe=Path(os.environ.get('FFMPEG_PATH','E:/openfilm/resources/runtime/ffmpeg/ffmpeg.exe')).with_name('ffprobe.exe')
                    check=subprocess.run([str(probe),'-v','error','-show_entries','stream=codec_type','-of','json',str(downloaded)],
                                         capture_output=True,text=True,timeout=20,
                                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if any(x.get('codec_type')=='audio' for x in json.loads(check.stdout).get('streams',[])):
                        return downloaded
                except (ValueError, httpx.HTTPError):
                    continue
            raise ValueError('已找到公开播放地址，但下载被平台拒绝。请下载视频后本地导入。')
        finally:
            browser.close()


def import_link(share_text, directory, progress=lambda s:None):
    url = safe_url(extract_url(share_text))
    # The upstream service validates the filename extension before FFmpeg probes it.
    # MP4 also supports the audio-only AAC track returned by Douyin.
    target = directory / 'source.mp4'
    host = urlparse(url).hostname
    path = urlparse(url).path.lower()
    if path.endswith(('.mp4','.mov','.mkv','.webm','.m4a','.mp3','.wav','.aac')) or 'douyinvod.com' in host:
        progress('正在下载媒体文件…')
        return stream_download(url,target,progress=progress)
    progress('正在解析视频链接…')
    # Reuse the installed parser skill, in its own dependency environment.
    parser = Path.home()/'.codex/skills/video-parse-transcribe/scripts/video_parse_transcribe.py'
    parser_python = Path(__file__).resolve().parents[1]/'.venv/Scripts/python.exe'
    if parser.exists() and parser_python.exists():
        import subprocess
        import json
        try:
            run = subprocess.run([str(parser_python),str(parser),'--url',url,'--mode','parse'],
                                 capture_output=True,encoding='utf-8',errors='replace',timeout=45,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if run.returncode == 0:
                info = json.loads(run.stdout)
                if info.get('video_url'):
                    return stream_download(info['video_url'],target,url,progress)
        except (ValueError, httpx.HTTPError, subprocess.TimeoutExpired):
            pass
    if host == 'douyin.com' or host.endswith('.douyin.com') or host.endswith('.iesdouyin.com'):
        try:
            import subprocess
            progress('正在通过独立公开播放页读取音轨…')
            # Uvicorn on Windows can select a loop incompatible with browser subprocesses.
            # A clean subprocess keeps the browser event loop separate from the API server.
            root=Path(__file__).resolve().parents[1]
            with (directory/'browser-import.log').open('w',encoding='utf-8') as output:
                result=subprocess.run([sys.executable,'-m','client.browser_import',url,str(target.resolve())],
                                      cwd=root,stdout=output,stderr=output,timeout=240,
                                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode or not target.is_file():
                raise ValueError('公开播放页未返回可用音轨。')
            return target
        except Exception as exc:
            raise ValueError('抖音公开链接导入失败。平台可能要求验证，请下载视频后本地导入。') from exc
    import yt_dlp
    try:
        class QuietLog:
            def debug(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg): pass
        with yt_dlp.YoutubeDL({'outtmpl':str(directory/'source.%(ext)s'),'format':'bestaudio/best',
                              'noplaylist':True,'max_filesize':MAX_BYTES,'socket_timeout':20,
                              'retries':1,'quiet':True,'logger':QuietLog(),'proxy':'',
                              'ffmpeg_location':os.environ.get('FFMPEG_PATH','')}) as downloader:
            info = downloader.extract_info(url,download=True)
            result = Path(downloader.prepare_filename(info))
        if result.is_file() and result.stat().st_size <= MAX_BYTES:
            return result
    except Exception as exc:
        raise ValueError('该链接暂时无法下载，可能受平台限制、需要登录或链接已失效。请下载视频后导入。') from exc
    raise ValueError('未取得媒体文件，请尝试本地导入。')
