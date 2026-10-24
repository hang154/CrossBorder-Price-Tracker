/* Shared by the editor preview and the frame exporter. No network or model calls. */
(function(global){
  'use strict';
  const selectors={title:'h2',body:'.body',image:'.photo',cards:'.cards'};
  const labels={title:'제목',body:'본문',image:'사진',cards:'보조 카드'};
  const effects={rise:'위로 등장',fade:'서서히 등장',left:'왼쪽에서 등장',zoom:'확대하며 등장',none:'움직임 없음'};
  function tracks(m={}){
    const defaults={title:{effect:'rise',start:m.title_start??.2,duration:m.enter_duration??.65},body:{effect:'rise',start:m.body_start??.8,duration:m.enter_duration??.65},image:{effect:'none',start:0,duration:.8},cards:{effect:'none',start:0,duration:.8}};
    return Object.fromEntries(Object.keys(selectors).map(k=>[k,{enabled:true,...defaults[k],...(m.tracks?.[k]||{})}]));
  }
  function pose(track,time){
    if(!track.enabled||track.effect==='none')return {opacity:1,transform:'none'};
    const progress=Math.max(0,Math.min(1,(time-track.start)/track.duration));
    const eased=1-Math.pow(1-progress,3),offset=1-eased;
    return {opacity:eased,transform:track.effect==='rise'?`translateY(${offset*32}px)`:track.effect==='left'?`translateX(${-offset*40}px)`:track.effect==='zoom'?`scale(${.9+eased*.1})`:'none'};
  }
  function apply(doc,motion,time){
    const rows=tracks(motion);
    for(const [key,selector]of Object.entries(selectors))for(const element of doc.querySelectorAll(selector)){
      const p=pose(rows[key],time);element.style.opacity=p.opacity;element.style.transform=p.transform;
    }
  }
  global.DetailMotion={selectors,labels,effects,tracks,pose,apply};
})(globalThis);
