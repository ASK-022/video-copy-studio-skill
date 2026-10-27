"""Local sampled frames/OCR and real ASR timestamps. No media leaves the machine here."""
import base64
from difflib import SequenceMatcher
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess


def fingerprint(media):
    stat=media.stat()
    return hashlib.sha256(f'{media.name}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()


def plain(text):
    return re.sub(r'\s+','',text)


def clock(seconds):
    if seconds is None:return '时间未对齐'
    value=max(0,int(seconds));return f'{value//60:02d}:{value%60:02d}'


def timeline(result):
    rows=[]
    for s in result.get('segments') or []:
        start=s.get('start',s.get('start_time'));end=s.get('end',s.get('end_time'))
        if isinstance(start,(int,float)) and isinstance(end,(int,float)) and 0<=start<end:
            rows.append({'start':round(start,2),'end':round(end,2),'text':s.get('text','')})
    return rows


def segment_times(structure, rows, corrected):
    """Map corrected text back to measured ASR spans; never allocate fake timestamps."""
    raw=''.join(plain(r['text']) for r in rows); target=plain(corrected)
    matches=SequenceMatcher(None,raw,target,autojunk=False).get_matching_blocks()
    spans=[];offset=0
    for row in rows:
        length=len(plain(row['text']));spans.append((offset,offset+length,row));offset+=length
    out=[];offset=0
    for s in structure:
        size=len(plain(s['text']));hits=[];matched=0
        for a,b,n in matches:
            lo=max(offset,b);hi=min(offset+size,b+n)
            if hi>lo:
                matched+=hi-lo;first=a+lo-b;last=a+hi-b
                hits.extend(row for start,end,row in spans if start<last and end>first)
        out.append({**s,'start':min((r['start'] for r in hits),default=None) if matched>=size*.5 else None,
                    'end':max((r['end'] for r in hits),default=None) if matched>=size*.5 else None})
        offset+=size
    return out


def local_frames(media,folder,duration,ffmpeg,notify=lambda _:None):
    frames_dir=folder/'frames';frames_dir.mkdir(exist_ok=True)
    # One capture per 3 seconds for short clips; bounded to 60 samples for long clips.
    step=max(3,math.ceil(duration/60));count=min(60,max(1,math.ceil(duration/step)))
    from rapidocr_onnxruntime import RapidOCR
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
    frames=[];tag=fingerprint(media)[:12]
    for index in range(count):
        second=min(index*step+.2,max(.0,duration-.1));path=frames_dir/f'{tag}-{index:03d}.jpg'
        if not path.exists():
            proc=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-ss',str(second),'-i',str(media),
                '-frames:v','1','-vf','scale=720:720:force_original_aspect_ratio=decrease','-q:v','3','-y',str(path)],
                capture_output=True,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if proc.returncode or not path.exists():continue # Audio-only import is supported.
        notify(f'本机画面文字识别 {index+1} / {count}…')
        result,_=engine(str(path))
        lines=[{'text':r[1],'confidence':round(float(r[2]),3)} for r in result or [] if r[2]>=.60]
        frames.append({'id':index+1,'time':round(second,2),'file':path.name,'ocr':lines})
    return {'frames':frames,'sample_interval':step,'ocr_engine':'RapidOCR / PP-OCR','visual_source':'local',
            'limitations':['画面按间隔抽样，可能遗漏快速闪过的文字；OCR 结果需核对。',
                            '本机 OCR 只识别屏幕文字；人物、动作与运镜未做视觉识别。']}


def image_payloads(folder,frames,limit=12):
    if not frames:return [],[]
    picked=[frames[i] for i in sorted(set(round(i*(len(frames)-1)/max(1,min(limit,len(frames))-1)) for i in range(min(limit,len(frames)))))]
    return picked,['data:image/jpeg;base64,'+base64.b64encode((folder/'frames'/f['file']).read_bytes()).decode() for f in picked]


def screen_groups(frames):
    seen={};groups=[]
    for frame in frames:
        for line in frame.get('ocr',[]):
            text=line['text'].strip();key=plain(text)
            if not key or key in seen:continue
            seen[key]=True
            groups.append({'time':frame['time'],'text':text,'frame_id':frame['id'],'confidence':line['confidence']})
    return groups
