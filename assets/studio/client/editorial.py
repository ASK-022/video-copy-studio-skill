"""Local review metadata, text similarity and reference-library filtering."""
from collections import Counter
from datetime import datetime,timedelta,timezone
import hashlib
import re
import unicodedata
from rapidfuzz.fuzz import ratio

STATUSES={'review':'待审核','edit':'需修改','adopted':'已采用','shoot':'待拍摄','published':'已发布','discarded':'弃用'}


def normalized(text):return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())


def library_match(item,q='',project='',product='',tag='',start='',end=''):
    if project and item.get('project','')!=project:return False
    if product and normalized(product) not in normalized(item.get('product_label','')):return False
    if tag and tag not in item.get('tags',[]):return False
    day=datetime.fromtimestamp(item['created'],timezone(timedelta(hours=8))).date().isoformat()
    if start and day<start or end and day>end:return False
    if q:
        hay='\n'.join([item.get('title',''),item.get('raw',''),item.get('corrected',''),item.get('facts',''),item.get('project',''),item.get('product_label',''),*item.get('tags',[])])
        if normalized(q) not in normalized(hay):return False
    return True


def text_review(reference,rows,threshold=80):
    """Character trigrams + opening overlap; no semantic-model or performance claims."""
    def grams(t):return set(t[i:i+3] for i in range(max(1,len(t)-2))) if t else set()
    values=[normalized(row['text']) for row in rows];tokens=[grams(v) for v in values]
    pairs=[];reference_value=normalized(reference);summaries=[]
    for i,row in enumerate(rows):
        summaries.append({'index':row['index'],'revision':row['revision'],'reference_similarity':round(ratio(values[i],reference_value)),
            'opening':row['text'].strip().split('\n')[0][:60],'chars':len(row['text']),
            'changed':values[i]!=reference_value})
        for j in range(i):
            a,b=tokens[i],tokens[j];score=round(200*len(a&b)/(len(a)+len(b))) if a or b else 0
            opening=round(ratio(values[i][:45],values[j][:45]))
            if score>=threshold or opening>=92:
                pairs.append({'a':rows[j]['index'],'b':row['index'],'similarity':score,'opening_similarity':opening,
                    'reason':'正文相似' if score>=threshold else '开头相似'})
    pairs.sort(key=lambda p:(-p['similarity'],-p['opening_similarity']))
    fingerprint=hashlib.sha256('\n'.join(f"{r['index']}:{r['revision']}:{r['text']}" for r in rows).encode()).hexdigest()
    return {'pairs':pairs,'items':summaries,'threshold':threshold,'fingerprint':fingerprint,'method':'本机文本重合与开头相似度；商品名和固定卖点会影响分数，需人工判断。'}
