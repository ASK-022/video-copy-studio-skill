'use strict';
class WorkflowRules {
  static visible(entry,filter,review,index){
    if(filter.status&&(entry?.status||'review')!==filter.status)return false;
    const related=(review?.pairs||[]).some(pair=>pair.a===index||pair.b===index);
    if(filter.similarity==='similar')return related;
    if(filter.similarity==='different')return !!review?.items.some(item=>item.index===index)&&!related;
    return true;
  }
  static split(text,mode){
    if(mode==='one')return [text];
    if(mode==='separator')return text.split(/^\s*---+\s*$/m).filter(part=>part.trim());
    const matches=[...text.matchAll(/^[ \t]*(?:(?:脚本|文案)[ \t]*[一二三四五六七八九十\d]+|第[一二三四五六七八九十\d]+[条篇份](?:脚本|文案)?)[^\n]{0,60}$/gm)];
    if(matches.length<2)return [text];
    const starts=matches.map(match=>match.index);starts[0]=0;return starts.map((start,i)=>text.slice(start,starts[i+1]??text.length));
  }
}
