'use strict';
(function(root){
  function chooseFrames(segment,frames,preferred=[],interval=3){
    const valid=(frames||[]).filter(f=>Number.isSafeInteger(f.id)&&Number.isFinite(f.time)&&f.time>=0);
    const explicit=valid.filter(f=>preferred.includes(f.id));
    if(explicit.length)return {frames:explicit.slice(0,2),nearby:false};
    if(!Number.isFinite(segment?.start)||!Number.isFinite(segment?.end)||segment.end<=segment.start)return {frames:[],nearby:false};
    const middle=(segment.start+segment.end)/2;
    const inside=valid.filter(f=>f.time>=segment.start&&f.time<=segment.end).sort((a,b)=>Math.abs(a.time-middle)-Math.abs(b.time-middle));
    if(inside.length)return {frames:inside.slice(0,1),nearby:false};
    const closest=valid.slice().sort((a,b)=>Math.abs(a.time-middle)-Math.abs(b.time-middle))[0];
    const gap=closest?Math.max(segment.start-closest.time,closest.time-segment.end,0):Infinity;
    return {frames:gap<=Math.max(0,Number(interval)||3)?[closest]:[],nearby:true};
  }
  const api={chooseFrames};root.ReportMediaRules=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
