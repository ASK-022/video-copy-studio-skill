"""Read-only local inspection. Results are suggestions; no editing commands exist here."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading

from client.evidence import fingerprint, clock

VERSION=1


@dataclass(frozen=True)
class Options:
    silence_db:float=-35
    silence_seconds:float=.6
    repeat_similarity:float=88
    scene_threshold:float=3
    min_scene_seconds:float=.5


def marker_id(kind,*values):
    return kind+'-'+hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()[:16]


def parse_silences(log,duration,minimum):
    result=[];start=None
    for name,value in re.findall(r'silence_(start|end):\s*(-?\d+(?:\.\d+)?)',log):
        second=min(duration,max(0,float(value)))
        if name=='start':start=second
        elif start is not None:
            if second-start>=minimum-.025:result.append((start,second))
            start=None
    if start is not None and duration-start>=minimum-.025:result.append((start,duration))
    return [{'id':marker_id('silence',round(a,3),round(b,3)),'kind':'silence','start':round(a,3),'end':round(b,3),
             'duration':round(b-a,3),'reason':'音量持续低于设定阈值，不等于没有人声。',
             'suggestion':'对照口播、情绪停顿与画面，确认是否需要保留；当前保留原片。'} for a,b in result]


def detect_silences(media,ffmpeg,duration,options):
    response=subprocess.run([str(ffmpeg),'-hide_banner','-nostats','-i',str(media),'-vn','-af',
        f'silencedetect=noise={options.silence_db}dB:d={options.silence_seconds}','-f','null','-'],
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if response.returncode:raise RuntimeError('音频检测未完成，请检查原文件音轨后重试。')
    return parse_silences(response.stderr,duration,options.silence_seconds)


def canonical(text):return re.sub(r'[\W_]+','',text).casefold()


def detect_repeats(rows,threshold=88):
    from rapidfuzz import fuzz,process
    # Combine up to three short ASR sentences so segmentation differences do not
    # hide a repeated utterance. All endpoints remain measured audio endpoints.
    windows=[]
    for i,row in enumerate(rows):
        for width in range(1,4):
            group=rows[i:i+width]
            if len(group)!=width:break
            if any(b['start']-a['end']>1.5 for a,b in zip(group,group[1:])):break
            text=''.join(s['text'] for s in group);key=canonical(text)
            if len(key)>140 or group[-1]['end']-row['start']>22:break
            if len(key)>=10:windows.append({'start':row['start'],'end':group[-1]['end'],'text':text,'key':key})
    candidates=[]
    for i,current in enumerate(windows):
        choices={j:w['key'] for j,w in enumerate(windows[:i]) if w['end']<=current['start']-.05
                 and min(len(w['key']),len(current['key']))/max(len(w['key']),len(current['key']))>=.7}
        for _,score,index in process.extract(current['key'],choices,scorer=fuzz.ratio,score_cutoff=threshold,limit=3):
            candidates.append((score,len(current['key']),windows[index],current))
    def overlap(a,b):
        return max(0,min(a['end'],b['end'])-max(a['start'],b['start']))/max(.01,min(a['end']-a['start'],b['end']-b['start']))
    selected=[]
    for score,_,original,repeated in sorted(candidates,key=lambda c:(-c[0],-c[1],c[3]['start'])):
        if any(overlap(original,s['original'])>.5 and overlap(repeated,s['repeated'])>.5 for s in selected):continue
        selected.append({'id':marker_id('repeat',original['start'],original['end'],repeated['start'],repeated['end']),
            'kind':'repeat','start':repeated['start'],'end':repeated['end'],'similarity':round(score,1),
            'original':{k:v for k,v in original.items() if k!='key'},'repeated':{k:v for k,v in repeated.items() if k!='key'},
            'reason':'转写文字相似，可能是重复强调、重说或相似表达，尚未判断口误。',
            'suggestion':'对照两处原声及上下文；若承担不同段落功能，继续保留。'})
    selected.sort(key=lambda r:r['start'])
    return selected[:150],len(selected)>150


def detect_cuts(media,options,notify):
    from scenedetect import open_video,SceneManager
    from scenedetect.detectors import AdaptiveDetector
    video=open_video(str(media));manager=SceneManager()
    manager.auto_downscale=False;manager.downscale=max(1,video.frame_size[0]//360)
    manager.add_detector(AdaptiveDetector(adaptive_threshold=options.scene_threshold,
        min_scene_len=max(1,round(video.frame_rate*options.min_scene_seconds))))
    expired=threading.Event()
    def timeout():expired.set();manager.stop()
    timer=threading.Timer(600,timeout);timer.daemon=True;timer.start()
    try:
        manager.detect_scenes(video=video,show_progress=False,
            callback=lambda image,frame:notify('正在本机检测画面切换，已扫描至 '+clock(frame.seconds if hasattr(frame,'seconds') else frame/video.frame_rate)+'…'))
        if expired.is_set():raise RuntimeError('画面切换扫描超时，其他检测结果已保留。')
        scenes=manager.get_scene_list(start_in_scene=True)
        return [{'id':marker_id('scene',round(start.seconds,4)),'kind':'scene',
            'start':round(start.seconds,3),'end':round(start.seconds,3),
            'previous_start':round(scenes[i-1][0].seconds,3),'next_end':round(end.seconds,3),
            'reason':'相邻帧的颜色与亮度变化触发自适应阈值，可能是切镜、闪光或明显运动。',
            'suggestion':'作为分镜核对位置；画面变化不等于内容重要，也不直接作为删减依据。'}
            for i,(start,end) in enumerate(scenes) if i>0]
    finally:
        timer.cancel()
        # VideoStreamCv2 owns an OpenCV capture. Release it after a complete scan.
        if hasattr(video,'_cap'):video._cap.release()


def analyze(media,folder,ffmpeg,duration,rows,has_video,options,notify=lambda _:None):
    source=fingerprint(media);row_hash=hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    key=hashlib.sha256(json.dumps([VERSION,source,row_hash,asdict(options)],sort_keys=True).encode()).hexdigest()
    cache=folder/f'markers-{key[:20]}.json'
    if cache.exists():return json.loads(cache.read_text(encoding='utf-8'))
    result={'version':VERSION,'source_hash':source,'timeline_hash':row_hash,'settings':asdict(options),
            'silences':[],'repeats':[],'cuts':[],'statuses':{},'warnings':[],
            'limitations':['静音检测反映音量，背景音乐可能遮住口播停顿。','重复检测引用本机带时间戳转写，相似文字不等于口误。',
                            '场景切换是视觉变化候选，可能漏检渐变或误报闪光；不代表内容重要程度。'],
            'policy':'mark_only','duration':duration}
    for name,action in [('silences',lambda:detect_silences(media,ffmpeg,duration,options)),
                        ('repeats',lambda:detect_repeats(rows,options.repeat_similarity)),
                        ('cuts',lambda:detect_cuts(media,options,notify))]:
        if name=='cuts' and not has_video:
            result['statuses'][name]='not_applicable';continue
        if name=='repeats' and not rows:
            result['statuses'][name]='error';result['warnings'].append('缺少真实时间戳，重复口播检测未运行。');continue
        notify({'silences':'正在标记低音量区间…','repeats':'正在对比疑似重复口播…','cuts':'正在扫描画面切换…'}[name])
        try:
            output=action()
            if name=='repeats':
                output,limited=output
                if limited:result['warnings'].append('相似口播较多，仅展示前150组，请结合原声核对。')
            result[name]=output;result['statuses'][name]='done'
        except Exception:
            result['statuses'][name]='error'
            result['warnings'].append({'silences':'静音检测失败，其他结果仍保留。','repeats':'重复口播检测失败，其他结果仍保留。',
                                       'cuts':'画面切换检测失败，其他结果仍保留。'}[name])
    for item in result['silences']:
        if any(item['start']-.3<=c['start']<=item['end']+.3 for c in result['cuts']):
            item['near_cut']=True;item['suggestion']='附近有画面切换，先核对转场与情绪停顿；当前保留原片。'
    # Cache only complete scans; a failed detector should be retryable, not stuck in a cache.
    if 'error' not in result['statuses'].values():
        temp=cache.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(cache)
    return result


def all_markers(result):return result.get('silences',[])+result.get('repeats',[])+result.get('cuts',[])


def markdown(result,title):
    from client.reports import table
    names={'silence':'低音量','repeat':'疑似重复口播','scene':'画面切换'};decisions=result.get('decisions',{})
    labels={'pending':'待查看','keep':'保留','reviewed':'已查看'}
    rows=[]
    for m in sorted(all_markers(result),key=lambda m:m['start']):
        proof=(m['original']['text']+' → '+m['repeated']['text']+f"（相似度 {m['similarity']}%）") if m['kind']=='repeat' else m['reason']
        rows.append((clock(m['start'])+'–'+clock(m['end']) if m['end']>m['start'] else clock(m['start']),names[m['kind']],
                     proof,m['suggestion'],labels.get(decisions.get(m['id'],'pending'),'待查看')))
    return '# 参考检测标记与建议\n\n'+title+'\n\n仅做标记，原片、口播和原结构均保留。\n\n'+table(
        ['时间','类型','检测依据','建议','查看状态'],rows)+'\n\n## 检测限制\n\n'+'\n'.join('- '+s for s in result.get('limitations',[])+result.get('warnings',[]))
