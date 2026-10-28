"""Deterministic generation directions: no extra model call or invented facts."""
from pydantic import BaseModel,Field,field_validator

ANGLES=('日常场景表达','选择理由表达','面向受众的提问','产品细节表达','使用便利表达','克制推荐表达','自然口语叙述')


class Focus(BaseModel):
    enabled:bool=True
    audience:str=Field(default='',max_length=300)
    scenario:str=Field(default='',max_length=300)
    tone:str=Field(default='自然口语',max_length=100)
    strength:str=Field(default='balanced',pattern='^(light|balanced|strong)$')
    custom:dict[str,str]=Field(default_factory=dict)

    @field_validator('custom')
    @classmethod
    def validate_custom(cls,value):
        if len(value)>1000 or any(not k.isdecimal() or not 1<=int(k)<=9007199254740991 or not v.strip() or len(v)>500 for k,v in value.items()):
            raise ValueError('自定义方向需要有效的正整数序号、1–500 字内容，最多编辑 1000 项。')
        return value


def direction(focus,index):
    if not focus.enabled:return ''
    angle=focus.custom.get(str(index),ANGLES[(index-1)%len(ANGLES)])
    cycle=(index-1)//len(ANGLES)+1
    details=[angle]
    if cycle>1:details.append(f'表达组合第 {cycle} 组，避免沿用前稿句式')
    if focus.audience.strip():details.append('面向：'+focus.audience.strip())
    if focus.scenario.strip():details.append('场景联想：'+focus.scenario.strip()+'（不得编造亲测经历）')
    if focus.tone.strip():details.append('语气：'+focus.tone.strip())
    details.append({'light':'轻度调整措辞','balanced':'调整措辞和表达角度','strong':'明显变化句式与表达角度'}[focus.strength])
    return '；'.join(details)+'。始终保留原段数、顺序、段落功能和说服关系，不改变商品事实；上述方向不得强行改变原开场类型。'
