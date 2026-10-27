"""Six deliverables from the installed studio skill, with source-bound output validation."""
import hashlib
import json
import re
from typing import Literal

from pydantic import Field
from client.ai import StrictModel, Structure, normalized, validate_structure
from client.evidence import clock, screen_groups

SCENES={'transcript':'视频转文字','summary':'内容分析总结','breakdown':'爆款视频拆解','storyboard':'视频转脚本',
        'prompts':'视频提示词反推'}
DIMENSIONS=['钩子力','节奏密度','情绪势能','价值密度','转化引导','可复制性']
Dimension=Literal['钩子力','节奏密度','情绪势能','价值密度','转化引导','可复制性']


def text_hash(text):return hashlib.sha256(text.encode()).hexdigest()


class CleanParagraph(StrictModel):
    title:str=Field(min_length=1,max_length=40)
    source_ids:list[int]=Field(min_length=1)
    clean_text:str=Field(min_length=1)
    spoken_highlight:str=Field(min_length=1)
    clean_highlight:str=Field(min_length=1)


class CleanReport(StrictModel):
    overview:str
    paragraphs:list[CleanParagraph]=Field(min_length=1)


class Chapter(StrictModel):
    source_ids:list[int]=Field(min_length=1)
    title:str
    description:str


class Quote(StrictModel):
    segment_id:int
    text:str=Field(min_length=1)


class Summary(StrictModel):
    thesis:str
    chapters:list[Chapter]=Field(min_length=1,max_length=8)
    key_points:list[str]=Field(min_length=1,max_length=10)
    quotes:list[Quote]=Field(min_length=1,max_length=5)
    audience:str
    viewing_value:str
    call_to_action:str


class Score(StrictModel):
    dimension:Dimension
    score:float=Field(ge=1,le=10)
    quote:str=Field(min_length=1)
    reason:str=Field(min_length=1)


class Quality(StrictModel):
    scores:list[Score]=Field(min_length=6,max_length=6)
    suggestions:list[str]=Field(max_length=8)


class BreakdownRow(StrictModel):
    segment_id:int
    technique:str
    quote:str=Field(min_length=1)


class Breakdown(StrictModel):
    synopsis:str
    script_type:str
    type_reason:str
    structure:list[BreakdownRow]=Field(min_length=1)
    algorithm_design_hypotheses:list[str]=Field(min_length=1,max_length=6)
    content_strengths:list[str]=Field(min_length=1,max_length=6)
    quality:Quality
    skeleton_template:list[str]=Field(min_length=1,max_length=40)
    hook_formulas:list[str]=Field(min_length=1,max_length=5)
    reusable_phrases:list[str]=Field(min_length=1,max_length=8)


class Shot(StrictModel):
    segment_id:int
    visual:str
    evidence_frame_ids:list[int]
    camera_inference:str
    motion_inference:str
    transition_inference:str
    emotion_inference:str
    notes:str


class Storyboard(StrictModel):
    overview:str
    shots:list[Shot]=Field(min_length=1,max_length=40)
    clean_narration:str


class PromptShot(StrictModel):
    segment_id:int
    prompt:str
    motion:str
    tool_tips:str


class Prompts(StrictModel):
    style_prompt:str
    shots:list[PromptShot]=Field(min_length=1,max_length=40)
    narration:str
    adaptation_notes:list[str]=Field(max_length=10)


class Observation(StrictModel):
    frame_id:int
    description:str


class Observations(StrictModel):
    frames:list[Observation]=Field(min_length=1,max_length=12)
    limitations:list[str]


def source_ids(values,segments,cover=False):
    expected=[s['id'] for s in segments]
    if any(i not in expected for i in values):raise ValueError('引用了不存在的原文段落。')
    if cover and values!=expected:raise ValueError('必须按原顺序完整覆盖每段原文且只能出现一次。')


def quote_in(quote,text):
    if normalized(quote) not in normalized(text):raise ValueError('引文必须逐字引用原文中的连续片段，不可省略或改写。')


def quality_valid(q,text):
    if sorted(s.dimension for s in q.scores)!=sorted(DIMENSIONS):raise ValueError('六个评分维度必须齐全且不能重复。')
    for s in q.scores:quote_in(s.quote,text)
    return q


def score_result(quality):
    result=quality.model_dump() if hasattr(quality,'model_dump') else quality
    avg=round(sum(s['score'] for s in result['scores'])/6,2)
    result.update(average=avg,grade='S' if avg>=8.5 else 'A' if avg>=7.5 else 'B' if avg>=6 else 'C',
                  needs_revision=any(s['score']<7 for s in result['scores']))
    return result


def assess(client,variant):
    text='\n'.join(s['text'] for s in variant['segments'])
    q=client.call('评估这份新写脚本的六维质量。这是编辑预测，不能声称已取得流量或销量。'
       '六维依次为钩子力、节奏密度、情绪势能、价值密度、转化引导、可复制性，每项1到10分。'
       '每项用成稿中的连续原话作quote并解释依据；不要为了及格虚高打分。给出可执行改进建议。'
       '不要要求编造容量、功效、使用经历、价格、优惠或证据来提高评分，资料不足时建议改进表达与信息组织。',
       {'script':variant},Quality,lambda q:quality_valid(q,text))
    return score_result(q)


def budget_rows(segments,duration):
    total=sum(len(s['text']) for s in segments) or 1
    return [{**s,'duration_budget':round(duration*len(s['text'])/total,1),
             'screen_suggestion':s['role']+'：'+s['text'][:24]} for s in segments]


def enrich_variant(client,variant,reference,mode,facts,direction,duration):
    quality=assess(client,variant);revised=False;note='';revision_error=''
    if quality['needs_revision']:
        feedback='；'.join(quality['suggestions'])
        try:
            revised_variant=client.generate(reference,mode,facts,1,direction+'\n基于以下质检意见改写一轮，仍须保留全部原结构：'+feedback)['variants'][0]
            revised_quality=assess(client,revised_variant)
            variant=revised_variant;quality=revised_quality;revised=True;note=feedback
        except (ValueError,RuntimeError):
            revision_error='改写或复评分未完成，保留原稿和首次有效评分；可根据建议手动修改。'
    return {**variant,'quality':quality,'revision':{'performed':revised,'reason':note},
            'revision_error':revision_error,
            'production_segments':budget_rows(variant['segments'],duration),
            'tts_narration':' / '.join(s['text'] for s in variant['segments'])}


def context(item,evidence,segments):
    return {'title':item['title'],'duration':item.get('duration'),'segments':segments,
            'screen_text':screen_groups(evidence.get('frames',[])),
            'observations':evidence.get('observations',[]),'cue_evidence':evidence.get('cue_text',''),
            'limitations':evidence.get('limitations',[]),
            'rules':'口播是内容陈述，不代表商品功效已验证。不能编造实际互动率、销量或转化率。'
                    'start/end为本地音频对齐观测值，null表示未对齐。人物身份不可仅凭画面确认。'
                    '无视觉描述时visual写「画面未识别」；拍摄建议与推断需注明。'}


def generate_report(client,scene,item,evidence,segments):
    if scene in ('storyboard','prompts') and len(segments)>8:
        parts=[]
        for i in range(0,len(segments),8):
            group=segments[i:i+8];part_item={**item,'corrected':''.join(s['text'] for s in group)}
            parts.append(generate_report(client,scene,part_item,evidence,group))
        result=parts[0];result['shots']=[s for p in parts for s in p['shots']]
        if scene=='storyboard':result['clean_narration']='\n\n'.join(p['clean_narration'] for p in parts)
        else:
            result['narration']=' / '.join(p['narration'] for p in parts)
            result['adaptation_notes']=list(dict.fromkeys(s for p in parts for s in p['adaptation_notes']))[:10]
        return result
    ctx=context(item,evidence,segments);by_id={s['id']:s for s in segments}
    text=item['corrected'];schema=None
    if scene=='transcript':
        schema=CleanReport
        task=('制作分段净稿和原口播存档。将连续原文段落按主题组合为3至8组（极短视频可更少），'
              'source_ids顺序完整覆盖原结构且不遗漏不重复。每组有简短小标题。clean_text只去语气词、修标点，不改事实不遗漏内容。'
              'spoken_highlight逐字引用该组原文，clean_highlight逐字引用clean_text，供加粗重点。')
        def validate(r):
            source_ids([i for p in r.paragraphs for i in p.source_ids],segments,True)
            for p in r.paragraphs:
                quote_in(p.spoken_highlight,''.join(by_id[i]['text'] for i in p.source_ids));quote_in(p.clean_highlight,p.clean_text)
            return r
    elif scene=='summary':
        schema=Summary;task='总结主旨、3到6组结构章节、最多10个核心要点、3到5句原文金句、受众、观看价值和结尾CTA。章节source_ids按顺序覆盖原结构。金句需真实引用对应segment_id的原话。'
        def validate(r):
            source_ids([i for p in r.chapters for i in p.source_ids],segments,True)
            for q in r.quotes:
                source_ids([q.segment_id],segments);quote_in(q.text,by_id[q.segment_id]['text'])
            return r
    elif scene=='breakdown':
        schema=Breakdown;task=('拆解视频说服结构，不预设它真的爆款。逐段structure的segment_id完整对应原结构，引用对应段内的连续原话。'
          '分析脚本类型及依据、算法留存/互动设计假设、内容优势，给出占位符骨架、钩子公式与话术库。'
          '六维钩子力/节奏密度/情绪势能/价值密度/转化引导/可复制性，每维1到10分并逐字引用原话说明。'
          '算法效果是待验证推测，不能写成已获得的完播率或真实爆款原因。无画面描述时节奏只能评价口播。')
        def validate(r):
            source_ids([p.segment_id for p in r.structure],segments,True)
            for row in r.structure:quote_in(row.quote,by_id[row.segment_id]['text'])
            quality_valid(r.quality,text);return r
    elif scene=='storyboard':
        schema=Storyboard;task=('按原结构生成逐段分镜脚本表，shots的segment_id完整按顺序对应输入原结构。'
          'visual只描述observations/Cue明确支持的画面，无视觉输入写画面未识别。evidence_frame_ids只填所用画面证据编号。'
          '景别机位、运镜、转场和情绪均写入inference字段作为推断/翻拍建议，不能声称测得精确镜头边界。'
          '附clean_narration去语气词净稿，保留所有原意。')
        def validate(r):
            source_ids([p.segment_id for p in r.shots],segments,True)
            frames={f['id'] for f in evidence.get('frames',[])}
            for row in r.shots:
                if any(i not in frames for i in row.evidence_frame_ids):raise ValueError('画面证据编号不存在。')
            return r
    else:
        schema=Prompts;task=('反推可用于生成式视频的提示词。style_prompt写主体/场景/风格/构图/色调/光线/画幅，未观察到的项标建议。'
          '每段一个shot，segment_id按顺序完整对应原结构；prompt采用主体-动作-镜头-风格四段式，motion是运镜建议，'
          'tool_tips写适配即梦/可灵/Vidu/Runway/Pika的通用使用建议，不假设最新参数。'
          'narration使用原口播并加 / 停顿、**重点**。全部视觉风格和分镜prompt属于创作推断，不能说是原片精确还原。')
        def validate(r):
            source_ids([p.segment_id for p in r.shots],segments,True)
            # TTS markers may change formatting, but must preserve the actual spoken words.
            def words(t):return re.sub(r'[\W_]+','',t)
            if words(r.narration)!=words(text):raise ValueError('TTS文案只可添加停顿和重音，不得增删原口播文字。')
            return r
    report=client.call(task,ctx,schema,validate).model_dump()
    if scene=='breakdown':report['quality']=score_result(report['quality'])
    return report


def span(segments):
    starts=[s['start'] for s in segments if s.get('start') is not None];ends=[s['end'] for s in segments if s.get('end') is not None]
    return clock(min(starts))+'–'+clock(max(ends)) if starts and ends else '时间未对齐'


def table(headers,rows):
    def cell(v):return str(v if v is not None else '未识别').replace('|','／').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(cell(v) for v in row)+' |' for row in rows])


def score_markdown(q,segments=None):
    text=f"六维均分 **{q['average']} / 10** · **{q['grade']}** 级（编辑评估，不代表实际播放或转化表现）\n\n"
    def cite(s):
        if segments:
            found=next((p for p in segments if normalized(s['quote']) in normalized(p['text'])),None)
            if found:return span([found])+' '+s['quote']
        return s['quote']
    text+=table(['维度','评分','依据','说明'],[(s['dimension'],s['score'],cite(s),s['reason']) for s in q['scores']])
    if q.get('suggestions'):text+='\n\n'+ '\n'.join('- '+s for s in q['suggestions'])
    return text


def markdown(scene,r,item,evidence,segments):
    by_id={s['id']:s for s in segments};screen=screen_groups(evidence.get('frames',[]))
    lines=['# '+SCENES[scene],item['title'],'> 时间来自本机音频对齐；画面按间隔抽样，OCR 可能有误。镜头、运镜、转场与情绪建议均为推断。']
    if scene=='transcript':
        lines+=['## 内容速览',r['overview'],'## 口播全文（分段）']
        for p in r['paragraphs']:
            group=[by_id[i] for i in p['source_ids']];full=''.join(s['text'] for s in group)
            full=full.replace(p['spoken_highlight'],'**'+p['spoken_highlight']+'**',1)
            lines += ['### 【'+span(group)+'】'+p['title'],full]
        lines+=['## 净稿（分段）']
        for p in r['paragraphs']:lines+=['### '+p['title'],p['clean_text'].replace(p['clean_highlight'],'**'+p['clean_highlight']+'**',1)]
        lines+=['## 画面文字稿（按主题分组，重复文字仅保留首次）']
        for title,entries in [('数字与价格',[x for x in screen if re.search(r'\d|元|折|¥|￥',x['text'])]),
                              ('字幕与其他文字',[x for x in screen if not re.search(r'\d|元|折|¥|￥',x['text'])])]:
            lines+=['### '+title,table(['首次出现','画面识别文字'],[(clock(x['time']),x['text']) for x in entries]) if entries else '未识别到相应文字。']
        lines+=['## 时间线合并稿',table(['时间','段落功能','口播','抽样屏幕文字'],[(span([s]),s['role'],s['text'],screen_near(s,screen)) for s in segments])]
    elif scene=='summary':
        lines+=['## 一句话主旨',r['thesis'],'## 结构分段',table(['时间','主题','内容'],[(span([by_id[i] for i in c['source_ids']]),c['title'],c['description']) for c in r['chapters']]),
                '## 核心要点','\n'.join('- '+x for x in r['key_points']),'## 金句摘录']
        lines+=['- 【'+span([by_id[q['segment_id']]])+'】'+q['text'] for q in r['quotes']]
        lines+=['## 目标受众',r['audience'],'## 观看价值',r['viewing_value'],'## 结尾 CTA',r['call_to_action']]
    elif scene=='breakdown':
        lines+=['## 一屏速览',r['synopsis'],'## 基本盘',f"标题：{item['title']}；时长：{item.get('duration',0):.1f} 秒。博主、标签和互动数据未接入，不作推测。",
          '## 结构分段表',table(['时间轴','段落功能','对齐跨度（秒）','手法','话术摘录'],[(span([by_id[x['segment_id']]]),by_id[x['segment_id']]['role'],
            round(by_id[x['segment_id']]['end']-by_id[x['segment_id']]['start'],1) if by_id[x['segment_id']].get('start') is not None else '未对齐',x['technique'],x['quote']) for x in r['structure']]),
          '## 脚本类型',r['script_type']+'：'+r['type_reason'],'## 算法层设计假设（尚无真实效果数据）','\n'.join('- '+x for x in r['algorithm_design_hypotheses']),
          '## 内容层优势','\n'.join('- '+x for x in r['content_strengths']),'## 六维评分',score_markdown(r['quality'],segments),
          '## 可复用骨架','\n'.join('- '+x for x in r['skeleton_template']),'## 钩子公式','\n'.join('- '+x for x in r['hook_formulas']),
          '## 话术库','\n'.join('- '+x for x in r['reusable_phrases']),'## 节奏参考','各段时间跨度见结构表。音频对齐跨句重叠不等于镜头切换；翻拍需结合实拍调整。']
    elif scene=='storyboard':
        lines+=['## 分镜速览',r['overview'],'## 分镜脚本表（按口播段落组织，非精确切镜检测）',table(
           ['时间线','镜头 ⚠推断','运镜 ⚠推断','转场 ⚠推断','画面内容','屏幕文字（OCR）','口播','情绪 ⚠推断','备注'],
           [(span([by_id[x['segment_id']]]),x['camera_inference'],x['motion_inference'],x['transition_inference'],x['visual'],
             screen_near(by_id[x['segment_id']],screen),by_id[x['segment_id']]['text'],x['emotion_inference'],x['notes']) for x in r['shots']]),'## 口播净稿',r['clean_narration']]
    else:
        lines+=['## 整体风格提示词（创作推断）',r['style_prompt'],'## 分镜提示词序列（创作建议）',table(
          ['镜号','原口播时间','画面 prompt','运镜建议','工具适配'],[(i,span([by_id[s['segment_id']]]),s['prompt'],s['motion'],s['tool_tips']) for i,s in enumerate(r['shots'],1)]),
          '## TTS 口播（/ 为停顿，**为重音）',r['narration'],'## 结构化 JSON','```json\n'+json.dumps(r,ensure_ascii=False,indent=2)+'\n```',
          '## 使用说明','\n'.join('- '+s for s in r['adaptation_notes'])]
    lines+=['## 证据与限制','\n'.join('- '+s for s in evidence.get('limitations',[]))]
    return '\n\n'.join(lines)


def screen_near(s,screen):
    if s.get('start') is None:return '时间未对齐'
    return '；'.join(x['text'] for x in screen if s['start']<=x['time']<=s['end']) or '该跨度抽样未识别到文字'
